"""Saved presets: scoped CRUD, real references and explicit missing data."""

import asyncio
import unittest
from uuid import UUID, uuid4

import httpx
import test_phase4 as fixture
from sqlalchemy import select


class SavedComparisonTests(unittest.TestCase):
    def setUp(self):
        fixture.Phase4Tests.setUp(self)
        data = fixture.source_data()
        data["laps"].append({**data["laps"][0], "lap_number": 2})
        fixture.Phase4Tests.import_data(self, data)
        from app import models
        from app.api.comparisons import workspace_owner
        from app.api.core import database
        from app.main import app

        self.app = app
        self.owner = uuid4()

        def db():
            with self.factory() as session:
                yield session

        app.dependency_overrides[database] = db
        app.dependency_overrides[workspace_owner] = lambda: self.owner
        self.addCleanup(app.dependency_overrides.clear)
        with self.factory() as db:
            session = db.get(models.Session, self.session_id)
            event = db.get(models.Event, session.event_id)
            laps = db.scalars(select(models.Lap).order_by(models.Lap.lap_number)).all()
            self.config = {
                "version": 1,
                "season": 2025,
                "event_id": str(event.id),
                "session_id": str(session.id),
                "driver_a_id": str(self.driver_id),
                "driver_b_id": str(self.driver_id),
                "lap_a_id": str(laps[0].id),
                "lap_b_id": str(laps[1].id),
                "alignment": "elapsed_time",
                "allow_approximate": True,
            }

    def request(self, method, path="/v1/comparisons", **kwargs):
        async def call():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app), base_url="http://test"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(call())

    def create(self, **extra):
        return self.request(
            "POST",
            json={
                "title": "Australian lap pair",
                "comparison_type": "telemetry_laps",
                "configuration": self.config,
                **extra,
            },
        )

    def test_crud_and_deterministic_reopening(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.text)
        saved = response.json()
        self.assertEqual(saved["source_route"], "/telemetry")
        self.assertNotIn("owner_id", saved)
        self.assertIn("season=2025", saved["open_url"])
        self.assertIn(f"session={self.session_id}", saved["open_url"])
        self.assertIn("alignment=elapsed_time", saved["open_url"])
        self.assertTrue(saved["created_at"].endswith("Z"))
        path = f"/v1/comparisons/{saved['id']}"
        self.assertEqual(len(self.request("GET").json()), 1)
        self.assertEqual(self.request("GET", path).json()["configuration"], self.config)
        self.assertEqual(
            self.request("PATCH", path, json={"title": "Renamed"}).json()["title"],
            "Renamed",
        )
        changed = {**self.config, "alignment": "normalized_distance"}
        self.assertEqual(
            self.request("PATCH", path, json={"configuration": changed}).status_code,
            200,
        )
        self.assertEqual(self.request("DELETE", path).status_code, 204)
        self.assertEqual(self.request("GET", path).status_code, 404)

    def test_validation_and_ownership_isolation(self):
        self.assertEqual(self.create(owner_id=str(uuid4())).status_code, 422)
        self.assertEqual(self.create(comparison_type="invented").status_code, 422)
        for changes in (
            {"lap_a_id": "bad"},
            {"lap_a_id": str(uuid4())},
            {"season": 2010},
            {"driver_a_id": str(uuid4())},
            {"lap_b_id": self.config["lap_a_id"]},
            {"version": 2},
            {"secret": "not-accepted"},
        ):
            self.assertEqual(
                self.create(configuration={**self.config, **changes}).status_code, 422
            )
        saved = self.create().json()
        self.owner = uuid4()
        self.assertEqual(self.request("GET").json(), [])
        path = f"/v1/comparisons/{saved['id']}"
        for method in ("GET", "DELETE", "PATCH"):
            kwargs = {"json": {"title": "Changed"}} if method == "PATCH" else {}
            self.assertEqual(self.request(method, path, **kwargs).status_code, 404)

    def test_missing_lap_keeps_preset_and_original_ids(self):
        from app import models

        saved = self.create().json()
        with self.factory.begin() as db:
            db.delete(db.get(models.Lap, UUID(self.config["lap_b_id"])))
        response = self.request("GET", f"/v1/comparisons/{saved['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["availability"], "unavailable")
        self.assertIsNone(response.json()["open_url"])
        self.assertEqual(response.json()["configuration"], self.config)

    def test_partial_historical_data_is_not_fabricated(self):
        saved = self.create().json()
        self.assertEqual(saved["availability"], "partial")
        self.assertTrue(saved["notices"])
        self.assertEqual(self.request("GET", params={"season": 2010}).json(), [])
        self.assertEqual(
            self.create(configuration={**self.config, "season": 2010}).status_code, 422
        )

    def test_stale_configuration_version_is_explicit_and_safe(self):
        from app import models

        saved = self.create().json()
        with self.factory.begin() as db:
            row = db.get(models.SavedComparison, UUID(saved["id"]))
            row.configuration = {
                **row.configuration,
                "version": 2,
                "unknown": "do-not-echo",
            }
        response = self.request("GET", f"/v1/comparisons/{saved['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["availability"], "unavailable")
        self.assertIsNone(response.json()["open_url"])
        self.assertNotIn("do-not-echo", response.text)

    def test_bounded_listing_batches_identities_and_null_updates_are_rejected(self):
        from sqlalchemy import event

        for number in range(4):
            self.assertEqual(self.create(title=f"Pair {number}").status_code, 201)
        count = []

        def track(connection, cursor, statement, parameters, context, many):
            if statement.lstrip().upper().startswith("SELECT"):
                count.append(statement)

        event.listen(self.engine, "before_cursor_execute", track)
        try:
            response = self.request("GET", params={"limit": 3, "offset": 1})
        finally:
            event.remove(self.engine, "before_cursor_execute", track)
        self.assertEqual(len(response.json()), 3)
        self.assertLessEqual(len(count), 8)
        saved = response.json()[0]
        for payload in ({}, {"title": None}, {"configuration": None}):
            self.assertEqual(
                self.request(
                    "PATCH", f"/v1/comparisons/{saved['id']}", json=payload
                ).status_code,
                422,
            )

    def test_model_keeps_aware_times_and_non_destructive_foreign_keys(self):
        from app import models

        table = models.SavedComparison.__table__
        self.assertTrue(table.c.created_at.type.timezone)
        self.assertTrue(table.c.updated_at.type.timezone)
        self.assertEqual(len(table.foreign_keys), 7)
        self.assertTrue(all(key.ondelete == "SET NULL" for key in table.foreign_keys))

    def test_real_but_wrong_driver_session_and_mixed_sources_are_rejected(self):
        from app import models

        with self.factory.begin() as db:
            driver = models.Driver(given_name="Other", family_name="Driver")
            session = models.Session(
                event_id=UUID(self.config["event_id"]), type="qualifying"
            )
            db.add_all([driver, session])
            db.flush()
            driver_id, session_id = str(driver.id), str(session.id)
        for changed in ({"driver_a_id": driver_id}, {"session_id": session_id}):
            self.assertEqual(
                self.create(configuration={**self.config, **changed}).status_code, 422
            )
        with self.factory.begin() as db:
            db.get(models.Lap, UUID(self.config["lap_b_id"])).provider = "other"
        self.assertEqual(self.create().status_code, 422)
        self.assertEqual(
            self.request("GET", "/v1/comparisons/not-a-uuid").status_code, 422
        )

    def test_completed_session_with_live_provisional_records_stays_labelled(self):
        from datetime import datetime, timezone

        from app import models
        from app.domain.enums import SessionStatus

        with self.factory.begin() as db:
            db.get(models.Session, self.session_id).status = SessionStatus.COMPLETED
            db.add(
                models.SessionUpdateJob(
                    session_id=self.session_id,
                    source_session=9999,
                    driver_ids={},
                    next_attempt_at=datetime.now(timezone.utc),
                    data_status="provisional",
                )
            )
        response = self.create().json()
        self.assertIn(
            "Session records are provisional, not final classification.",
            response["notices"],
        )

    def test_strategy_pair_and_scope(self):
        from app import models
        from app.domain.enums import SessionStatus

        with self.factory.begin() as db:
            db.get(models.Session, self.session_id).status = SessionStatus.COMPLETED
            driver = models.Driver(given_name="Second", family_name="Driver")
            db.add(driver)
            db.flush()
            first = db.scalar(select(models.Stint))
            db.add(
                models.Stint(
                    provider=first.provider,
                    session_id=self.session_id,
                    driver_id=driver.id,
                    source_key="second",
                    source_record_id=first.source_record_id,
                    stint_number=1,
                    lap_start=1,
                    lap_end=2,
                    compound=None,
                    tyre_age_at_start=None,
                )
            )
            driver_id = str(driver.id)
        config = {
            key: self.config[key]
            for key in (
                "version",
                "season",
                "event_id",
                "session_id",
                "driver_a_id",
                "driver_b_id",
            )
        }
        config.update(driver_b_id=driver_id, provider_a="openf1", provider_b="openf1")
        response = self.create(comparison_type="strategy_tyres", configuration=config)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertIn("/strategy?", response.json()["open_url"])
        self.assertIn("a=openf1%3A", response.json()["open_url"])
        self.assertEqual(
            self.create(
                comparison_type="strategy_tyres",
                configuration={**config, "provider_b": "unknown"},
            ).status_code,
            422,
        )


if __name__ == "__main__":
    unittest.main()
