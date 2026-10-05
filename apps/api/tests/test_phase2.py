"""Focused provider normalization, retry and atomic ingestion checks."""

import asyncio
import copy
import unittest
from datetime import timezone

import httpx
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def race():
    return {
        "season": "2025",
        "round": "1",
        "raceName": "Test Grand Prix",
        "date": "2025-03-16",
        "time": "04:00:00Z",
        "FirstPractice": {"date": "2025-03-14"},
        "Circuit": {
            "circuitId": "test",
            "circuitName": "Test Circuit",
            "Location": {"country": "Australia", "locality": "Test city"},
        },
    }


def driver():
    return {
        "driverId": "test_driver",
        "givenName": "Test",
        "familyName": "Driver",
        "code": "TST",
        "permanentNumber": "7",
        "nationality": "British",
    }


def team():
    return {"constructorId": "test_team", "name": "Test Team", "nationality": "British"}


def payloads():
    result = {
        "Driver": driver(),
        "Constructor": team(),
        "position": "1",
        "grid": "2",
        "laps": "57",
        "points": "25",
        "status": "Finished",
        "Time": {"millis": "5000000", "time": "1:23:20.000"},
    }
    second = copy.deepcopy(result)
    second["Driver"]["driverId"] = "second_driver"
    second["Driver"]["code"] = "SEC"
    second["Driver"]["permanentNumber"] = "8"
    second.update(
        position="2", points="18", Time={"millis": "5001250", "time": "+1.250"}
    )
    return {
        "races": [race()],
        "drivers": [driver(), second["Driver"]],
        "constructors": [team()],
        "results": [dict(race(), Results=[result, second])],
        "qualifying": [],
        "sprint": [],
        "driverstandings": [
            {
                "season": "2025",
                "round": "1",
                "DriverStandings": [
                    {
                        "Driver": driver(),
                        "Constructors": [team()],
                        "position": "1",
                        "points": "25",
                        "wins": "1",
                    },
                ],
            }
        ],
        "constructorstandings": [
            {
                "season": "2025",
                "round": "1",
                "ConstructorStandings": [
                    {
                        "Constructor": team(),
                        "position": "1",
                        "points": "43",
                        "wins": "1",
                    },
                ],
            }
        ],
    }


def provider(data=None, handler=None):
    from app.providers.jolpica import JolpicaProvider

    data = payloads() if data is None else data

    def respond(request):
        endpoint = request.url.path.rsplit("/", 1)[-1].removesuffix(".json")
        rows = data[endpoint]
        if endpoint in {"drivers", "constructors"}:
            table, key = (
                ("DriverTable", "Drivers")
                if endpoint == "drivers"
                else ("ConstructorTable", "Constructors")
            )
        elif endpoint.endswith("standings"):
            table, key = "StandingsTable", "StandingsLists"
        else:
            table, key = "RaceTable", "Races"
        if endpoint in {"results", "qualifying", "sprint"}:
            nested = {
                "results": "Results",
                "qualifying": "QualifyingResults",
                "sprint": "SprintResults",
            }[endpoint]
            total = sum(len(row[nested]) for row in rows)
        elif endpoint.endswith("standings"):
            nested = (
                "DriverStandings"
                if endpoint == "driverstandings"
                else "ConstructorStandings"
            )
            total = sum(len(row[nested]) for row in rows)
        else:
            total = len(rows)
        return httpx.Response(
            200,
            json={
                "MRData": {
                    "total": str(total),
                    "limit": "100",
                    "offset": "0",
                    table: {key: rows},
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler or respond))
    return JolpicaProvider(client=client, request_interval=0, sleep=lambda _: None)


class Phase2Tests(unittest.TestCase):
    def test_unranked_standings_preserve_missing_position(self):
        from app.ingestion.service import run_import
        from app.models import ConstructorStanding, DriverStanding

        data = payloads()
        del data["driverstandings"][0]["DriverStandings"][0]["position"]
        del data["constructorstandings"][0]["ConstructorStandings"][0]["position"]
        run_import(provider(data), self.factory, 2025)
        with self.factory() as db:
            self.assertIsNone(db.scalar(select(DriverStanding)).position)
            self.assertIsNone(db.scalar(select(ConstructorStanding)).position)

    def test_additive_migration_matches_models(self):
        import importlib.util
        import io
        from pathlib import Path

        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import MetaData

        from app.models import Base

        # This historical revision check covers Phase 1–2 tables only.
        core_metadata = MetaData()
        for mapper in Base.registry.mappers:
            if mapper.class_.__module__ in {"app.models.domain", "app.models.imports"}:
                mapper.local_table.to_metadata(core_metadata)
        migrations = []
        for filename in ("0001_core_domain.py", "0002_core_ingestion.py"):
            path = Path(__file__).parents[1] / "migrations/versions" / filename
            spec = importlib.util.spec_from_file_location(filename, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            migrations.append(module)
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                context = MigrationContext.configure(
                    connection, opts={"target_metadata": Base.metadata}
                )
                with Operations.context(context):
                    for migration in migrations:
                        migration.upgrade()
                self.assertEqual(compare_metadata(context, core_metadata), [])
                with Operations.context(context):
                    migrations[1].downgrade()
                    migrations[0].downgrade()
            output = io.StringIO()
            context = MigrationContext.configure(
                dialect_name="postgresql",
                opts={
                    "as_sql": True,
                    "output_buffer": output,
                    "target_metadata": Base.metadata,
                },
            )
            with Operations.context(context):
                for migration in migrations:
                    migration.upgrade()
            self.assertEqual(output.getvalue().count("CREATE TABLE "), 11)
            self.assertIn("ADD COLUMN scheduled_date DATE", output.getvalue())
        finally:
            engine.dispose()

    def test_reimport_clears_unavailable_timing(self):
        from app.ingestion.service import run_import
        from app.models import Event, Result

        run_import(provider(), self.factory, 2025)
        data = payloads()
        del data["races"][0]["time"]
        del data["results"][0]["Results"][1]["Time"]
        run_import(provider(data), self.factory, 2025)
        with self.factory() as db:
            result = db.scalar(select(Result).where(Result.position == 2))
            self.assertIsNone(result.total_time_ms)
            self.assertIsNone(result.gap_ms)
            self.assertIsNone(db.scalar(select(Event)).starts_at)

    def setUp(self):
        from app.models import Base

        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)

    def tearDown(self):
        self.engine.dispose()

    def test_normalization_preserves_date_only_and_race_times(self):
        bundle = provider().fetch(2025)
        practice = next(
            row
            for row in bundle.records
            if row.kind == "session" and row.attributes["type"] == "practice_1"
        )
        self.assertIsNone(practice.attributes.get("starts_at"))
        self.assertEqual(str(practice.attributes["scheduled_date"]), "2025-03-14")
        results = [row for row in bundle.records if row.kind == "result"]
        self.assertEqual(results[0].attributes["total_time_ms"], 5000000)
        self.assertEqual(results[1].attributes["total_time_ms"], 5001250)
        self.assertEqual(results[1].attributes["gap_ms"], 1250)

    def test_reimport_updates_without_duplicates_or_changed_ids(self):
        from app.ingestion.service import run_import
        from app.models import Driver, ImportRun, ProviderIdentity, Result, Session

        first = run_import(provider(), self.factory, 2025)
        with self.factory() as db:
            identities = dict(
                db.execute(
                    select(ProviderIdentity.external_id, ProviderIdentity.domain_id)
                ).all()
            )
        data = payloads()
        data["results"][0]["Results"][0]["points"] = "24.5"
        run_import(provider(data), self.factory, 2025)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Driver)), 2)
            self.assertEqual(db.scalar(select(func.count()).select_from(Result)), 2)
            self.assertEqual(db.scalar(select(func.count()).select_from(ImportRun)), 2)
            self.assertEqual(
                identities,
                dict(
                    db.execute(
                        select(ProviderIdentity.external_id, ProviderIdentity.domain_id)
                    ).all()
                ),
            )
            self.assertEqual(
                str(db.scalar(select(Result).where(Result.position == 1)).points),
                "24.500",
            )
            self.assertEqual(db.get(ImportRun, first).status, "succeeded")
            self.assertEqual(
                db.scalar(select(Session).where(Session.type == "race")).status,
                "completed",
            )

    def test_failed_import_rolls_back_domain_but_records_failure(self):
        from app.ingestion.service import run_import
        from app.models import Event, ImportRun

        data = payloads()
        data["results"][0]["Results"][0]["points"] = "-1"
        with self.assertRaises(ValidationError):
            run_import(provider(data), self.factory, 2025)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Event)), 0)
            run = db.scalar(select(ImportRun))
            self.assertEqual(run.status, "failed")
            self.assertIsNotNone(run.failure_details)

    def test_retry_and_pagination_honor_offsets(self):
        calls = []

        def respond(request):
            calls.append(int(request.url.params["offset"]))
            if len(calls) == 1:
                return httpx.Response(503)
            offset = int(request.url.params["offset"])
            return httpx.Response(
                200,
                json={
                    "MRData": {
                        "total": "2",
                        "limit": "1",
                        "offset": str(offset),
                        "DriverTable": {
                            "Drivers": [dict(driver(), driverId=f"driver_{offset}")]
                        },
                    }
                },
            )

        adapter = provider(handler=respond)
        rows = adapter._pages("2025/drivers.json", "DriverTable", "Drivers")
        self.assertEqual(len(rows), 2)
        self.assertEqual(calls, [0, 0, 1])

    def test_standings_round_is_not_relabelled(self):
        from app.ingestion.service import run_import
        from app.models import ImportRun
        from app.providers.base import ProviderError

        data = payloads()
        data["driverstandings"][0]["round"] = "2"
        with self.assertRaises(ProviderError):
            run_import(provider(data), self.factory, 2025)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(ImportRun)).status, "failed")

    def test_public_reads_use_domain_ids_and_missing_items_return_404(self):
        from sqlalchemy.orm.attributes import set_committed_value

        from app.api.core import database as read_database
        from app.ingestion.service import run_import
        from app.main import app
        from app.models import Base

        run_import(provider(), self.factory, 2025)
        db = self.factory()
        # SQLite drops timezone information; restore it only in test fixtures.
        held = []
        for model in Base.registry.mappers:
            for row in db.scalars(select(model.class_)):
                for field in ("created_at", "updated_at", "starts_at", "ends_at"):
                    value = getattr(row, field, None)
                    if value is not None and value.tzinfo is None:
                        set_committed_value(
                            row, field, value.replace(tzinfo=timezone.utc)
                        )
                held.append(row)

        def database():
            yield db

        app.dependency_overrides[read_database] = database

        async def requests():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                events = await client.get("/v1/events?season=2025")
                self.assertEqual(events.status_code, 200)
                event_id = events.json()[0]["id"]
                self.assertNotEqual(event_id, "2025:1")
                sessions = await client.get(f"/v1/events/{event_id}/sessions")
                self.assertEqual(sessions.status_code, 200)
                race_id = next(
                    row["id"] for row in sessions.json() if row["type"] == "race"
                )
                results = await client.get(f"/v1/sessions/{race_id}/results")
                self.assertEqual(len(results.json()), 2)
                self.assertNotIn("Driver", results.json()[0])
                standings = await client.get("/v1/standings/drivers?season=2025")
                self.assertEqual(len(standings.json()), 1)
                missing = await client.get(
                    "/v1/events/00000000-0000-0000-0000-000000000001"
                )
                self.assertEqual(missing.status_code, 404)

        try:
            asyncio.run(requests())
        finally:
            app.dependency_overrides.clear()
            db.close()


if __name__ == "__main__":
    unittest.main()
