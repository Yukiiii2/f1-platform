"""Replay uses normalized recorded order, never synthetic track coordinates."""

import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import test_phase4
from sqlalchemy import event, func, select
from sqlalchemy.orm.attributes import set_committed_value

START = datetime(2025, 3, 16, 4, tzinfo=timezone.utc)


class ReplayTests(unittest.TestCase):
    def setUp(self):
        test_phase4.Phase4Tests.setUp(self)

        @event.listens_for(self.factory, "loaded_as_persistent")
        def aware(db, row):
            for column in row.__mapper__.columns:
                value = getattr(row, column.key)
                if isinstance(value, datetime) and value.tzinfo is None:
                    set_committed_value(
                        row, column.key, value.replace(tzinfo=timezone.utc)
                    )

    def seed(self, times=(0, 10, 20), provisional=False):
        from app import models

        with self.factory.begin() as db:
            session = db.get(models.Session, self.session_id)
            session.starts_at, session.ends_at, session.status = (
                START,
                START + timedelta(seconds=max(times)),
                "completed",
            )
            other = models.Driver(given_name="Other", family_name="Driver", code="OTH")
            db.add(other)
            db.flush()
            self.other_id = other.id
            for index, driver_id in enumerate((self.driver_id, self.other_id)):
                db.add(
                    models.SessionDriverIdentity(
                        provider="openf1",
                        session_id=session.id,
                        driver_id=driver_id,
                        driver_number=index + 1,
                    )
                )
                for offset in times:
                    source = models.TelemetrySourceRecord(
                        provider="openf1",
                        session_id=session.id,
                        kind="position",
                        source_key=str(uuid4()),
                        checksum=uuid4().hex,
                        payload={"position": index + 1},
                        fetched_at=START,
                    )
                    db.add(source)
                    db.flush()
                    db.add(
                        models.PositionSample(
                            provider="openf1",
                            session_id=session.id,
                            driver_id=driver_id,
                            source_key=source.source_key,
                            source_record_id=source.id,
                            timestamp=START + timedelta(seconds=offset),
                            position=index + 1,
                        )
                    )
            if provisional:
                db.add(
                    models.SessionUpdateJob(
                        session_id=session.id,
                        source_session=100,
                        driver_ids={},
                        next_attempt_at=START,
                        data_status="provisional",
                        live_enabled=True,
                        live_active=True,
                    )
                )
                session.status = "in_progress"

    def test_results_only_never_enable_replay(self):
        from app import models
        from app.services.replay import session_replay

        with self.factory.begin() as db:
            team = models.Team(name="Recorded team")
            db.add(team)
            db.flush()
            db.add(
                models.Result(
                    session_id=self.session_id,
                    driver_id=self.driver_id,
                    team_id=team.id,
                    position=1,
                    completed_laps=57,
                )
            )
            db.get(
                models.Season,
                db.get(
                    models.Event, db.get(models.Session, self.session_id).event_id
                ).season_id,
            ).year = 2010
        with self.factory() as db:
            payload = session_replay(db, self.session_id)
            self.assertEqual(payload.capability, "unavailable")
            self.assertEqual(payload.drivers, [])
            self.assertIsNone(payload.starts_at)
            self.assertEqual(payload.season, 2010)

    def test_two_drivers_source_order_payload_and_identity(self):
        from app import models
        from app.services.replay import session_replay

        self.seed()
        with self.factory() as db:
            before = db.scalar(
                select(func.count()).select_from(models.TelemetrySourceRecord)
            )
            payload = session_replay(db, self.session_id)
            self.assertEqual(payload.capability, "available")
            self.assertEqual(payload.mode, "timing_order")
            self.assertEqual(
                {d.driver.id for d in payload.drivers}, {self.driver_id, self.other_id}
            )
            self.assertEqual(payload.duration_seconds, 20)
            self.assertEqual(payload.drivers[0].positions[0].elapsed_seconds, 0)
            self.assertEqual(payload.quality.interpolation, "previous_sample_hold")
            self.assertEqual(payload.quality.max_hold_seconds, 30)
            self.assertFalse(payload.quality.coordinates_available)
            self.assertNotIn("source_key", payload.model_dump_json())
            self.assertEqual(
                before,
                db.scalar(
                    select(func.count()).select_from(models.TelemetrySourceRecord)
                ),
            )

    def test_gap_and_provisional_quality_remain_explicit(self):
        from app.services.replay import session_replay

        self.seed(times=(0, 10, 90), provisional=True)
        with self.factory() as db:
            payload = session_replay(db, self.session_id)
            self.assertEqual(payload.capability, "partial")
            self.assertTrue(payload.provisional)
            self.assertTrue(payload.quality.gaps_present)
            self.assertTrue(
                any("provisional" in note.lower() for note in payload.quality.notes)
            )

    def test_late_driver_does_not_disable_supported_pair(self):
        from app import models
        from app.services.replay import session_replay

        self.seed()
        with self.factory.begin() as db:
            late = models.Driver(given_name="Late", family_name="Coverage")
            db.add(late)
            db.flush()
            for offset in (80, 90):
                source = models.TelemetrySourceRecord(
                    provider="openf1",
                    session_id=self.session_id,
                    kind="position",
                    source_key=str(uuid4()),
                    checksum=uuid4().hex,
                    payload={},
                    fetched_at=START,
                )
                db.add(source)
                db.flush()
                db.add(
                    models.PositionSample(
                        provider="openf1",
                        session_id=self.session_id,
                        driver_id=late.id,
                        source_key=source.source_key,
                        source_record_id=source.id,
                        timestamp=START + timedelta(seconds=offset),
                        position=3,
                    )
                )
        with self.factory() as db:
            payload = session_replay(db, self.session_id)
            self.assertEqual(payload.capability, "partial")
            self.assertEqual(len(payload.drivers), 3)
            self.assertTrue(payload.quality.gaps_present)

    def test_unsupported_session_type(self):
        from app import models
        from app.services.replay import session_replay

        self.seed()
        with self.factory.begin() as db:
            db.get(models.Session, self.session_id).type = "practice_1"
        with self.factory() as db:
            self.assertEqual(
                session_replay(db, self.session_id).capability, "unavailable"
            )

    def test_envelope_overlap_without_usable_samples_is_unavailable(self):
        from app import models
        from app.services.replay import session_replay

        self.seed(times=(0, 100))
        with self.factory.begin() as db:
            rows = list(
                db.scalars(
                    select(models.PositionSample)
                    .where(models.PositionSample.driver_id == self.other_id)
                    .order_by(models.PositionSample.timestamp)
                )
            )
            rows[0].timestamp = START + timedelta(seconds=40)
            rows[1].timestamp = START + timedelta(seconds=60)
        with self.factory() as db:
            self.assertEqual(
                session_replay(db, self.session_id).capability, "unavailable"
            )

    def test_leading_missing_samples_are_partial_even_inside_hold_limit(self):
        from app import models
        from app.services.replay import session_replay

        self.seed()
        with self.factory.begin() as db:
            first = db.scalar(
                select(models.PositionSample)
                .where(models.PositionSample.driver_id == self.other_id)
                .order_by(models.PositionSample.timestamp)
            )
            db.delete(first)
        with self.factory() as db:
            payload = session_replay(db, self.session_id)
            self.assertEqual(payload.capability, "partial")
            self.assertTrue(payload.quality.gaps_present)

    def test_exact_hold_boundary_matches_playback_capability(self):
        from app import models
        from app.services.replay import session_replay

        self.seed(times=(0, 100))
        with self.factory.begin() as db:
            rows = list(
                db.scalars(
                    select(models.PositionSample)
                    .where(models.PositionSample.driver_id == self.other_id)
                    .order_by(models.PositionSample.timestamp)
                )
            )
            rows[0].timestamp = START + timedelta(seconds=30)
            rows[1].timestamp = START + timedelta(seconds=130)
        with self.factory() as db:
            self.assertEqual(session_replay(db, self.session_id).capability, "partial")

    def test_provider_coverage_cannot_be_combined_to_invent_multi_car_replay(self):
        from app import models
        from app.services.replay import session_replay

        self.seed()
        with self.factory.begin() as db:
            # Remove the second driver's normalized rows without touching raw revisions.
            for row in db.scalars(
                select(models.PositionSample).where(
                    models.PositionSample.driver_id == self.other_id
                )
            ):
                db.delete(row)
        with self.factory() as db:
            self.assertEqual(
                session_replay(db, self.session_id).capability, "unavailable"
            )

    def test_recorded_context_and_missing_grid_are_explicit(self):
        from app import models
        from app.services.replay import session_replay

        self.seed()
        with self.factory.begin() as db:

            def source(kind):
                row = models.TelemetrySourceRecord(
                    provider="openf1",
                    session_id=self.session_id,
                    kind=kind,
                    source_key=str(uuid4()),
                    checksum=uuid4().hex,
                    payload={},
                    fetched_at=START,
                )
                db.add(row)
                db.flush()
                return dict(
                    provider="openf1",
                    session_id=self.session_id,
                    source_key=row.source_key,
                    source_record_id=row.id,
                )

            team = models.Team(name="Recorded team")
            missing = models.Driver(given_name="Missing", family_name="Coverage")
            db.add_all([team, missing])
            db.flush()
            db.add_all(
                [
                    models.Result(
                        session_id=self.session_id,
                        driver_id=self.driver_id,
                        team_id=team.id,
                        position=1,
                    ),
                    models.Result(
                        session_id=self.session_id,
                        driver_id=missing.id,
                        team_id=team.id,
                        position=3,
                    ),
                    models.Lap(
                        **source("laps"),
                        driver_id=self.driver_id,
                        lap_number=1,
                        starts_at=START,
                        duration_seconds=15,
                        start_time_is_approximate=True,
                    ),
                    models.PitStop(
                        **source("pit"),
                        driver_id=self.driver_id,
                        timestamp=START + timedelta(seconds=5),
                        lane_duration_seconds=None,
                        lap_number=1,
                    ),
                    models.IntervalSample(
                        **source("intervals"),
                        driver_id=self.driver_id,
                        timestamp=START + timedelta(seconds=5),
                        gap_to_leader_seconds=1.25,
                    ),
                    models.RaceControlMessage(
                        **source("race_control"),
                        timestamp=START + timedelta(seconds=5),
                        message="VSC DEPLOYED",
                        category="SafetyCar",
                        flag=None,
                    ),
                ]
            )
        with self.factory() as db:
            payload = session_replay(db, self.session_id)
            self.assertEqual(payload.capability, "partial")
            self.assertEqual(payload.quality.omitted_driver_count, 1)
            driver = next(d for d in payload.drivers if d.driver.id == self.driver_id)
            self.assertEqual(driver.team.name, "Recorded team")
            self.assertTrue(driver.laps[0].approximate)
            self.assertEqual(driver.laps[0].end_seconds, 15)
            self.assertIsNone(driver.pits[0].lane_duration_seconds)
            self.assertEqual(float(driver.intervals[0].gap_to_leader_seconds), 1.25)
            self.assertEqual(payload.race_control[0].message, "VSC DEPLOYED")
            self.assertIsNone(driver.inactive_state)

    def test_driver_bound_and_omissions_are_not_double_counted(self):
        from app import models
        from app.services.replay import session_replay

        self.seed()
        with self.factory.begin() as db:
            for index in range(32):
                driver = models.Driver(given_name=f"Grid {index}", family_name="Driver")
                db.add(driver)
                db.flush()
                db.add(
                    models.SessionDriverIdentity(
                        provider="openf1",
                        session_id=self.session_id,
                        driver_id=driver.id,
                        driver_number=index + 10,
                    )
                )
                for offset in (0, 10, 20):
                    source = models.TelemetrySourceRecord(
                        provider="openf1",
                        session_id=self.session_id,
                        kind="position",
                        source_key=str(uuid4()),
                        checksum=uuid4().hex,
                        payload={},
                        fetched_at=START,
                    )
                    db.add(source)
                    db.flush()
                    db.add(
                        models.PositionSample(
                            provider="openf1",
                            session_id=self.session_id,
                            driver_id=driver.id,
                            source_key=source.source_key,
                            source_record_id=source.id,
                            timestamp=START + timedelta(seconds=offset),
                            position=index + 3,
                        )
                    )
        with self.factory() as db:
            payload = session_replay(db, self.session_id)
            self.assertEqual(len(payload.drivers), 32)
            self.assertEqual(payload.quality.omitted_driver_count, 2)
            self.assertEqual(payload.capability, "partial")

    def test_sampling_is_bounded_keeps_source_timestamps_and_endpoints(self):
        from app.services.replay import session_replay

        self.seed(times=range(1000))
        with self.factory() as db:
            payload = session_replay(db, self.session_id, max_samples=32)
            for driver in payload.drivers:
                self.assertLessEqual(len(driver.positions), 32)
                self.assertEqual(driver.positions[0].elapsed_seconds, 0)
                self.assertEqual(driver.positions[-1].elapsed_seconds, 999)
                self.assertTrue(
                    all(
                        p.timestamp == START + timedelta(seconds=p.elapsed_seconds)
                        for p in driver.positions
                    )
                )
            self.assertTrue(payload.quality.downsampled)

    def test_replay_http_contract_bounds_and_unknown_session(self):
        from app.api.core import database
        from app.main import app

        self.seed()
        with self.factory() as db:
            app.dependency_overrides[database] = lambda: db

            async def check():
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    result = await client.get(f"/v1/sessions/{self.session_id}/replay")
                    self.assertEqual(result.status_code, 200)
                    self.assertEqual(result.json()["capability"], "available")
                    invalid = await client.get(
                        f"/v1/sessions/{self.session_id}/replay?max_samples=100000"
                    )
                    self.assertEqual(invalid.status_code, 422)
                    unknown = await client.get(f"/v1/sessions/{uuid4()}/replay")
                    self.assertEqual(unknown.status_code, 404)

            try:
                asyncio.run(check())
            finally:
                app.dependency_overrides.clear()


@unittest.skipUnless(
    os.environ.get("F1_TEST_POSTGRES") == "1", "Opt-in isolated PostgreSQL check"
)
class PostgresReplayTests(unittest.TestCase):
    def test_bounded_postgres_sampling_and_source_preservation(self):
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.schema import CreateSchema, DropSchema

        from app import models
        from app.db.session import get_engine
        from app.services.replay import session_replay

        schema = "replay_test_" + uuid4().hex
        engine = get_engine().execution_options(schema_translate_map={None: schema})
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        try:
            models.Base.metadata.create_all(engine)
            factory = sessionmaker(engine, expire_on_commit=False)
            with factory.begin() as db:
                season = models.Season(year=2025)
                circuit = models.Circuit(name="Replay test", country="Australia")
                driver = models.Driver(given_name="Test", family_name="Driver")
                db.add_all([season, circuit, driver])
                db.flush()
                event = models.Event(
                    season_id=season.id,
                    circuit_id=circuit.id,
                    round=1,
                    name="Replay test",
                )
                db.add(event)
                db.flush()
                session = models.Session(event_id=event.id, type="race")
                db.add(session)
                db.flush()
                case = ReplayTests()
                case.factory, case.session_id, case.driver_id = (
                    factory,
                    session.id,
                    driver.id,
                )
            case.seed(times=range(1000))
            with factory() as db:
                count = db.scalar(
                    select(func.count()).select_from(models.TelemetrySourceRecord)
                )
                payload = session_replay(db, case.session_id, max_samples=32)
                self.assertNotEqual(payload.capability, "unavailable")
                for entry in payload.drivers:
                    self.assertLessEqual(len(entry.positions), 32)
                    self.assertEqual(entry.positions[0].elapsed_seconds, 0)
                    self.assertEqual(entry.positions[-1].elapsed_seconds, 999)
                self.assertEqual(
                    count,
                    db.scalar(
                        select(func.count()).select_from(models.TelemetrySourceRecord)
                    ),
                )
        finally:
            with engine.begin() as connection:
                models.Base.metadata.drop_all(connection)
                connection.execute(DropSchema(schema))
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
