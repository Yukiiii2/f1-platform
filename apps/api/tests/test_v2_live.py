"""V2 near-live checks using isolated data and controlled provider transports."""

import asyncio
import copy
import importlib.util
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import test_phase11
from sqlalchemy import func, select

ACTIVE = datetime(2025, 3, 16, 4, 3, tzinfo=timezone.utc)


class LiveTests(unittest.TestCase):
    def setUp(self):
        from app.providers.openf1 import OpenF1Provider

        self.fixture = test_phase11.Phase11Tests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.data = self.fixture.data
        self.data["race_control"].append(
            {
                "session_key": 9999,
                "date": "2025-03-16T04:00:00Z",
                "category": "SessionStatus",
                "message": "SESSION STARTED",
                "driver_number": None,
            }
        )
        self.requests = []

        def respond(request):
            self.requests.append(request)
            if request.url.path == "/token":
                return httpx.Response(
                    200,
                    json={
                        "access_token": "fixture-live-token",
                        "expires_in": 3600,
                        "token_type": "bearer",
                    },
                )
            endpoint = request.url.path.rsplit("/", 1)[-1]
            rows = copy.deepcopy(self.data[endpoint])
            if "driver_number" in request.url.params:
                rows = [
                    row
                    for row in rows
                    if row.get("driver_number")
                    == int(request.url.params["driver_number"])
                ]
            for field, operation in (
                ("date>=", lambda a, b: a >= b),
                ("date<=", lambda a, b: a <= b),
            ):
                if field in request.url.params:
                    cutoff = datetime.fromisoformat(request.url.params[field])
                    rows = [
                        row
                        for row in rows
                        if operation(
                            datetime.fromisoformat(row["date"].replace("Z", "+00:00")),
                            cutoff,
                        )
                    ]
            return httpx.Response(200, json=rows)

        client = httpx.Client(transport=httpx.MockTransport(respond))
        self.addCleanup(client.close)
        self.provider = OpenF1Provider(
            client=client,
            sleep=lambda _: None,
            username="fixture-user",
            password="fixture-password",
        )

    def register(self):
        from app.workers.sessions import register_session

        return register_session(
            self.fixture.factory,
            self.fixture.session_id,
            9999,
            {7: self.fixture.driver_id},
            now=ACTIVE,
            live=True,
        )

    def tick(self, now=ACTIVE):
        from app.workers.sessions import run_once

        return run_once(
            self.fixture.factory,
            self.fixture.core,
            self.provider,
            now=now,
            live_interval=60,
        )

    def test_active_detection_requires_source_signal_and_ignores_future_signals(self):
        self.assertTrue(self.provider.inspect_live_session(9999, ACTIVE).active)
        self.data["race_control"] = []
        self.assertFalse(self.provider.inspect_live_session(9999, ACTIVE).active)
        self.data["race_control"] = [
            {
                "session_key": 9999,
                "date": "2025-03-16T05:00:00Z",
                "category": "SessionStatus",
                "message": "SESSION STARTED",
            }
        ]
        self.assertFalse(self.provider.inspect_live_session(9999, ACTIVE).active)

    def test_live_poll_is_incremental_idempotent_provisional_without_core(
        self,
    ):
        self.register()
        self.tick()
        models, factory = self.fixture.models, self.fixture.factory
        with factory() as db:
            lap = db.scalar(select(models.Lap))
            identifier = lap.id
            raw_count = db.scalar(
                select(func.count()).select_from(models.TelemetrySourceRecord)
            )
            job = db.scalar(select(models.SessionUpdateJob))
            self.assertEqual(job.data_status, "provisional")
            self.assertTrue(job.live_cursor)
            self.assertEqual(
                db.get(models.Session, self.fixture.session_id).status, "in_progress"
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(models.Result)), 0
            )
        self.fixture.core.fetch.assert_not_called()
        self.tick(ACTIVE + timedelta(minutes=2))
        with factory() as db:
            self.assertEqual(db.scalar(select(models.Lap.id)), identifier)
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(models.TelemetrySourceRecord)
                ),
                raw_count,
            )
            self.assertEqual(
                db.scalar(select(models.SessionUpdateJob)).row_counts["lap"], 0
            )
        telemetry_requests = [
            request
            for request in self.requests
            if request.url.path.endswith("/car_data")
        ]
        self.assertEqual(len(telemetry_requests), 2)
        self.assertTrue(
            all(
                "date>=" in request.url.params and "date<=" in request.url.params
                for request in telemetry_requests
            )
        )
        self.assertEqual(
            sum(request.url.path == "/token" for request in self.requests), 1
        )

    def test_finalization_uses_full_import_and_marks_final_only_after_success(
        self,
    ):
        self.register()
        self.tick()
        self.requests.clear()
        self.tick(ACTIVE + timedelta(days=1))
        job = self.fixture.job()
        self.assertEqual(job.status, "succeeded")
        self.assertEqual(job.data_status, "finalized")
        self.assertEqual(job.completion_evidence["kind"], "published_results")
        requests = [
            request
            for request in self.requests
            if request.url.path.endswith("/car_data")
        ]
        self.assertTrue(requests)
        self.assertTrue(all("date>=" not in request.url.params for request in requests))
        self.assertTrue(
            all("Authorization" not in request.headers for request in requests)
        )

    def test_live_failures_suspend_polling_without_killing_finalization(self):
        from app.providers.base import ProviderError

        self.register()
        with patch.object(
            self.provider,
            "inspect_live_session",
            side_effect=ProviderError("private-token-must-not-leak"),
        ):
            for minute in (0, 2, 5):
                self.tick(ACTIVE + timedelta(minutes=minute))
        job = self.fixture.job()
        self.assertTrue(job.live_suspended)
        self.assertEqual(job.status, "pending")
        self.assertNotIn("private", job.failure_details)
        self.tick(ACTIVE + timedelta(days=1))
        self.assertEqual(self.fixture.job().status, "succeeded")

    def test_api_and_pitwall_mark_provisional_and_hide_final_classification(self):
        from app.ai.tools import ToolExecutor
        from app.api import core
        from app.schemas.ai import PageContext

        self.register()
        self.tick()
        with self.fixture.factory() as db:
            session = core.session(db, self.fixture.session_id)
            self.assertEqual(session.updates.data_status, "provisional")
            self.assertEqual(
                next(
                    row
                    for row in core.sessions(db, session.event_id)
                    if row.id == session.id
                ).updates.data_status,
                "provisional",
            )
            self.assertEqual(
                core.session_updates(db, session.id).data_status, "provisional"
            )
            executor = ToolExecutor(db, PageContext(session_id=session.id))
            result = executor.execute("get_laps", {"session_id": str(session.id)})
            self.assertEqual(result.data_status, "provisional")
            info = executor.execute("get_session", {"session_id": str(session.id)})
            self.assertNotIn("status", info.data["source"])
            self.assertEqual(
                info.data["derived"]["session_status"][0]["status"], "in_progress"
            )
            # Provisional positions can never become a final classification API.
            self.assertEqual(core.results(db, session.id), [])

    def test_overlap_defers_and_failed_import_does_not_advance_cursor(self):
        from contextlib import contextmanager

        @contextmanager
        def unavailable(engine):
            yield False

        self.register()
        with patch("app.workers.sessions.worker_lock", unavailable):
            self.assertEqual(self.tick(), 0)
        self.assertEqual(self.requests, [])
        self.data["car_data"][0]["speed"] = -1
        self.tick()
        self.assertEqual(self.fixture.job().live_cursor, {})
        with self.fixture.factory() as db:
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(
                        self.fixture.models.TelemetrySourceRecord
                    )
                ),
                0,
            )

    def test_incremental_new_samples_and_corrections_preserve_revisions_and_stale_order(
        self,
    ):
        from dataclasses import replace

        from app.ingestion.telemetry import persist_session_bundle

        self.register()
        self.tick()
        self.provider.inspect_live_session(9999, ACTIVE + timedelta(minutes=1))
        stale = self.provider.fetch_incremental(
            9999, [7], self.fixture.job().live_cursor, ACTIVE + timedelta(minutes=1)
        )
        self.data["laps"][0]["lap_duration"] = 100
        sample = copy.deepcopy(self.data["car_data"][0])
        sample["date"] = "2025-03-16T04:04:00Z"
        sample["brake"] = 104
        self.data["car_data"].append(sample)
        self.tick(ACTIVE + timedelta(minutes=2))
        with self.fixture.factory.begin() as db:
            lap = db.scalar(select(self.fixture.models.Lap))
            self.assertEqual(lap.duration_seconds, 100)
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(
                        self.fixture.models.TelemetrySample
                    )
                ),
                2,
            )
            newest = db.scalar(
                select(self.fixture.models.TelemetrySample).order_by(
                    self.fixture.models.TelemetrySample.timestamp.desc()
                )
            )
            self.assertIsNone(newest.brake_applied)
            raw = db.get(
                self.fixture.models.TelemetrySourceRecord, newest.source_record_id
            )
            self.assertEqual(raw.payload["brake"], 104)
            counts = persist_session_bundle(
                db,
                "openf1",
                self.fixture.session_id,
                9999,
                {7: self.fixture.driver_id},
                stale,
                changed_only=True,
            )
            self.assertEqual(counts["lap"], 0)
            self.assertEqual(lap.duration_seconds, 100)
        # Restore A, observe unchanged A again, then reject the older B observation.
        self.data["laps"][0]["lap_duration"] = stale.records[0].source_payload[
            "lap_duration"
        ]
        self.tick(ACTIVE + timedelta(minutes=4))
        with self.fixture.factory() as db:
            lap = db.scalar(select(self.fixture.models.Lap))
            restored = lap.duration_seconds
            latest = lap.source_observed_at
        self.tick(ACTIVE + timedelta(minutes=6))
        delayed = replace(
            stale, observation_started_at=latest - timedelta(microseconds=1)
        )
        record = replace(
            delayed.records[0],
            attributes={**delayed.records[0].attributes, "duration_seconds": 100},
            source_payload={**delayed.records[0].source_payload, "lap_duration": 100},
        )
        delayed = replace(delayed, records=[record])
        with self.fixture.factory.begin() as db:
            persist_session_bundle(
                db,
                "openf1",
                self.fixture.session_id,
                9999,
                {7: self.fixture.driver_id},
                delayed,
                changed_only=True,
            )
            self.assertEqual(
                db.scalar(select(self.fixture.models.Lap)).duration_seconds, restored
            )

    def test_nullable_end_pause_resume_cancellation_and_qualifying_phase(self):
        self.data["sessions"][0]["date_end"] = None
        self.assertTrue(self.provider.inspect_live_session(9999, ACTIVE).active)
        self.register()
        self.tick()
        for message, active in (
            ("SESSION STOPPED", False),
            ("SESSION RESUMED", True),
            ("SESSION ENDED", False),
        ):
            self.data["race_control"].append(
                {
                    "session_key": 9999,
                    "date": "2025-03-16T04:02:00Z",
                    "category": "SessionStatus",
                    "message": message,
                }
            )
            self.assertEqual(
                self.provider.inspect_live_session(9999, ACTIVE).active, active
            )
            self.data["race_control"].pop()
        self.data["race_control"].append(
            {
                "session_key": 9999,
                "date": "2025-03-16T04:02:00Z",
                "category": "SessionStatus",
                "message": "SESSION CANCELLED",
            }
        )
        self.assertTrue(self.provider.inspect_live_session(9999, ACTIVE).cancelled)
        self.data["race_control"].pop()
        self.data["sessions"][0]["session_name"] = "Qualifying"
        self.data["race_control"].append(
            {
                "session_key": 9999,
                "date": "2025-03-16T04:02:00Z",
                "category": "SessionStatus",
                "message": "SESSION ENDED",
                "qualifying_phase": 1,
            }
        )
        self.assertFalse(self.provider.inspect_live_session(9999, ACTIVE).settled)
        self.assertFalse(
            self.provider.inspect_live_session(9999, ACTIVE + timedelta(days=1)).active
        )

    def test_suspended_live_handoff_preserves_historical_retry_budget_within_same_day(
        self,
    ):
        from app.providers.base import ProviderError

        self.register()
        self.tick()
        with patch.object(
            self.provider,
            "inspect_live_session",
            side_effect=ProviderError("unavailable"),
        ):
            for minute in (2, 5, 10):
                self.tick(ACTIVE + timedelta(minutes=minute))
        self.assertTrue(self.fixture.job().live_suspended)
        original = self.fixture.core.fetch.side_effect
        self.fixture.core.fetch.side_effect = ProviderError(
            "historical temporary failure"
        )
        self.tick(ACTIVE + timedelta(hours=3))
        self.assertEqual(self.fixture.job().status, "retry")
        self.assertEqual(self.fixture.job().consecutive_failures, 1)
        self.fixture.core.fetch.side_effect = original
        self.tick(ACTIVE + timedelta(hours=4))
        self.assertEqual(self.fixture.job().status, "succeeded")
        self.assertEqual(self.fixture.job().data_status, "finalized")

    def test_live_retry_reenables_detection_and_ended_source_is_no_longer_labelled_live(
        self,
    ):
        from app.workers.sessions import retry_session

        self.register()
        self.tick()
        self.data["race_control"].append(
            {
                "session_key": 9999,
                "date": "2025-03-16T04:04:00Z",
                "category": "SessionStatus",
                "message": "SESSION ENDED",
            }
        )
        self.tick(ACTIVE + timedelta(minutes=2))
        self.assertFalse(self.fixture.job().live_active)
        self.assertEqual(self.fixture.job().data_status, "provisional")
        with self.fixture.factory.begin() as db:
            job = db.get(self.fixture.models.SessionUpdateJob, self.fixture.job().id)
            job.live_suspended = True
        self.data["race_control"].pop()
        retry_session(
            self.fixture.factory,
            self.fixture.session_id,
            now=ACTIVE + timedelta(minutes=3),
        )
        self.tick(ACTIVE + timedelta(minutes=3))
        self.assertTrue(self.fixture.job().live_active)
        self.assertFalse(self.fixture.job().live_suspended)
        self.fixture.core.fetch.assert_not_called()

    def test_cancelled_source_without_actual_times_is_terminal_not_a_validation_failure(
        self,
    ):
        from app.api.core import session

        self.register()
        self.tick()
        self.data["sessions"][0].update(
            is_cancelled=True, date_start=None, date_end=None
        )
        self.tick(ACTIVE + timedelta(minutes=2))
        self.assertEqual(self.fixture.job().status, "cancelled")
        with self.fixture.factory() as db:
            result = session(db, self.fixture.session_id)
            self.assertEqual(result.status, "cancelled")
            self.assertEqual(result.updates.data_status, "provisional")
            self.assertEqual(
                db.scalar(select(func.count()).select_from(self.fixture.models.Lap)), 1
            )
        self.fixture.core.fetch.assert_not_called()

    def test_recent_source_activity_can_detect_a_session_without_start_messages(self):
        self.data["race_control"] = []
        self.assertTrue(self.provider.inspect_live_session(9999, ACTIVE, [7]).active)
        self.assertFalse(
            self.provider.inspect_live_session(
                9999, ACTIVE + timedelta(minutes=10), [7]
            ).active
        )
        sample = copy.deepcopy(self.data["car_data"][0])
        sample.update(driver_number=9, date="2025-03-16T04:12:30Z")
        self.data["car_data"].append(sample)
        self.assertTrue(
            self.provider.inspect_live_session(
                9999, ACTIVE + timedelta(minutes=10), [7, 9]
            ).active
        )
        self.data["race_control"] = [
            {
                "session_key": 9999,
                "date": "2025-03-16T04:02:30Z",
                "category": "SessionStatus",
                "message": "SESSION ENDED",
            }
        ]
        self.assertFalse(self.provider.inspect_live_session(9999, ACTIVE, [7]).active)

    def test_windows_scope_and_live_provider_pacing_are_bounded(self):
        delays = []
        self.provider.sleep = delays.append
        self.register()
        self.tick()
        requests = [
            request
            for request in self.requests
            if request.url.path.endswith("/car_data")
        ]
        self.assertEqual(
            datetime.fromisoformat(requests[0].url.params["date>="]),
            ACTIVE - timedelta(seconds=120),
        )
        self.tick(ACTIVE + timedelta(minutes=10))
        request = [
            request
            for request in self.requests
            if request.url.path.endswith("/car_data")
        ][-1]
        span = datetime.fromisoformat(
            request.url.params["date<="]
        ) - datetime.fromisoformat(request.url.params["date>="])
        self.assertLessEqual(span.total_seconds(), 420)
        self.assertTrue(all(0 <= delay <= 1.1 for delay in delays))
        with self.assertRaises(ValueError):
            self.provider.inspect_live_session(9999, ACTIVE, list(range(1, 34)))
        with self.assertRaises(ValueError):
            self.provider.inspect_live_session(9999, ACTIVE, [0])

    def test_source_active_evidence_wins_over_scheduled_end(self):
        late = ACTIVE + timedelta(hours=3)
        self.data["race_control"].append(
            {
                "session_key": 9999,
                "date": "2025-03-16T06:50:00Z",
                "category": "SessionStatus",
                "message": "SESSION RESUMED",
            }
        )
        proof = self.provider.inspect_live_session(9999, late)
        self.assertTrue(proof.active)
        self.assertFalse(proof.settled)

    def test_auth_renewal_and_errors_are_bounded_and_safe(
        self,
    ):
        from app.providers.base import ProviderError

        self.provider.inspect_live_session(9999, ACTIVE)
        self.provider._token_expires = 0
        self.provider.inspect_live_session(9999, ACTIVE)
        self.assertEqual(
            sum(request.url.path == "/token" for request in self.requests), 2
        )
        real_get = self.provider.client.get
        with patch.object(
            self.provider.client,
            "get",
            side_effect=[
                httpx.Response(503),
                real_get(
                    "https://api.openf1.org/v1/sessions", params={"session_key": 9999}
                ),
            ],
        ) as get:
            self.provider._request("sessions", {"session_key": 9999}, live=True)
            self.assertEqual(get.call_count, 2)
        with patch.object(
            self.provider.client,
            "get",
            return_value=httpx.Response(401, json={"detail": "fixture-private"}),
        ) as get:
            with self.assertRaises(ProviderError) as error:
                self.provider._request("sessions", {}, live=True)
            self.assertEqual(get.call_count, 1)
            self.assertNotIn("fixture-private", str(error.exception))
        self.provider._token_expires = 0
        with patch.object(
            self.provider.client,
            "post",
            return_value=httpx.Response(403, json={"detail": "fixture-private"}),
        ) as post:
            with self.assertRaises(ProviderError) as error:
                self.provider._authorization()
            self.assertEqual(post.call_count, 1)
            self.assertNotIn("fixture-private", str(error.exception))

    def test_missing_results_keep_data_provisional_until_complete_handoff(self):
        from test_phase2 import payloads

        from app.providers.jolpica_normalization import normalize

        self.register()
        self.tick()
        data = payloads()
        data["results"], data["driverstandings"], data["constructorstandings"] = (
            [],
            [],
            [],
        )
        self.fixture.core.fetch.side_effect = lambda *args: normalize(data, 2025, 1)
        self.data["race_control"].append(
            {
                "session_key": 9999,
                "date": "2025-03-16T06:00:00Z",
                "category": "SessionStatus",
                "message": "SESSION ENDED",
            }
        )
        self.tick(ACTIVE + timedelta(days=1))
        job = self.fixture.job()
        self.assertEqual(job.data_status, "provisional")
        self.assertEqual(job.stage, "results")
        self.fixture.core.fetch.side_effect = lambda *args: normalize(
            payloads(), 2025, 1
        )
        self.tick(ACTIVE + timedelta(days=2))
        self.assertEqual(self.fixture.job().data_status, "finalized")

    def test_public_http_contracts_include_safe_updates_and_preserve_empty_states(self):
        from uuid import uuid4

        from app.api.core import database
        from app.main import app

        self.register()
        self.tick()
        with self.fixture.factory() as db:
            app.dependency_overrides[database] = lambda: db
            try:

                async def check():
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.get(
                            f"/v1/sessions/{self.fixture.session_id}/updates"
                        )
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.json()["data_status"], "provisional")
                        self.assertTrue(response.json()["live_active"])
                        self.assertNotIn("source_session", response.text)
                        self.assertNotIn("driver_ids", response.text)
                        self.assertNotIn("cursor", response.text)
                        for resource in ("laps", "telemetry", "stints", "weather"):
                            result = await client.get(
                                f"/v1/sessions/{self.fixture.session_id}/{resource}"
                            )
                            self.assertEqual(result.status_code, 200)
                        response = await client.get(f"/v1/sessions/{uuid4()}/updates")
                        self.assertEqual(response.status_code, 404)

                asyncio.run(check())
            finally:
                app.dependency_overrides.clear()


@unittest.skipUnless(
    os.environ.get("F1_TEST_POSTGRES") == "1", "Opt-in isolated PostgreSQL check"
)
class PostgresLiveTests(unittest.TestCase):
    def test_migration_consistency_and_independent_worker_connections(self):
        from uuid import uuid4

        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import text
        from sqlalchemy.schema import CreateSchema, DropSchema

        from app import models
        from app.db.session import get_engine
        from app.workers.sessions import worker_lock

        schema = "v2_test_" + uuid4().hex
        engine = get_engine().execution_options(schema_translate_map={None: schema})
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        try:
            with engine.begin() as connection:
                # Only this verified disposable schema; no application migration.
                connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                context = MigrationContext.configure(
                    connection, opts={"target_metadata": models.Base.metadata}
                )
                paths = sorted(
                    (Path(__file__).parents[1] / "migrations/versions").glob("*.py")
                )
                with Operations.context(context):
                    for path in paths:
                        spec = importlib.util.spec_from_file_location(path.stem, path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        module.upgrade()
                    self.assertEqual(
                        compare_metadata(context, models.Base.metadata), []
                    )
            with patch("app.workers.sessions.LOCK_KEY", uuid4().int % 2_000_000_000):
                with worker_lock(engine) as acquired:
                    self.assertTrue(acquired)
                    with worker_lock(engine) as second:
                        self.assertFalse(second)
                with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                    with worker_lock(engine) as acquired:
                        self.assertTrue(acquired)
                        raise RuntimeError("simulated crash")
                with worker_lock(engine) as recovered:
                    self.assertTrue(recovered)
        finally:
            with engine.begin() as connection:
                models.Base.metadata.drop_all(connection)
                connection.execute(DropSchema(schema))


if __name__ == "__main__":
    unittest.main()
