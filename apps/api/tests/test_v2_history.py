"""Historical seasons use existing normalized contracts, not telemetry assumptions."""

import asyncio
import copy
import importlib.util
import os
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import test_phase2
from sqlalchemy import func, select


def historical(year=2010):
    data = copy.deepcopy(test_phase2.payloads())
    for key in ("races", "results", "driverstandings", "constructorstandings"):
        for row in data[key]:
            row["season"] = str(year)
            if "date" in row:
                row["date"] = f"{year}-03-16"
                row.pop("FirstPractice", None)
                row.pop("time", None)
    data["drivers"][1]["driverId"] = f"historical_{year}"
    data["results"][0]["Results"][1]["Driver"]["driverId"] = f"historical_{year}"
    return data


class HistoryTests(unittest.TestCase):
    setUp = test_phase2.Phase2Tests.setUp
    tearDown = test_phase2.Phase2Tests.tearDown

    def test_conflicting_shared_driver_classifications_are_not_silently_merged(self):
        from app.providers.base import ProviderError

        data = historical(1950)
        extra = copy.deepcopy(data["results"][0]["Results"][0])
        extra["position"] = "3"
        data["results"][0]["Results"].append(extra)
        with self.assertRaises(ProviderError):
            test_phase2.provider(data).fetch(1950)

    def test_missing_historical_sessions_and_standings_are_not_invented(self):
        data = historical(1950)
        data["driverstandings"] = []
        data["constructorstandings"] = []
        bundle = test_phase2.provider(data).fetch(1950)
        self.assertEqual(
            [
                record.attributes["type"]
                for record in bundle.records
                if record.kind == "session"
            ],
            ["race"],
        )
        self.assertFalse(
            any(record.kind.endswith("standing") for record in bundle.records)
        )

    def test_historical_imports_coexist_and_reimport_preserves_ids_and_raw(self):
        from app import models
        from app.ingestion.service import run_import

        run_import(test_phase2.provider(), self.factory, 2025)
        run_import(test_phase2.provider(historical()), self.factory, 2010)
        with self.factory() as db:
            ids = [
                (r.entity_kind, r.external_id, r.domain_id)
                for r in db.scalars(select(models.ProviderIdentity))
            ]
        run_import(test_phase2.provider(historical()), self.factory, 2010)
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(models.Season)), 2
            )
            self.assertEqual(
                ids,
                [
                    (r.entity_kind, r.external_id, r.domain_id)
                    for r in db.scalars(select(models.ProviderIdentity))
                ],
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(models.CoreSourceRevision)),
                2,
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(models.SessionUpdateJob)), 0
            )

    def test_old_observation_cannot_overwrite_corrected_results(self):
        from app import models
        from app.ingestion.service import persist_bundle

        observed = datetime(2026, 10, 1, tzinfo=timezone.utc)
        old = replace(
            test_phase2.provider(historical()).fetch(2010), fetched_at=observed
        )
        data = historical()
        data["results"][0]["Results"][0]["points"] = "24.5"
        new = replace(
            test_phase2.provider(data).fetch(2010),
            fetched_at=observed + timedelta(minutes=1),
        )
        for bundle in (new, old):
            with self.factory.begin() as db:
                persist_bundle(db, "jolpica", bundle)
        with self.factory() as db:
            self.assertEqual(
                str(
                    db.scalar(
                        select(models.Result).where(models.Result.position == 1)
                    ).points
                ),
                "24.500",
            )

    def test_unchanged_observation_advances_ordering_without_new_revision(self):
        from app import models
        from app.ingestion.service import persist_bundle

        initial = test_phase2.provider(historical()).fetch(2010)
        latest = replace(initial, fetched_at=initial.fetched_at + timedelta(minutes=2))
        data = historical()
        data["results"][0]["Results"][0]["points"] = "20"
        stale = replace(
            test_phase2.provider(data).fetch(2010),
            fetched_at=initial.fetched_at + timedelta(minutes=1),
        )
        for bundle in (initial, latest, stale):
            with self.factory.begin() as db:
                persist_bundle(db, "jolpica", bundle)
        with self.factory() as db:
            self.assertEqual(
                str(
                    db.scalar(
                        select(models.Result).where(models.Result.position == 1)
                    ).points
                ),
                "25.000",
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(models.CoreSourceRevision)),
                2,
            )

    def test_completed_history_rejects_live_registration_but_allows_post_session(self):
        from app import models
        from app.ingestion.service import run_import
        from app.workers.sessions import register_session

        run_import(test_phase2.provider(historical()), self.factory, 2010)
        with self.factory() as db:
            session = db.scalar(
                select(models.Session).where(models.Session.type == "race")
            )
            driver = db.scalar(select(models.Driver))
        with self.assertRaisesRegex(ValueError, "Historical completed"):
            register_session(self.factory, session.id, 100, {1: driver.id}, live=True)
        register_session(self.factory, session.id, 100, {1: driver.id})
        with self.factory() as db:
            self.assertFalse(db.scalar(select(models.SessionUpdateJob)).live_enabled)

    def test_historical_tools_retrieve_scoped_records_and_explicit_missing_laps(self):
        from sqlalchemy import event
        from sqlalchemy.orm.attributes import set_committed_value

        from app import models
        from app.ai.tools import ToolExecutor
        from app.ingestion.service import run_import
        from app.schemas.ai import PageContext

        @event.listens_for(self.factory, "loaded_as_persistent")
        def aware(db, row):
            for column in row.__mapper__.columns:
                value = getattr(row, column.key)
                if isinstance(value, datetime) and value.tzinfo is None:
                    set_committed_value(
                        row, column.key, value.replace(tzinfo=timezone.utc)
                    )

        run_import(test_phase2.provider(), self.factory, 2025)
        run_import(test_phase2.provider(historical()), self.factory, 2010)
        with self.factory() as db:
            event_row = db.scalar(
                select(models.Event)
                .join(models.Season)
                .where(models.Season.year == 2010)
            )
            session = db.scalar(
                select(models.Session).where(
                    models.Session.event_id == event_row.id,
                    models.Session.type == "race",
                )
            )
            executor = ToolExecutor(
                db,
                PageContext(
                    route="/races",
                    season=2010,
                    event_id=event_row.id,
                    session_id=session.id,
                ),
            )
            drivers = executor.execute("get_drivers", {"season": 2010})
            self.assertEqual(drivers.status, "available")
            self.assertEqual(len(drivers.data["source"]), 2)
            events = executor.execute("get_events", {"season": 2010})
            self.assertEqual(events.data["source"][0]["id"], str(event_row.id))
            laps = executor.execute("get_laps", {"session_id": str(session.id)})
            self.assertEqual(laps.status, "unavailable")
            self.assertEqual(laps.data, {})

    def test_availability_partial_import_and_missing_source_standings(self):
        from app.ingestion.service import run_import
        from app.services.core import season_availability

        data = historical()
        data["constructorstandings"] = []
        run_import(test_phase2.provider(data), self.factory, 2010, 1)
        with self.factory() as db:
            self.assertEqual(
                season_availability(db, [2010])[2010].availability, "partial"
            )
        run_import(test_phase2.provider(data), self.factory, 2010)
        with self.factory() as db:
            status = season_availability(db, [2010])[2010]
            self.assertEqual(status.availability, "partial")
            self.assertFalse(status.constructor_standings_available)

    def test_http_historical_scope_details_missing_telemetry_and_availability(self):
        from app.api.core import database
        from app.ingestion.service import run_import
        from app.main import app

        run_import(test_phase2.provider(), self.factory, 2025)
        run_import(test_phase2.provider(historical()), self.factory, 2010)
        with self.factory() as db:
            from sqlalchemy.orm.attributes import set_committed_value

            from app import models

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

            async def check():
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    seasons = await client.get("/v1/seasons")
                    self.assertEqual(seasons.status_code, 200)
                    self.assertEqual([r["year"] for r in seasons.json()], [2025, 2010])
                    self.assertTrue(
                        all(r["availability"] == "imported" for r in seasons.json())
                    )
                    missing = await client.get("/v1/seasons/2000/availability")
                    self.assertEqual(missing.json()["availability"], "unavailable")
                    self.assertIsNone(missing.json()["season_id"])
                    for year in (2010, 2025):
                        events = (await client.get(f"/v1/events?season={year}")).json()
                        self.assertEqual(len(events), 1)
                        detail = await client.get(f"/v1/events/{events[0]['id']}")
                        self.assertEqual(detail.status_code, 200)
                        sessions = (
                            await client.get(f"/v1/events/{events[0]['id']}/sessions")
                        ).json()
                        race = next(s for s in sessions if s["type"] == "race")
                        results = await client.get(f"/v1/sessions/{race['id']}/results")
                        self.assertEqual(len(results.json()), 2)
                        for path in ("laps", "stints", "telemetry"):
                            rows = await client.get(f"/v1/sessions/{race['id']}/{path}")
                            self.assertEqual(rows.json(), [])
                        for category in ("drivers", "constructors"):
                            rows = (
                                await client.get(
                                    f"/v1/standings/{category}?season={year}"
                                )
                            ).json()
                            self.assertEqual(
                                rows[0]["season_id"], events[0]["season_id"]
                            )
                        drivers = (
                            await client.get(f"/v1/drivers?season={year}")
                        ).json()
                        self.assertEqual(len(drivers), 2)
                        self.assertEqual(
                            len(
                                (
                                    await client.get(
                                        f"/v1/drivers?season={year}&limit=1&offset=1"
                                    )
                                ).json()
                            ),
                            1,
                        )
                    self.assertEqual(
                        (await client.get("/v1/drivers?season=2000")).json(), []
                    )

            try:
                asyncio.run(check())
            finally:
                app.dependency_overrides.clear()


@unittest.skipUnless(
    os.environ.get("F1_TEST_POSTGRES") == "1", "Opt-in isolated PostgreSQL check"
)
class PostgresHistoryTests(unittest.TestCase):
    def test_migration_roundtrip_and_existing_observation_backfill(self):
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import text
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.schema import CreateSchema, DropSchema

        from app import models
        from app.db.session import get_engine
        from app.ingestion.service import run_import

        schema = "history_test_" + uuid4().hex
        engine = get_engine().execution_options(schema_translate_map={None: schema})
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        try:
            with engine.begin() as connection:
                connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                context = MigrationContext.configure(
                    connection, opts={"target_metadata": models.Base.metadata}
                )
                with Operations.context(context):
                    for path in sorted(
                        (Path(__file__).parents[1] / "migrations/versions").glob("*.py")
                    ):
                        spec = importlib.util.spec_from_file_location(path.stem, path)
                        migration = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(migration)
                        migration.upgrade()
                    self.assertEqual(
                        compare_metadata(context, models.Base.metadata), []
                    )
            factory = sessionmaker(engine, expire_on_commit=False)
            run_import(test_phase2.provider(historical()), factory, 2010)
            with engine.begin() as connection:
                connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                context = MigrationContext.configure(
                    connection, opts={"target_metadata": models.Base.metadata}
                )
                with Operations.context(context):
                    migration.downgrade()
                    migration.upgrade()
                self.assertEqual(compare_metadata(context, models.Base.metadata), [])
            with factory() as db:
                self.assertEqual(
                    db.scalar(select(func.count()).select_from(models.CoreSourceState)),
                    db.scalar(
                        select(func.count()).select_from(models.ProviderIdentity)
                    ),
                )
                self.assertEqual(
                    db.scalar(
                        select(func.count()).select_from(models.CoreSourceRevision)
                    ),
                    0,
                )
        finally:
            with engine.begin() as connection:
                models.Base.metadata.drop_all(connection)
                connection.execute(DropSchema(schema))


if __name__ == "__main__":
    unittest.main()
