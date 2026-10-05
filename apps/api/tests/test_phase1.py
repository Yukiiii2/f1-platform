"""Focused domain integrity and bootstrap checks; no external database needed."""

import asyncio
import importlib.util
import io
import os
import re
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, insert, inspect
from sqlalchemy.exc import IntegrityError


class Phase1Tests(unittest.TestCase):
    def test_postgresql_migration_has_no_duplicate_constraint_names(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        from app.models import Base

        path = Path(__file__).parents[1] / "migrations/versions/0001_core_domain.py"
        spec = importlib.util.spec_from_file_location("postgresql_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
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
            migration.upgrade()
        sql = output.getvalue()
        names = re.findall(r"CONSTRAINT (\w+)", sql)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(sql.count("CREATE TABLE "), 9)
        self.assertIn("TIMESTAMP WITH TIME ZONE", sql)

    def test_versioned_liveness_without_database(self):
        from app.main import app

        async def request():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                return await client.get("/v1/health")

        response = asyncio.run(request())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_configuration_rejects_non_postgresql_database(self):
        from app.core.config import Settings

        with self.assertRaises(ValidationError):
            Settings(_env_file=None, database_url="sqlite:///local.db")
        settings = Settings(
            _env_file=None,
            database_url="postgresql://user:password@localhost:5432/f1",
        )
        self.assertNotIn("password", repr(settings))

    def test_database_is_lazy_and_requires_configuration(self):
        from app.core.config import get_settings
        from app.db.session import get_engine

        get_settings.cache_clear()
        get_engine.cache_clear()
        try:
            with patch.dict(os.environ, {}, clear=True):
                with patch("app.db.session.get_settings") as settings:
                    settings.return_value.database_url = None
                    with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                        get_engine()
        finally:
            get_settings.cache_clear()
            get_engine.cache_clear()

    def test_session_schema_rejects_naive_and_reversed_times(self):
        from app.schemas import SessionCreate

        data = {"event_id": uuid4(), "type": "race"}
        with self.assertRaises(ValidationError):
            SessionCreate(**data, starts_at=datetime(2026, 1, 1))
        with self.assertRaises(ValidationError):
            SessionCreate(
                **data,
                starts_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                ends_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        session = SessionCreate(**data)
        self.assertIsNone(session.starts_at)

    def test_result_schema_rejects_provider_ids_and_invalid_values(self):
        from app.schemas import ResultCreate

        data = {"session_id": uuid4(), "driver_id": uuid4(), "team_id": uuid4()}
        for invalid in ({"provider_id": "42"}, {"points": "-1"}, {"position": 0}):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                ResultCreate(**data, **invalid)
        result = ResultCreate(**data, points="0.5")
        self.assertEqual(result.points, Decimal("0.5"))
        self.assertIsNone(result.total_time_ms)

    def test_initial_migration_enforces_domain_integrity(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.schema import CreateTable

        from app.models import Base

        path = Path(__file__).parents[1] / "migrations/versions/0001_core_domain.py"
        spec = importlib.util.spec_from_file_location("initial_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine("sqlite://")

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            self.assertEqual(
                set(inspect(connection).get_table_names()),
                {
                    "seasons",
                    "circuits",
                    "events",
                    "sessions",
                    "drivers",
                    "teams",
                    "results",
                    "driver_standings",
                    "constructor_standings",
                },
            )
            tables = Base.metadata.tables
            season, other_season, circuit, event_id, session, driver, team = (
                uuid4() for _ in range(7)
            )
            connection.execute(
                insert(tables["seasons"]),
                [
                    {"id": season, "year": 2026},
                    {"id": other_season, "year": 2025},
                ],
            )
            connection.execute(
                insert(tables["circuits"]),
                {
                    "id": circuit,
                    "name": "Test circuit",
                    "country": "Test country",
                },
            )
            connection.execute(
                insert(tables["events"]),
                {
                    "id": event_id,
                    "season_id": season,
                    "circuit_id": circuit,
                    "round": 1,
                    "name": "Test event",
                },
            )
            connection.execute(
                insert(tables["sessions"]),
                {
                    "id": session,
                    "event_id": event_id,
                    "type": "race",
                },
            )
            connection.execute(
                insert(tables["drivers"]),
                {
                    "id": driver,
                    "given_name": "Test",
                    "family_name": "Driver",
                },
            )
            connection.execute(
                insert(tables["teams"]), {"id": team, "name": "Test team"}
            )
            result = {"session_id": session, "driver_id": driver, "team_id": team}
            connection.execute(insert(tables["results"]), result)
            with self.assertRaises(IntegrityError):
                connection.execute(insert(tables["results"]), result)
            with self.assertRaises(IntegrityError):
                connection.execute(
                    insert(tables["driver_standings"]),
                    {
                        "season_id": other_season,
                        "event_id": event_id,
                        "driver_id": driver,
                        "position": 1,
                        "points": 0,
                        "wins": 0,
                    },
                )
            with self.assertRaises(IntegrityError):
                connection.execute(
                    insert(tables["events"]),
                    {
                        "season_id": season,
                        "circuit_id": circuit,
                        "round": 1,
                        "name": "Duplicate round",
                    },
                )
            for table in tables.values():
                sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
                self.assertIn("UUID", sql)
                self.assertIn("TIMESTAMP WITH TIME ZONE", sql)
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
            self.assertEqual(inspect(connection).get_table_names(), [])
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
