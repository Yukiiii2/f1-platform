"""Focused Phase 4 checks; no upstream network or application database writes."""

import asyncio
import copy
import importlib.util
import io
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def source_data():
    common = {"session_key": 9999, "meeting_key": 1234, "driver_number": 7}
    stamp = "2025-03-16T04:02:00.123456+00:00"
    return {
        "sessions": [
            {
                "session_key": 9999,
                "year": 2025,
                "session_name": "Race",
                "country_name": "Australia",
                "date_start": "2025-03-16T04:00:00Z",
                "date_end": "2025-03-16T06:00:00Z",
            }
        ],
        "drivers": [{**common, "name_acronym": "TST"}],
        "laps": [
            {
                **common,
                "lap_number": 1,
                "date_start": None,
                "lap_duration": 91.743,
                "duration_sector_1": 26.966,
                "duration_sector_2": None,
                "duration_sector_3": 26.12,
                "is_pit_out_lap": False,
                "segments_sector_1": [2049],
            }
        ],
        "car_data": [
            {
                **common,
                "date": stamp,
                "speed": 315,
                "throttle": 99,
                "brake": 100,
                "n_gear": 8,
                "rpm": 11141,
                "drs": 12,
            }
        ],
        "stints": [
            {
                **common,
                "stint_number": 1,
                "lap_start": 1,
                "lap_end": 20,
                "compound": "SOFT",
                "tyre_age_at_start": 3,
            }
        ],
        "pit": [
            {
                **common,
                "date": stamp,
                "lap_number": 20,
                "pit_duration": 22.215,
                "stop_duration": None,
            }
        ],
        "position": [{**common, "date": stamp, "position": 2}],
        "intervals": [
            {**common, "date": stamp, "gap_to_leader": "+1 LAP", "interval": 0.003}
        ],
        "race_control": [
            {
                "session_key": 9999,
                "date": stamp,
                "driver_number": None,
                "category": "Flag",
                "message": "YELLOW",
                "flag": "YELLOW",
                "scope": "Track",
                "lap_number": 2,
                "sector": 1,
            }
        ],
        "weather": [
            {
                "session_key": 9999,
                "date": stamp,
                "air_temperature": 27.8,
                "track_temperature": 52.5,
                "humidity": 58,
                "pressure": 1018.7,
                "rainfall": 0,
                "wind_direction": 136,
                "wind_speed": 2.4,
            }
        ],
    }


def provider(data=None, failures=0):
    from app.providers.openf1 import OpenF1Provider

    data = data or source_data()
    remaining = failures

    def respond(request):
        nonlocal remaining
        if remaining:
            remaining -= 1
            return httpx.Response(429, headers={"Retry-After": "0"})
        endpoint = request.url.path.rsplit("/", 1)[-1]
        if request.url.params.get("session_key") != "9999":
            return httpx.Response(400)
        rows = copy.deepcopy(data[endpoint])
        if "driver_number" in request.url.params:
            rows = [row for row in rows if row.get("driver_number") == 7]
        return httpx.Response(200, json=rows)

    return OpenF1Provider(
        client=httpx.Client(transport=httpx.MockTransport(respond)),
        sleep=lambda seconds: None,
    )


class Phase4Tests(unittest.TestCase):
    def setUp(self):
        try:
            from app.models.telemetry import Lap  # noqa: F401
            from app.providers.openf1 import OpenF1Provider  # noqa: F401
        except ImportError:
            self.fail("Phase 4 storage and provider are not implemented")
        from app import models

        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        models.Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        with self.factory.begin() as db:
            season = models.Season(year=2025)
            circuit = models.Circuit(name="Test", country="Australia")
            driver = models.Driver(given_name="Test", family_name="Driver", code="TST")
            db.add_all([season, circuit, driver])
            db.flush()
            weekend = models.Event(
                season_id=season.id,
                circuit_id=circuit.id,
                round=1,
                name="Test Grand Prix",
            )
            db.add(weekend)
            db.flush()
            session = models.Session(
                event_id=weekend.id,
                type="race",
                scheduled_date=datetime(2025, 3, 16).date(),
            )
            db.add(session)
            db.flush()
            self.session_id, self.driver_id = session.id, driver.id
        self.addCleanup(self.engine.dispose)

    def import_data(self, data=None):
        from app.ingestion.telemetry import run_telemetry_import

        return run_telemetry_import(
            provider(data), self.factory, self.session_id, 9999, {7: self.driver_id}
        )

    def test_normalized_channels_preserve_units_nulls_and_source_payload(self):
        bundle = provider(failures=1).fetch_session(9999, [7])
        records = {record.kind: record for record in bundle.records}
        self.assertEqual(str(records["lap"].attributes["duration_seconds"]), "91.743")
        self.assertIsNone(records["lap"].attributes["starts_at"])
        self.assertTrue(records["telemetry"].attributes["brake_applied"])
        self.assertEqual(records["telemetry"].source_payload["brake"], 100)
        self.assertEqual(records["telemetry"].attributes["drs_state"], 12)
        self.assertEqual(records["interval"].attributes["gap_to_leader_laps"], 1)
        self.assertIsNone(records["interval"].attributes["gap_to_leader_seconds"])
        self.assertEqual(
            str(records["pit"].attributes["lane_duration_seconds"]), "22.215"
        )

    def test_reimports_keep_ids_and_archive_source_corrections(self):
        from app.models.telemetry import Lap, TelemetrySourceRecord

        self.import_data()
        with self.factory() as db:
            lap_id = db.scalar(select(Lap.id))
        self.import_data()
        data = source_data()
        data["laps"][0]["lap_duration"] = 92.001
        self.import_data(data)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Lap)), 1)
            self.assertEqual(db.scalar(select(Lap.id)), lap_id)
            values = db.scalars(
                select(TelemetrySourceRecord).where(TelemetrySourceRecord.kind == "lap")
            ).all()
            self.assertEqual(
                sorted(row.payload["lap_duration"] for row in values), [91.743, 92.001]
            )

    def test_unavailable_pedal_104_is_null_and_raw_revisions_survive_reimports(self):
        from app.models.telemetry import TelemetrySample, TelemetrySourceRecord

        data = source_data()
        data["car_data"][0].update(brake=104, throttle=104)
        original = copy.deepcopy(data)
        self.import_data(data)
        self.import_data(data)
        with self.factory() as db:
            sample = db.scalar(select(TelemetrySample))
            sample_id = sample.id
            self.assertIsNone(sample.brake_applied)
            self.assertIsNone(sample.throttle_percent)
            self.assertEqual(sample.speed_kph, 315)
            raw = db.scalars(
                select(TelemetrySourceRecord).where(
                    TelemetrySourceRecord.kind == "telemetry"
                )
            ).all()
            self.assertEqual(len(raw), 1)
            self.assertEqual(raw[0].payload, original["car_data"][0])
        self.assertEqual(data, original)

        data["car_data"][0].update(brake=100, throttle=42)
        self.import_data(data)
        with self.factory() as db:
            sample = db.scalar(select(TelemetrySample))
            self.assertEqual(sample.id, sample_id)
            self.assertTrue(sample.brake_applied)
            self.assertEqual(sample.throttle_percent, 42)
            raw = db.scalars(
                select(TelemetrySourceRecord).where(
                    TelemetrySourceRecord.kind == "telemetry"
                )
            ).all()
            self.assertEqual(sorted(row.payload["brake"] for row in raw), [100, 104])

    def test_unavailable_pedal_marker_does_not_hide_known_or_invalid_other_fields(self):
        from app.providers.base import ProviderError

        for brake, throttle in ((104, 0), (0, 104), (100, 104)):
            data = source_data()
            data["car_data"][0].update(brake=brake, throttle=throttle)
            sample = next(
                record
                for record in provider(data).fetch_session(9999, [7]).records
                if record.kind == "telemetry"
            )
            self.assertEqual(
                sample.attributes["brake_applied"],
                None if brake == 104 else brake == 100,
            )
            self.assertEqual(
                sample.attributes["throttle_percent"],
                None if throttle == 104 else throttle,
            )
        for throttle in (-1, 101, 105):
            data = source_data()
            data["car_data"][0]["throttle"] = throttle
            with self.assertRaises(ValueError):
                self.import_data(data)
        data = source_data()
        data["weather"][0]["rainfall"] = 104
        with self.assertRaises(ProviderError):
            provider(data).fetch_session(9999, [7])

    def test_failed_import_is_atomic_and_observable(self):
        from app import models
        from app.models.telemetry import Lap, TelemetrySourceRecord

        data = source_data()
        data["weather"][0]["humidity"] = 101
        with self.assertRaises(ValueError):
            self.import_data(data)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Lap)), 0)
            self.assertEqual(
                db.scalar(select(func.count()).select_from(TelemetrySourceRecord)), 0
            )
            run = db.scalar(select(models.ImportRun))
            self.assertEqual(run.status, "failed")
            self.assertEqual(run.session_id, self.session_id)
            self.assertIsNotNone(run.finished_at)

    def test_explicit_identity_mappings_cannot_be_silently_reassigned(self):
        from app.ingestion.telemetry import run_telemetry_import

        self.import_data()
        with self.assertRaises(ValueError):
            run_telemetry_import(
                provider(), self.factory, self.session_id, 9999, {7: uuid4()}
            )
        data = source_data()
        data["sessions"][0]["session_name"] = "Qualifying"
        with self.assertRaises(ValueError):
            self.import_data(data)

    def test_schedule_fallback_matches_the_source_utc_date(self):
        from app.ingestion.telemetry import persist_session_bundle
        from app.models import Lap, Session

        data = source_data()
        data["sessions"][0]["date_start"] = "2025-03-16T20:00:00Z"
        data["sessions"][0]["date_end"] = "2025-03-16T22:00:00Z"
        bundle = provider(data).fetch_session(9999, [7])
        with self.factory.begin() as db:
            session = db.get(Session, self.session_id)
            session.scheduled_date = None
            # PostgreSQL can return this same instant in its connection timezone.
            session.starts_at = datetime(
                2025, 3, 17, 4, tzinfo=timezone(timedelta(hours=8))
            )
            persist_session_bundle(
                db, "openf1", self.session_id, 9999, {7: self.driver_id}, bundle
            )
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Lap)), 1)

    def test_provider_rejects_wrong_session_and_unsupported_brake(self):
        from app.providers.base import ProviderError

        for field, value in (("session_key", 123), ("brake", 42)):
            data = source_data()
            data["car_data"][0][field] = value
            with self.assertRaises(ProviderError):
                provider(data).fetch_session(9999, [7])

    def test_malformed_numeric_source_data_is_a_safe_provider_failure(self):
        from app.providers.base import ProviderError

        data = source_data()
        data["intervals"][0]["interval"] = "unavailable"
        with self.assertRaises(ProviderError):
            provider(data).fetch_session(9999, [7])

    def test_approximate_lap_timing_does_not_assign_samples(self):
        from app.models.telemetry import TelemetrySample

        data = source_data()
        data["laps"][0]["date_start"] = "2025-03-16T04:01:00Z"
        self.import_data(data)
        with self.factory() as db:
            row = db.scalar(select(TelemetrySample))
            self.assertIsNone(row.lap_id)
            self.assertEqual(row.timestamp.microsecond, 123456)

    def test_transaction_retry_rolls_back_before_reusing_the_bundle(self):
        from app.ingestion.telemetry import run_telemetry_import
        from app.models import ImportRun, Lap, TelemetrySourceRecord

        original_begin = self.factory.begin
        transactions = 0

        class SerializationFailure(Exception):
            sqlstate = "40001"

        @contextmanager
        def begin():
            nonlocal transactions
            transactions += 1
            with original_begin() as db:
                yield db
                if transactions == 2:
                    # Fail after all writes, before commit, to exercise full rollback.
                    raise DBAPIError(None, None, SerializationFailure())

        with (
            patch.object(self.factory, "begin", begin),
            patch("app.ingestion.telemetry.time.sleep", lambda seconds: None),
        ):
            run_id = run_telemetry_import(
                provider(), self.factory, self.session_id, 9999, {7: self.driver_id}
            )
        with self.factory() as db:
            self.assertEqual(db.get(ImportRun, run_id).attempt_count, 2)
            self.assertEqual(db.get(ImportRun, run_id).status, "succeeded")
            self.assertEqual(db.scalar(select(func.count()).select_from(Lap)), 1)
            self.assertEqual(
                db.scalar(select(func.count()).select_from(TelemetrySourceRecord)), 8
            )

    def test_lap_association_constraint_rejects_a_different_driver(self):
        from app.models import Driver, Lap, TelemetrySample

        self.import_data()
        with self.factory.begin() as db:
            other = Driver(given_name="Other", family_name="Driver")
            db.add(other)
            db.flush()
            other_id = other.id
        with self.assertRaises(IntegrityError):
            with self.factory.begin() as db:
                sample = db.scalar(select(TelemetrySample))
                sample.lap_id = db.scalar(select(Lap.id))
                sample.driver_id = other_id

    def test_empty_collections_and_retry_exhaustion_are_distinct(self):
        from app.providers.base import ProviderError
        from app.providers.openf1 import OpenF1Provider

        def no_pits(request):
            return httpx.Response(404, json={"detail": "No results found."})

        with httpx.Client(transport=httpx.MockTransport(no_pits)) as client:
            adapter = OpenF1Provider(client=client, sleep=lambda seconds: None)
            self.assertEqual(adapter._request("pit", {}, allow_empty=True), [])
            with self.assertRaises(ProviderError):
                adapter._request("sessions", {})
        with self.assertRaises(ProviderError):
            provider(failures=3).fetch_session(9999, [7])

    def test_zero_states_and_lap_gaps_are_not_missing_or_time_gaps(self):
        data = source_data()
        data["car_data"][0].update(brake=0, throttle=0, speed=0, n_gear=0)
        data["intervals"][0].update(gap_to_leader=None, interval="+2 LAPS")
        records = {
            record.kind: record
            for record in provider(data).fetch_session(9999, [7]).records
        }
        self.assertFalse(records["telemetry"].attributes["brake_applied"])
        self.assertEqual(records["telemetry"].attributes["throttle_percent"], 0)
        self.assertIsNone(records["interval"].attributes["gap_to_leader_seconds"])
        self.assertEqual(records["interval"].attributes["interval_laps"], 2)
        self.assertIsNone(records["interval"].attributes["interval_seconds"])

    def test_tyre_age_has_explicit_completed_lap_boundaries(self):
        from app.telemetry.tyres import tyre_age

        self.assertEqual(tyre_age(3, 4, 20, 3), (0, 3))
        self.assertEqual(tyre_age(3, 4, 20, 4), (1, 4))
        self.assertEqual(tyre_age(3, 4, 20, 13), (10, 13))
        self.assertEqual(tyre_age(None, 4, 20, 13), (10, None))
        self.assertEqual(tyre_age(3, 4, 20, 21), (17, 20))
        with self.assertRaises(ValueError):
            tyre_age(3, 4, 20, 2)

    def test_read_apis_return_domain_data_with_filters_and_empty_states(self):
        from sqlalchemy.orm.attributes import set_committed_value

        from app import models
        from app.api.core import database
        from app.main import app

        self.import_data()
        db = self.factory()
        held = []
        for mapper in models.Base.registry.mappers:
            for row in db.scalars(select(mapper.class_)):
                for column in mapper.columns:
                    value = getattr(row, column.key)
                    if isinstance(value, datetime) and value.tzinfo is None:
                        set_committed_value(
                            row, column.key, value.replace(tzinfo=timezone.utc)
                        )
                held.append(row)
        app.dependency_overrides[database] = lambda: db

        async def requests():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                for path in (
                    "laps",
                    "telemetry",
                    "stints",
                    "pits",
                    "positions",
                    "intervals",
                    "race-control",
                    "weather",
                ):
                    response = await client.get(
                        f"/v1/sessions/{self.session_id}/{path}"
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    rows = response.json()
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["session_id"], str(self.session_id))
                    self.assertNotIn("session_key", rows[0])
                    self.assertNotIn("source_payload", rows[0])
                laps = (await client.get(f"/v1/sessions/{self.session_id}/laps")).json()
                response = await client.get(f"/v1/laps/{laps[0]['id']}/telemetry")
                self.assertEqual(response.json(), [])
                response = await client.get(
                    f"/v1/sessions/{self.session_id}/telemetry",
                    params={"driver_id": str(uuid4())},
                )
                self.assertEqual(response.json(), [])
                response = await client.get(f"/v1/sessions/{uuid4()}/laps")
                self.assertEqual(response.status_code, 404)
                response = await client.get(
                    f"/v1/sessions/{self.session_id}/laps?limit=201"
                )
                self.assertEqual(response.status_code, 422)
                sample_path = f"/v1/sessions/{self.session_id}/telemetry"
                response = await client.get(
                    sample_path,
                    params={
                        "from_time": "2025-03-16T04:02:00.123456Z",
                        "to_time": "2025-03-16T04:03:00Z",
                    },
                )
                self.assertEqual(len(response.json()), 1)
                response = await client.get(
                    sample_path,
                    params={
                        "to_time": "2025-03-16T04:02:00.123456Z",
                    },
                )
                self.assertEqual(response.json(), [])
                response = await client.get(
                    sample_path,
                    params={
                        "from_time": "2025-03-16T04:02:00",
                    },
                )
                self.assertEqual(response.status_code, 422)
                stints = (
                    await client.get(f"/v1/sessions/{self.session_id}/stints")
                ).json()
                response = await client.get(
                    f"/v1/stints/{stints[0]['id']}/tyre-age?completed_lap=10"
                )
                self.assertEqual(response.json()["total_tyre_age"], 13)
                self.assertEqual(response.json()["classification"], "derived")
                self.assertEqual(response.json()["tyre_age_at_start"], 3)

        try:
            asyncio.run(requests())
        finally:
            app.dependency_overrides.clear()
            db.close()

    def test_migration_matches_models_and_compiles_for_postgresql(self):
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        from app.models import Base

        modules = []
        for filename in (
            "0001_core_domain.py",
            "0002_core_ingestion.py",
            "0003_telemetry_pipeline.py",
            "0004_session_updates.py",
            "0005_pitwall_protection.py",
            "0006_telemetry_observation_order.py",
        ):
            path = Path(__file__).parents[1] / "migrations/versions" / filename
            spec = importlib.util.spec_from_file_location(filename, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            modules.append(module)
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                context = MigrationContext.configure(
                    connection, opts={"target_metadata": Base.metadata}
                )
                with Operations.context(context):
                    for module in modules:
                        module.upgrade()
                    self.assertEqual(compare_metadata(context, Base.metadata), [])
                    for module in reversed(modules[2:]):
                        module.downgrade()
            output = io.StringIO()
            context = MigrationContext.configure(
                dialect_name="postgresql",
                opts={"as_sql": True, "output_buffer": output},
            )
            with Operations.context(context):
                modules[2].upgrade()
            self.assertIn("TIMESTAMP WITH TIME ZONE", output.getvalue())
            self.assertEqual(output.getvalue().count("CREATE TABLE "), 10)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
