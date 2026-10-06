"""Post-session finalization checks using real services and isolated SQLite."""

import importlib.util
import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock

import httpx
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.pool import StaticPool
from test_phase2 import payloads
from test_phase4 import source_data

NOW = datetime(2025, 3, 17, tzinfo=timezone.utc)


class Phase11Tests(unittest.TestCase):
    def setUp(self):
        from app import models
        from app.ingestion.service import persist_bundle
        from app.providers.jolpica_normalization import normalize

        self.models = models
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        models.Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)

        @event.listens_for(self.factory, "loaded_as_persistent")
        def aware_fixtures(db, row):
            # Match PostgreSQL's aware datetimes; SQLite discards timezone metadata.
            for column in row.__mapper__.columns:
                value = getattr(row, column.key)
                if isinstance(value, datetime) and value.tzinfo is None:
                    set_committed_value(
                        row, column.key, value.replace(tzinfo=timezone.utc)
                    )

        data = payloads()
        data["results"] = []
        data["driverstandings"] = []
        data["constructorstandings"] = []
        with self.factory.begin() as db:
            persist_bundle(db, "jolpica", normalize(data, 2025, 1))
            self.session_id = db.scalar(
                select(models.Session.id).where(models.Session.type == "race")
            )
            self.driver_id = db.scalar(
                select(models.Driver.id).where(models.Driver.code == "TST")
            )
        self.core = Mock(name="core")
        self.core.name = "jolpica"
        self.core.fetch.side_effect = lambda *args: normalize(payloads(), 2025, 1)
        self.data = source_data()
        self.openf1 = self.provider()

    def provider(self):
        from app.providers.openf1 import OpenF1Provider

        def respond(request):
            collection = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, json=self.data[collection])

        client = httpx.Client(transport=httpx.MockTransport(respond))
        self.addCleanup(client.close)
        return OpenF1Provider(client=client, sleep=lambda _: None)

    def register(self):
        from app.workers.sessions import register_session

        return register_session(
            self.factory, self.session_id, 9999, {7: self.driver_id}, now=NOW
        )

    def tick(self, now=NOW, invalidate=None):
        from app.workers.sessions import run_once

        return run_once(
            self.factory, self.core, self.openf1, now=now, invalidate=invalidate
        )

    def job(self):
        from app.models.updates import SessionUpdateJob

        with self.factory() as db:
            return db.scalar(select(SessionUpdateJob))

    def test_registration_is_explicit_idempotent_and_rejects_changed_scope(self):
        from app.workers.sessions import register_session

        identifier = self.register()
        self.assertEqual(self.register(), identifier)
        with self.assertRaises(ValueError):
            register_session(
                self.factory, self.session_id, 10000, {7: self.driver_id}, now=NOW
            )
        with self.assertRaises(ValueError):
            register_session(
                self.factory, self.session_id, 9999, {0: self.driver_id}, now=NOW
            )

    def test_elapsed_schedule_alone_does_not_confirm_completion(self):
        from app.providers.jolpica_normalization import normalize

        data = payloads()
        data["results"] = []
        self.core.fetch.side_effect = lambda *args: normalize(data, 2025, 1)
        self.register()
        self.tick()
        self.assertEqual(self.job().status, "pending")
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(self.models.Lap)), 0
            )
        self.core.fetch.reset_mock()
        self.tick(now=NOW + timedelta(minutes=10))
        self.core.fetch.assert_not_called()

    def test_finalization_reuses_imports_calculations_and_fresh_read_contracts(self):
        self.register()
        invalidate = Mock(return_value={"mode": "not_cached"})
        self.tick(invalidate=invalidate)
        job = self.job()
        self.assertEqual(job.status, "succeeded")
        self.assertEqual(job.completion_evidence["kind"], "published_results")
        self.assertEqual(job.row_counts["lap"], 1)
        self.assertEqual(job.row_counts["weather"], 1)
        self.assertEqual(
            job.derived_summary["drivers"][0]["stints"][0]["total_tyre_age"], 23
        )
        self.assertEqual(job.cache_state, {"mode": "not_cached"})
        scope = invalidate.call_args.args[0]
        self.assertEqual(scope["session_id"], str(self.session_id))
        self.assertIn(str(self.driver_id), scope["driver_ids"])
        with self.factory() as db:
            self.assertEqual(
                db.get(self.models.Session, self.session_id).status, "completed"
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(self.models.DriverStanding)),
                1,
            )
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(self.models.TelemetrySourceRecord)
                ),
                8,
            )
        self.core.fetch.reset_mock()
        self.tick(now=NOW + timedelta(days=1))
        self.core.fetch.assert_not_called()

    def test_failures_are_bounded_sanitized_and_can_be_retried_manually(self):
        from app.providers.base import ProviderError
        from app.workers.sessions import retry_session

        self.register()
        self.core.fetch.side_effect = ProviderError("private credentials/prompt")
        for hour in [0, 2, 4]:
            self.tick(now=NOW + timedelta(hours=hour))
        job = self.job()
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.attempt_count, 3)
        self.assertNotIn("private", job.failure_details)
        self.tick(now=NOW + timedelta(days=1))
        self.assertEqual(self.core.fetch.call_count, 3)
        retry_session(self.factory, self.session_id, now=NOW + timedelta(days=1))
        self.assertEqual(self.job().status, "pending")
        self.assertEqual(self.job().consecutive_failures, 0)

    def test_interrupted_finalization_and_invalidation_retry_are_idempotent(self):
        from app.models.updates import SessionUpdateJob

        self.register()
        with self.factory.begin() as db:
            job = db.scalar(select(SessionUpdateJob))
            job.status, job.stage = "running", "telemetry"
        fail = Mock(side_effect=RuntimeError("private cache URL"))
        self.tick(invalidate=fail)
        self.assertEqual(self.job().status, "retry")
        with self.factory() as db:
            revisions = db.scalar(
                select(func.count()).select_from(self.models.TelemetrySourceRecord)
            )
        self.tick(now=NOW + timedelta(hours=1))
        self.assertEqual(self.job().status, "succeeded")
        with self.factory() as db:
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(self.models.TelemetrySourceRecord)
                ),
                revisions,
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(self.models.Lap)), 1
            )

    def test_cancelled_source_and_wrong_source_mapping_are_not_finalized(self):
        self.register()
        common = {"session_key": 9999, "date": "2025-03-16T06:00:00Z"}
        self.data["race_control"] = [
            {**common, "category": "SessionStatus", "message": "SESSION CANCELLED"}
        ]
        self.tick()
        self.assertEqual(self.job().status, "cancelled")
        self.core.fetch.reset_mock()
        self.tick(now=NOW + timedelta(hours=1))
        self.core.fetch.assert_not_called()
        from app.workers.sessions import retry_session

        retry_session(self.factory, self.session_id, now=NOW + timedelta(hours=1))
        self.data["race_control"] = []
        self.data["sessions"][0]["country_name"] = "France"
        self.tick(now=NOW + timedelta(hours=1))
        self.assertEqual(self.job().status, "retry")
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(self.models.Lap)), 0
            )

    def test_far_future_session_does_not_poll_providers(self):
        self.register()
        with self.factory.begin() as db:
            db.get(self.models.Session, self.session_id).starts_at = NOW + timedelta(
                days=10
            )
        self.tick()
        self.core.fetch.assert_not_called()
        self.assertEqual(self.job().status, "pending")
        with self.assertRaises(ValueError):
            from app.workers.sessions import run_once

            run_once(self.factory, self.core, self.openf1, now=NOW, interval=10)

    def test_two_sessions_share_core_refresh_and_practice_never_invents_results(self):
        from app.providers.openf1 import OpenF1Provider
        from app.workers.sessions import register_session

        self.register()
        practice = json.loads(
            json.dumps(source_data())
            .replace("9999", "9998")
            .replace("2025-03-16", "2025-03-14")
        )
        practice["sessions"][0]["session_name"] = "Practice 1"
        practice["race_control"].append(
            {
                "session_key": 9998,
                "date": "2025-03-14T06:00:00Z",
                "flag": "CHEQUERED",
                "scope": "Track",
                "message": "CHEQUERED FLAG",
            }
        )
        with self.factory() as db:
            session_id = db.scalar(
                select(self.models.Session.id).where(
                    self.models.Session.type == "practice_1"
                )
            )
        register_session(self.factory, session_id, 9998, {7: self.driver_id}, now=NOW)
        datasets = {9999: self.data, 9998: practice}

        def respond(request):
            collection = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200, json=datasets[int(request.url.params["session_key"])][collection]
            )

        client = httpx.Client(transport=httpx.MockTransport(respond))
        self.addCleanup(client.close)
        self.openf1 = OpenF1Provider(client=client, sleep=lambda _: None)
        self.tick()
        self.assertEqual(self.core.fetch.call_count, 1)
        with self.factory() as db:
            self.assertEqual(
                list(db.scalars(select(self.models.SessionUpdateJob.status))),
                ["succeeded", "succeeded"],
            )
            self.assertEqual(
                db.scalar(
                    select(func.count())
                    .select_from(self.models.Result)
                    .where(self.models.Result.session_id == session_id)
                ),
                0,
            )

    def test_missing_channels_remain_empty_and_job_exposes_zero_counts(self):
        self.register()
        self.data["car_data"] = []
        self.tick()
        self.assertEqual(self.job().status, "succeeded")
        self.assertEqual(self.job().row_counts["telemetry"], 0)
        with self.factory() as db:
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(self.models.TelemetrySample)
                ),
                0,
            )

    def test_postgresql_worker_lock_defers_second_worker_and_releases_on_error(self):
        from app.workers.sessions import worker_lock

        engine = MagicMock()
        engine.dialect.name = "postgresql"
        connection = engine.connect.return_value.__enter__.return_value
        connection.scalar.return_value = False
        with worker_lock(engine) as acquired:
            self.assertFalse(acquired)
        connection.execute.assert_not_called()
        connection.scalar.return_value = True
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            with worker_lock(engine) as acquired:
                self.assertTrue(acquired)
                raise RuntimeError("interrupted")
        self.assertIn("pg_advisory_unlock", str(connection.execute.call_args.args[0]))

    def test_source_completion_requires_settling_and_final_qualifying_signal(self):
        common = {"session_key": 9999, "date": "2025-03-16T06:00:00Z"}
        self.data["sessions"][0]["session_name"] = "Qualifying"
        self.data["race_control"] = [
            {**common, "flag": "CHEQUERED", "scope": "Track", "qualifying_phase": 1}
        ]
        self.assertFalse(self.openf1.inspect_session(9999, NOW).completed)
        self.data["race_control"][0]["qualifying_phase"] = 3
        self.assertTrue(self.openf1.inspect_session(9999, NOW).completed)
        recent = datetime(2025, 3, 16, 6, 5, tzinfo=timezone.utc)
        self.assertFalse(self.openf1.inspect_session(9999, recent).settled)

    def test_early_session_end_and_later_resumption_do_not_confirm_completion(self):
        common = {"session_key": 9999, "category": "SessionStatus"}
        self.data["sessions"][0]["session_name"] = "Qualifying"
        self.data["race_control"] = [
            {
                **common,
                "date": "2025-03-16T05:00:00Z",
                "message": "SESSION ENDED",
                "qualifying_phase": 1,
            }
        ]
        self.assertFalse(self.openf1.inspect_session(9999, NOW).completed)

        self.data["sessions"][0]["session_name"] = "Race"
        self.data["race_control"] = [
            {**common, "date": "2025-03-16T06:00:00Z", "message": "SESSION ENDED"},
            {**common, "date": "2025-03-16T06:05:00Z", "message": "SESSION STARTED"},
        ]
        self.assertFalse(self.openf1.inspect_session(9999, NOW).completed)
        self.data["race_control"][1]["message"] = "SESSION RESUMED"
        self.assertFalse(self.openf1.inspect_session(9999, NOW).completed)

    def test_metadata_cancellation_is_explicit_even_without_dates_or_messages(self):
        from app.providers.base import ProviderError

        self.register()
        metadata = self.data["sessions"][0]
        metadata.update(is_cancelled=True, date_start=None, date_end=None)
        self.data["race_control"] = []
        self.assertTrue(self.openf1.inspect_session(9999, NOW).cancelled)
        self.tick()
        self.assertEqual(self.job().status, "cancelled")
        metadata["is_cancelled"] = "false"
        with self.assertRaises(ProviderError):
            self.openf1.inspect_session(9999, NOW)

    def test_late_results_and_standings_are_imported_before_job_finishes(self):
        from app.providers.jolpica_normalization import normalize

        self.register()
        early = payloads()
        early["results"] = []
        early["driverstandings"] = []
        early["constructorstandings"] = []
        self.core.fetch.side_effect = lambda *args: normalize(early, 2025, 1)
        self.data["race_control"].append(
            {
                "session_key": 9999,
                "date": "2025-03-16T06:00:00Z",
                "flag": "CHEQUERED",
                "scope": "Track",
                "message": "CHEQUERED FLAG",
            }
        )
        self.tick()
        self.assertEqual(self.job().status, "pending")
        self.assertEqual(self.job().stage, "results")
        with self.factory() as db:
            runs = db.scalar(
                select(func.count())
                .select_from(self.models.ImportRun)
                .where(self.models.ImportRun.provider == "openf1")
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(self.models.Lap)), 1
            )
        self.tick(now=NOW + timedelta(hours=1))
        with self.factory() as db:
            self.assertEqual(
                db.scalar(
                    select(func.count())
                    .select_from(self.models.ImportRun)
                    .where(self.models.ImportRun.provider == "openf1")
                ),
                runs,
            )
        classified = payloads()
        classified["driverstandings"] = []
        classified["constructorstandings"] = []
        self.core.fetch.side_effect = lambda *args: normalize(classified, 2025, 1)
        self.tick(now=NOW + timedelta(hours=2))
        self.assertEqual(self.job().status, "pending")
        self.core.fetch.side_effect = lambda *args: normalize(payloads(), 2025, 1)
        self.tick(now=NOW + timedelta(hours=3))
        self.assertEqual(self.job().status, "succeeded")
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(self.models.Result)), 2
            )

    def test_source_completion_rejects_foreign_session_rows_and_naive_clock(self):
        from app.providers.base import ProviderError

        self.data["race_control"][0]["session_key"] = 10000
        with self.assertRaises(ProviderError):
            self.openf1.inspect_session(9999, NOW)
        with self.assertRaises(ValueError):
            self.openf1.inspect_session(9999, NOW.replace(tzinfo=None))

    def test_migration_matches_models_and_supports_postgresql(self):
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        modules = []
        self.assertTrue(
            (
                Path(__file__).parents[1]
                / "migrations/versions/0004_session_updates.py"
            ).exists()
        )
        for path in sorted(
            (Path(__file__).parents[1] / "migrations/versions").glob("*.py")
        ):
            spec = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            modules.append(module)
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                context = MigrationContext.configure(connection)
                with Operations.context(context):
                    for module in modules:
                        module.upgrade()
                    self.assertEqual(
                        compare_metadata(context, self.models.Base.metadata), []
                    )
                    modules[-1].downgrade()
            output = io.StringIO()
            context = MigrationContext.configure(
                dialect_name="postgresql",
                opts={"as_sql": True, "output_buffer": output},
            )
            with Operations.context(context):
                modules[-1].upgrade()
            self.assertIn("TIMESTAMP WITH TIME ZONE", output.getvalue())
            self.assertIn("uq_session_update_session", output.getvalue())
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
