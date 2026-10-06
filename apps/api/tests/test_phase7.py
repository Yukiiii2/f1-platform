"""Strategy checks against temporary storage; no provider IO or production writes."""

import asyncio
import hashlib
import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.pool import StaticPool

from app import models


class Phase7Tests(unittest.TestCase):
    def setUp(self):
        try:
            from app.services.strategy import session_strategy
        except ImportError:
            self.fail("Phase 7 strategy service is not implemented")
        self.strategy = session_strategy
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        models.Base.metadata.create_all(self.engine)
        self.db = sessionmaker(self.engine, expire_on_commit=False)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.start = datetime(2025, 3, 16, 4, tzinfo=timezone.utc)
        season = models.Season(year=2025)
        circuit = models.Circuit(name="Test", country="Australia")
        self.driver = models.Driver(given_name="A", family_name="Driver")
        self.db.add_all([season, circuit, self.driver])
        self.db.flush()
        weekend = models.Event(
            season_id=season.id, circuit_id=circuit.id, round=1, name="Test"
        )
        self.db.add(weekend)
        self.db.flush()
        self.session = models.Session(
            event_id=weekend.id, type="race", status="completed"
        )
        self.db.add(self.session)
        self.db.flush()
        self.stint = self.row(
            models.Stint,
            "stint",
            stint_number=1,
            lap_start=4,
            lap_end=8,
            tyre_age_at_start=3,
            compound="SOFT",
        )
        for lap, duration in ((4, 90), (5, 120), (6, 110), (7, 92), (8, 0)):
            self.row(
                models.Lap,
                "lap",
                lap_number=lap,
                duration_seconds=duration,
                starts_at=self.start,
                start_time_is_approximate=True,
                is_pit_out_lap=False,
            )
        self.row(models.PitStop, "pit", timestamp=self.start, lap_number=5)
        for category, message, lap in (
            ("SafetyCar", "SAFETY CAR DEPLOYED", 5),
            ("Flag", "VIRTUAL SAFETY CAR ENDING", None),
            ("Flag", "YELLOW IN TURN 1", 6),
        ):
            self.row(
                models.RaceControlMessage,
                "race_control",
                driver_id=None,
                timestamp=self.start,
                category=category,
                message=message,
                lap_number=lap,
                scope="Track",
            )
        self.db.commit()
        self.held = []
        self.aware_fixtures()

    def aware_fixtures(self):
        # SQLite loses timezone metadata; production PostgreSQL preserves it.
        for mapper in models.Base.registry.mappers:
            for row in self.db.scalars(select(mapper.class_)):
                for column in mapper.columns:
                    value = getattr(row, column.key)
                    if isinstance(value, datetime) and value.tzinfo is None:
                        set_committed_value(
                            row, column.key, value.replace(tzinfo=timezone.utc)
                        )
                self.held.append(row)

    def row(self, model, kind, provider="openf1", **fields):
        key = str(uuid4())
        payload = {"kind": kind, "value": key}
        raw = models.TelemetrySourceRecord(
            session_id=self.session.id,
            provider=provider,
            kind=kind,
            source_key=key,
            payload=payload,
            checksum=hashlib.sha256(json.dumps(payload).encode()).hexdigest(),
            fetched_at=self.start,
        )
        self.db.add(raw)
        self.db.flush()
        row = (
            model(
                session_id=self.session.id,
                provider=provider,
                source_key=key,
                source_record_id=raw.id,
                driver_id=self.driver.id,
                **fields,
            )
            if "driver_id" not in fields
            else model(
                session_id=self.session.id,
                provider=provider,
                source_key=key,
                source_record_id=raw.id,
                **fields,
            )
        )
        self.db.add(row)
        self.db.flush()
        return row

    def result(self, provider=None):
        self.aware_fixtures()
        return self.strategy(self.db, self.session, provider)

    def test_pace_excludes_pit_laps_next_laps_and_nonpositive_timing(self):
        stint = self.result().drivers[0].stints[0]
        self.assertEqual(stint.pace.recorded_laps, 5)
        self.assertEqual(stint.pace.included_laps, 2)
        self.assertEqual(stint.pace.excluded_laps, 3)
        self.assertEqual(stint.pace.average_seconds, Decimal("91"))
        self.assertEqual(stint.pace.best_seconds, Decimal("90"))
        self.assertEqual(stint.completed_laps_on_stint, 5)
        self.assertEqual(stint.total_tyre_age, 8)
        self.assertEqual(stint.source.tyre_age_at_start, 3)

    def test_unknown_age_and_unknown_pit_out_status_stay_unavailable(self):
        self.stint.tyre_age_at_start = None
        for lap in self.db.scalars(select(models.Lap)):
            lap.is_pit_out_lap = None
        self.db.flush()
        stint = self.result().drivers[0].stints[0]
        self.assertEqual(stint.completed_laps_on_stint, 5)
        self.assertIsNone(stint.total_tyre_age)
        self.assertEqual(stint.pace.included_laps, 0)
        self.assertIsNone(stint.pace.average_seconds)
        self.assertIsNone(stint.pace.best_seconds)

    def test_overlaps_and_missing_bounds_do_not_guess_stint_metrics(self):
        other = self.row(models.Stint, "stint", stint_number=2, lap_start=8, lap_end=10)
        self.db.flush()
        first, last = self.result().drivers[0].stints
        for stint in (first, last):
            self.assertEqual(stint.context_status, "ambiguous")
        self.assertEqual(first.pace.average_seconds, Decimal("91"))
        self.assertEqual(first.age_completed_lap, 7)
        self.assertEqual(first.completed_laps_on_stint, 4)
        self.assertEqual(first.total_tyre_age, 7)
        self.assertIsNone(last.pace.average_seconds)
        self.assertIsNone(last.total_tyre_age)
        other.lap_start = None
        self.db.flush()
        stints = self.result().drivers[0].stints
        self.assertEqual(stints[0].context_status, "ambiguous")
        self.assertIsNone(stints[0].pace.average_seconds)
        self.assertEqual(stints[1].context_status, "unavailable")
        self.assertIsNone(stints[1].completed_laps_on_stint)

    def test_provider_scopes_are_separate_and_reads_preserve_source_rows(self):
        self.row(
            models.Stint,
            "stint",
            provider="other",
            stint_number=1,
            lap_start=4,
            lap_end=4,
            compound="HARD",
            tyre_age_at_start=0,
        )
        self.row(
            models.Lap,
            "lap",
            provider="other",
            lap_number=4,
            duration_seconds=30,
            start_time_is_approximate=False,
            is_pit_out_lap=False,
        )
        before = [
            (row.id, dict(row.payload))
            for row in self.db.scalars(select(models.TelemetrySourceRecord))
        ]
        results = {driver.provider: driver for driver in self.result().drivers}
        self.assertEqual(
            results["openf1"].stints[0].pace.average_seconds, Decimal("91")
        )
        self.assertEqual(results["other"].stints[0].pace.average_seconds, Decimal("30"))
        self.assertEqual(len(self.result("other").drivers), 1)
        self.assertEqual(
            before,
            [
                (row.id, row.payload)
                for row in self.db.scalars(select(models.TelemetrySourceRecord))
            ],
        )
        self.assertFalse(self.db.dirty)

    def test_race_control_retains_messages_and_missing_lap_without_inferred_periods(
        self,
    ):
        context = self.result().race_control
        self.assertEqual(
            {row.message for row in context},
            {"SAFETY CAR DEPLOYED", "VIRTUAL SAFETY CAR ENDING"},
        )
        self.assertTrue(any(row.lap_number is None for row in context))
        self.assertEqual(self.result().lap_axis_end, 8)

    def test_unknown_pit_lap_disables_pace_instead_of_guessing_its_location(self):
        pit = self.db.scalar(select(models.PitStop))
        pit.lap_number = None
        self.db.flush()
        pace = self.result().drivers[0].stints[0].pace
        self.assertIsNone(pace.average_seconds)
        self.assertEqual(pace.unavailable_reason, "pit_lap_context")

    def test_different_drivers_are_not_combined_and_empty_imports_are_explicit(self):
        second = models.Driver(given_name="B", family_name="Driver")
        self.db.add(second)
        self.db.flush()
        self.row(
            models.Stint,
            "stint",
            driver_id=second.id,
            stint_number=1,
            lap_start=4,
            lap_end=4,
            tyre_age_at_start=0,
        )
        self.row(
            models.Lap,
            "lap",
            driver_id=second.id,
            lap_number=4,
            duration_seconds=80,
            start_time_is_approximate=True,
            is_pit_out_lap=False,
        )
        results = {driver.driver_id: driver for driver in self.result().drivers}
        self.assertEqual(
            results[self.driver.id].stints[0].pace.average_seconds, Decimal("91")
        )
        self.assertEqual(
            results[second.id].stints[0].pace.average_seconds, Decimal("80")
        )
        empty = self.result("not-imported")
        self.assertEqual(empty.drivers, [])
        self.assertEqual(empty.race_control, [])
        self.assertIsNone(empty.lap_axis_end)

    def test_endpoint_requires_completed_race_and_returns_application_data(self):
        from app.api.core import database
        from app.main import app

        def dependency():
            yield self.db

        app.dependency_overrides[database] = dependency
        self.addCleanup(app.dependency_overrides.clear)

        async def check():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/v1/sessions/{self.session.id}/strategy")
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("source_key", response.text)
                self.assertNotIn("source_record_id", response.text)
                self.assertEqual(
                    response.json()["drivers"][0]["stints"][0]["pace"][
                        "average_seconds"
                    ],
                    "91.000000",
                )
                self.session.status = "upcoming"
                self.db.flush()
                self.assertEqual(
                    (
                        await client.get(f"/v1/sessions/{self.session.id}/strategy")
                    ).status_code,
                    422,
                )
                self.session.status = "completed"
                self.session.type = "qualifying"
                self.db.flush()
                self.assertEqual(
                    (
                        await client.get(f"/v1/sessions/{self.session.id}/strategy")
                    ).status_code,
                    422,
                )
                self.assertEqual(
                    (await client.get(f"/v1/sessions/{uuid4()}/strategy")).status_code,
                    404,
                )

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
