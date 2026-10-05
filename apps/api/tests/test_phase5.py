"""Hand-checked comparison cases against temporary storage, without provider IO."""

import asyncio
import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.pool import StaticPool

from app import models


class Phase5Tests(unittest.TestCase):
    def setUp(self):
        try:
            from app.schemas.comparison import CompareRequest
            from app.services.comparison import compare_laps
        except ImportError:
            self.fail("Phase 5 comparison service is not implemented")
        self.compare = compare_laps
        self.request = CompareRequest
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
        self.held = []
        season = models.Season(year=2025)
        circuit = models.Circuit(name="Test", country="Australia")
        self.drivers = [
            models.Driver(given_name=name, family_name="Driver") for name in ("A", "B")
        ]
        self.db.add_all([season, circuit, *self.drivers])
        self.db.flush()
        weekend = models.Event(
            season_id=season.id, circuit_id=circuit.id, round=1, name="Test"
        )
        self.db.add(weekend)
        self.db.flush()
        self.session = models.Session(event_id=weekend.id, type="race")
        self.db.add(self.session)
        self.db.flush()
        self.laps = [
            self.make_lap(self.drivers[0], 4),
            self.make_lap(self.drivers[1], 5),
        ]
        for index, lap in enumerate(self.laps):
            for second in range(5 + index):
                self.sample(lap, second, speed=36 if index == 0 else Decimal("28.8"))
            self.stint(lap, 1, 4, 20, 3 if index == 0 else None)
        self.db.commit()
        self.aware_fixtures()

    def source(self, kind, key, payload, provider="openf1"):
        row = models.TelemetrySourceRecord(
            provider=provider,
            session_id=self.session.id,
            kind=kind,
            source_key=key,
            checksum=hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest(),
            payload=payload,
            fetched_at=self.start,
        )
        self.db.add(row)
        self.db.flush()
        return row.id

    def make_lap(self, driver, duration):
        key = f"{driver.id}:10"
        lap = models.Lap(
            provider="openf1",
            session_id=self.session.id,
            driver_id=driver.id,
            source_key=key,
            source_record_id=self.source("lap", key, {"duration": duration}),
            lap_number=10,
            starts_at=self.start,
            start_time_is_approximate=False,
            duration_seconds=Decimal(duration),
            sector_1_seconds=Decimal("1.25"),
            sector_2_seconds=None,
            sector_3_seconds=Decimal("1.5"),
            is_pit_out_lap=False,
        )
        self.db.add(lap)
        self.db.flush()
        return lap

    def sample(self, lap, second, speed=36, provider=None):
        provider = provider or lap.provider
        stamp = self.start + timedelta(seconds=float(second))
        key = f"{lap.driver_id}:{stamp.isoformat()}"
        row = models.TelemetrySample(
            provider=provider,
            session_id=self.session.id,
            driver_id=lap.driver_id,
            lap_id=lap.id if provider == lap.provider else None,
            source_key=key,
            source_record_id=self.source(
                "telemetry", key, {"speed": str(speed)}, provider
            ),
            timestamp=stamp,
            speed_kph=speed,
            throttle_percent=20 + Decimal(str(second)) * 10,
            brake_applied=second >= 1,
            gear=2 if second < 1 else 3,
            rpm=1000 + int(second * 100),
            drs_state=8 if second < 1 else 12,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def stint(self, lap, number, first, last, age):
        key = f"{lap.driver_id}:stint:{number}"
        row = models.Stint(
            provider=lap.provider,
            session_id=lap.session_id,
            driver_id=lap.driver_id,
            source_key=key,
            source_record_id=self.source("stint", key, {"age": age}),
            stint_number=number,
            lap_start=first,
            lap_end=last,
            tyre_age_at_start=age,
            compound="SOFT",
        )
        self.db.add(row)
        self.db.flush()
        return row

    def aware_fixtures(self):
        # SQLite discards timezone metadata; PostgreSQL does not.
        for mapper in models.Base.registry.mappers:
            for row in self.db.scalars(select(mapper.class_)):
                for column in mapper.columns:
                    value = getattr(row, column.key)
                    if isinstance(value, datetime) and value.tzinfo is None:
                        set_committed_value(
                            row, column.key, value.replace(tzinfo=timezone.utc)
                        )
                self.held.append(row)

    def result(self, **options):
        return self.compare(
            self.db,
            self.request(
                lap_a_id=self.laps[0].id,
                lap_b_id=self.laps[1].id,
                sample_count=9,
                **options,
            ),
        )

    def test_distance_trace_and_delta_sign_are_hand_checked(self):
        result = self.result()
        self.assertEqual(result.lap_delta_ms, -1000)
        self.assertEqual(result.sector_delta_ms.sector_1, 0)
        self.assertIsNone(result.sector_delta_ms.sector_2)
        self.assertEqual(result.trace.alignment, "normalized_distance")
        self.assertEqual(result.trace.distance_a_m, 40)
        self.assertEqual(result.trace.distance_b_m, 40)
        point = result.trace.points[4]
        self.assertEqual(point.elapsed_seconds_a, 2)
        self.assertEqual(point.elapsed_seconds_b, Decimal("2.5"))
        self.assertEqual(point.delta_ms, -500)
        reverse = self.compare(
            self.db,
            self.request(
                lap_a_id=self.laps[1].id,
                lap_b_id=self.laps[0].id,
                sample_count=9,
            ),
        )
        self.assertEqual(reverse.lap_delta_ms, 1000)
        self.assertEqual(reverse.trace.points[4].delta_ms, 500)

    def test_continuous_channels_interpolate_and_discrete_channels_hold(self):
        point = self.result().trace.points[1]
        self.assertEqual(point.channels_a.throttle_percent, 25)
        self.assertEqual(point.channels_a.rpm, 1050)
        self.assertEqual(point.channels_a.gear, 2)
        self.assertFalse(point.channels_a.brake_applied)
        self.assertEqual(point.channels_a.drs_state, 8)
        point = self.result().trace.points[2]
        self.assertEqual(point.channels_a.gear, 3)
        self.assertTrue(point.channels_a.brake_applied)
        self.assertEqual(point.channels_a.drs_state, 12)

    def test_distance_integrates_variable_speed_instead_of_assuming_time_progress(self):
        speeds = (0, 36, 72, 36, 0)
        rows = self.db.scalars(
            select(models.TelemetrySample)
            .where(
                models.TelemetrySample.driver_id == self.drivers[0].id,
            )
            .order_by(models.TelemetrySample.timestamp)
        ).all()
        for row, speed in zip(rows, speeds, strict=True):
            row.speed_kph = speed
        self.db.flush()
        result = self.result()
        self.assertEqual(result.trace.distance_a_m, 40)
        self.assertEqual(result.trace.points[1].elapsed_seconds_a, 1)
        self.assertEqual(result.trace.points[1].elapsed_seconds_b, Decimal("0.625"))
        self.assertEqual(result.trace.points[1].delta_ms, 375)

    def test_stationary_finish_keeps_the_trace_endpoint_at_the_lap_boundary(self):
        rows = self.db.scalars(
            select(models.TelemetrySample)
            .where(
                models.TelemetrySample.driver_id == self.drivers[0].id,
            )
            .order_by(models.TelemetrySample.timestamp)
        ).all()
        for row, speed in zip(rows, (36, 36, 36, 0, 0), strict=True):
            row.speed_kph = speed
        self.db.flush()
        result = self.result()
        self.assertEqual(result.trace.points[-1].elapsed_seconds_a, 4)
        self.assertEqual(result.trace.points[-1].delta_ms, -1000)

    def test_missing_speed_falls_back_without_inventing_a_distance_delta(self):
        row = self.db.scalar(
            select(models.TelemetrySample).where(
                models.TelemetrySample.driver_id == self.drivers[0].id,
                models.TelemetrySample.timestamp == self.start + timedelta(seconds=1),
            )
        )
        row.speed_kph = None
        self.db.flush()
        result = self.result()
        self.assertEqual(result.trace.alignment, "elapsed_time")
        self.assertFalse(result.trace.delta_available)
        self.assertTrue(all(point.delta_ms is None for point in result.trace.points))
        self.assertEqual(result.lap_delta_ms, -1000)

    def test_long_gaps_and_missing_edges_are_not_extrapolated(self):
        for row in self.db.scalars(
            select(models.TelemetrySample).where(
                models.TelemetrySample.driver_id == self.drivers[0].id,
            )
        ):
            if row.timestamp in (self.start, self.start + timedelta(seconds=2)):
                self.db.delete(row)
        self.db.flush()
        result = self.result(alignment="elapsed_time")
        self.assertIsNone(result.trace.points[0].channels_a.speed_kph)
        # The common grid spans five seconds; 1.875 lies in a two-second hole.
        self.assertIsNone(result.trace.points[3].channels_a.speed_kph)
        self.assertIsNone(result.trace.points[-1].channels_a.speed_kph)

    def test_tyres_use_source_age_and_completed_lap_boundaries(self):
        result = self.result()
        a, b = result.lap_a.tyres, result.lap_b.tyres
        self.assertEqual(a.tyre_age_at_start, 3)
        self.assertEqual(a.completed_laps_before, 6)
        self.assertEqual(a.completed_laps_after, 7)
        self.assertEqual(a.total_age_before, 9)
        self.assertEqual(a.total_age_after, 10)
        self.assertIsNone(b.total_age_before)
        self.assertIsNone(b.total_age_after)
        self.assertEqual(b.completed_laps_after, 7)

    def test_overlapping_or_unknown_stint_bounds_do_not_guess_context(self):
        self.stint(self.laps[0], 2, 9, 15, 0)
        self.aware_fixtures()
        result = self.result()
        self.assertEqual(result.lap_a.tyres.status, "ambiguous")
        self.assertIsNone(result.lap_a.tyres.total_age_after)
        stint = self.db.scalar(
            select(models.Stint).where(
                models.Stint.driver_id == self.drivers[1].id,
            )
        )
        stint.lap_end = None
        self.db.flush()
        self.assertEqual(self.result().lap_b.tyres.status, "unavailable")

    def test_approximate_windows_require_opt_in_and_never_change_raw_rows(self):
        for lap in self.laps:
            lap.start_time_is_approximate = True
        for sample in self.db.scalars(select(models.TelemetrySample)):
            sample.lap_id = None
        self.db.commit()
        self.aware_fixtures()
        raw_before = [
            row.payload.copy()
            for row in self.db.scalars(select(models.TelemetrySourceRecord))
        ]
        self.assertEqual(self.result().trace.availability, "unavailable")
        result = self.result(allow_approximate=True)
        self.assertEqual(result.trace.association_a, "approximate_window")
        self.assertEqual(result.trace.classification, "estimate")
        self.assertEqual(result.trace.points[4].delta_ms, -500)
        self.assertTrue(
            all(
                row.lap_id is None
                for row in self.db.scalars(select(models.TelemetrySample))
            )
        )
        self.assertEqual(
            raw_before,
            [
                row.payload
                for row in self.db.scalars(select(models.TelemetrySourceRecord))
            ],
        )
        self.assertFalse(self.db.dirty)
        self.assertFalse(self.db.new)
        self.assertFalse(self.db.deleted)

    def test_provider_context_is_not_mixed(self):
        self.sample(self.laps[0], Decimal("0.5"), speed=999, provider="other")
        self.aware_fixtures()
        result = self.result()
        self.assertEqual(result.trace.distance_a_m, 40)
        self.assertEqual(result.trace.points[1].channels_a.speed_kph, 36)

    def test_missing_or_zero_lap_times_keep_source_but_disable_calculations(self):
        self.laps[0].duration_seconds = 0
        self.laps[0].sector_1_seconds = None
        self.db.flush()
        result = self.result()
        self.assertEqual(result.lap_a.lap.duration_seconds, 0)
        self.assertIsNone(result.lap_delta_ms)
        self.assertIsNone(result.sector_delta_ms.sector_1)
        self.assertEqual(result.trace.availability, "unavailable")

    def test_endpoint_validates_ids_bounds_and_session_scope(self):
        from app.api.core import database
        from app.main import app

        app.dependency_overrides[database] = lambda: self.db

        async def requests():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                body = {
                    "lap_a_id": str(self.laps[0].id),
                    "lap_b_id": str(self.laps[1].id),
                    "sample_count": 9,
                }
                response = await client.post("/v1/telemetry/compare", json=body)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["lap_delta_ms"], "-1000")
                self.assertNotIn("source_key", response.json()["lap_a"]["lap"])
                for changes in (
                    {"sample_count": 2002},
                    {"sample_count": 1},
                    {"lap_b_id": body["lap_a_id"]},
                    {"fake_channel": True},
                ):
                    response = await client.post(
                        "/v1/telemetry/compare", json={**body, **changes}
                    )
                    self.assertEqual(response.status_code, 422)
                response = await client.post(
                    "/v1/telemetry/compare", json={**body, "lap_b_id": str(uuid4())}
                )
                self.assertEqual(response.status_code, 404)
                other = models.Session(
                    event_id=self.session.event_id, type="qualifying"
                )
                self.db.add(other)
                self.db.flush()
                self.laps[1].session_id = other.id
                # Do not flush an intentionally mismatching lap/sample fixture.
                with self.db.no_autoflush:
                    response = await client.post("/v1/telemetry/compare", json=body)
                self.assertEqual(response.status_code, 422)

        try:
            asyncio.run(requests())
        finally:
            app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
