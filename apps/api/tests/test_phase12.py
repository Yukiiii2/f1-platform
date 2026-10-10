"""Regressions for the reviewed Phase 12 findings; no live provider calls."""

import asyncio
import os
import unittest
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine


class SharedLocks:
    """Connection-owned advisory locks, shared by independently created guards."""

    def __init__(self):
        self.owners = {}


class GuardConnection:
    def __init__(self, connection, locks):
        self.connection, self.locks = connection, locks
        self.dialect = SimpleNamespace(name="postgresql")

    def scalar(self, statement):
        sql = str(statement)
        if "pg_try_advisory_lock(" in sql:
            slot = tuple(statement.compile().params.values())
            if slot in self.locks.owners:
                return False
            self.locks.owners[slot] = self
            return True
        if "pg_advisory_unlock(" in sql:
            slot = tuple(statement.compile().params.values())
            if self.locks.owners.get(slot) is self:
                del self.locks.owners[slot]
            return True
        if "pg_try_advisory_xact_lock(" in sql:
            return True
        return self.connection.scalar(statement)

    def __getattr__(self, name):
        return getattr(self.connection, name)


class PitwallProtectionTests(unittest.TestCase):
    def setUp(self):
        from app.ai.protection import permit
        from app.models import PitwallUsage

        self.permit = permit
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        PitwallUsage.__table__.create(self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                PitwallUsage.__table__.insert().values(
                    id=1, minute=0, minute_count=0, day=0, day_count=0
                )
            )
        self.locks = SharedLocks()
        self.settings = SimpleNamespace(
            pitwall_requests_per_minute=2,
            pitwall_requests_per_day=3,
            pitwall_max_concurrent=1,
        )

    @contextmanager
    def connection(self):
        with self.engine.connect() as connection:
            yield GuardConnection(connection, self.locks)

    def test_minute_and_daily_usage_are_shared_and_bounded(self):
        for _ in range(2):
            with (
                self.connection() as connection,
                self.permit(connection, self.settings, now=86400),
            ):
                pass
        with self.connection() as connection, self.assertRaises(HTTPException) as error:
            with self.permit(connection, self.settings, now=86400):
                self.fail("Rate-limited request reached the model")
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(error.exception.headers["Retry-After"], "60")
        with (
            self.connection() as connection,
            self.permit(connection, self.settings, now=86460),
        ):
            pass
        with self.connection() as connection, self.assertRaises(HTTPException) as error:
            with self.permit(connection, self.settings, now=86520):
                self.fail("Daily usage limit did not hold")
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(error.exception.headers["Retry-After"], "86280")
        with (
            self.connection() as connection,
            self.permit(connection, self.settings, now=172800),
        ):
            pass

    def test_overlapping_guards_reject_and_failure_releases_concurrency(self):
        with self.assertRaisesRegex(RuntimeError, "simulated failure"):
            with (
                self.connection() as first,
                self.permit(first, self.settings, now=86400),
            ):
                with (
                    self.connection() as second,
                    self.assertRaises(HTTPException) as error,
                ):
                    with self.permit(second, self.settings, now=86400):
                        self.fail("Concurrent model request was admitted")
                self.assertEqual(error.exception.status_code, 429)
                raise RuntimeError("simulated failure")
        self.assertFalse(self.locks.owners)
        with (
            self.connection() as connection,
            self.permit(connection, self.settings, now=86400),
        ):
            pass

    def test_missing_budget_and_unsupported_database_fail_closed(self):
        from app.models import PitwallUsage

        with self.engine.begin() as connection:
            connection.execute(PitwallUsage.__table__.delete())
        with self.connection() as connection, self.assertRaises(HTTPException) as error:
            with self.permit(connection, self.settings, now=86400):
                self.fail("Missing migration bypassed protection")
        self.assertEqual(error.exception.status_code, 503)
        self.assertFalse(self.locks.owners)
        with (
            self.engine.connect() as connection,
            self.assertRaises(HTTPException) as error,
        ):
            with self.permit(connection, self.settings):
                self.fail("Unsupported deployment bypassed protection")
        self.assertEqual(error.exception.status_code, 503)

    def test_endpoint_rejection_precedes_model_creation_and_hides_input(self):
        import httpx

        from app.api.ai import ai_client, pitwall_access
        from app.main import app

        created = []

        def denied():
            raise HTTPException(
                429,
                "Pitwall is busy; please try again later",
                headers={"Retry-After": "5"},
            )

        app.dependency_overrides[pitwall_access] = denied
        app.dependency_overrides[ai_client] = lambda: created.append(True)
        self.addCleanup(app.dependency_overrides.clear)

        async def check():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as http:
                response = await http.post(
                    "/v1/ai/query", json={"question": "private question"}
                )
                self.assertEqual(response.status_code, 429)
                self.assertEqual(response.headers["Retry-After"], "5")
                self.assertNotIn("private", response.text)

        asyncio.run(check())
        self.assertFalse(created)


class TelemetryOrderingTests(unittest.TestCase):
    def setUp(self):
        from apps.api.tests.test_phase4 import Phase4Tests

        self.fixture = Phase4Tests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_older_partial_driver_scope_still_inserts_missing_records(self):
        from dataclasses import replace
        from datetime import datetime, timedelta, timezone

        from apps.api.tests.test_phase4 import provider, source_data
        from sqlalchemy import select

        from app import models
        from app.ingestion.telemetry import persist_session_bundle
        from app.providers.openf1_normalization import normalize

        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        current = replace(
            provider().fetch_session(9999, [7]),
            fetched_at=base + timedelta(seconds=3),
            observation_started_at=base + timedelta(seconds=2),
        )
        other_data = source_data()
        for rows in other_data.values():
            for row in rows:
                if row.get("driver_number") == 7:
                    row["driver_number"] = 8
        other_data["drivers"][0]["name_acronym"] = "SEC"
        other = replace(
            normalize(other_data, 9999, [8], base + timedelta(seconds=1)),
            fetched_at=base + timedelta(seconds=1),
            observation_started_at=base,
        )
        with self.fixture.factory.begin() as db:
            driver = models.Driver(
                given_name="Second", family_name="Driver", code="SEC"
            )
            db.add(driver)
            db.flush()
            second_id = driver.id
            persist_session_bundle(
                db,
                "openf1",
                self.fixture.session_id,
                9999,
                {7: self.fixture.driver_id},
                current,
            )
        with self.fixture.factory.begin() as db:
            persist_session_bundle(
                db, "openf1", self.fixture.session_id, 9999, {8: second_id}, other
            )
        with self.fixture.factory() as db:
            self.assertEqual(
                set(db.scalars(select(models.Lap.driver_id))),
                {self.fixture.driver_id, second_id},
            )
            self.assertEqual(
                db.scalar(select(models.WeatherSample.source_observed_at)).replace(
                    tzinfo=timezone.utc
                ),
                current.observation_started_at,
            )

    def test_slow_older_import_preserves_revisions_without_replacing_newer_rows(self):
        from dataclasses import replace
        from datetime import datetime, timedelta, timezone
        from decimal import Decimal

        from apps.api.tests.test_phase4 import provider, source_data
        from sqlalchemy import select

        from app import models
        from app.ingestion.telemetry import persist_session_bundle

        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        old = replace(
            provider().fetch_session(9999, [7]),
            fetched_at=base + timedelta(seconds=10),
            observation_started_at=base,
        )
        corrected = source_data()
        corrected["laps"][0]["lap_duration"] = 92.001
        new = replace(
            provider(corrected).fetch_session(9999, [7]),
            fetched_at=base + timedelta(seconds=5),
            observation_started_at=base + timedelta(seconds=1),
        )

        def persist(bundle):
            with self.fixture.factory.begin() as db:
                persist_session_bundle(
                    db,
                    "openf1",
                    self.fixture.session_id,
                    9999,
                    {7: self.fixture.driver_id},
                    bundle,
                )

        persist(new)
        persist(old)
        persist(old)
        with self.fixture.factory() as db:
            lap = db.scalar(select(models.Lap))
            identifier = lap.id
            self.assertEqual(lap.duration_seconds, Decimal("92.001"))
            raws = db.scalars(
                select(models.TelemetrySourceRecord).where(
                    models.TelemetrySourceRecord.kind == "lap"
                )
            ).all()
            self.assertEqual(
                sorted(row.payload["lap_duration"] for row in raws), [91.743, 92.001]
            )
            self.assertEqual(
                db.get(models.TelemetrySourceRecord, lap.source_record_id).payload[
                    "lap_duration"
                ],
                92.001,
            )
        # A later observation may legitimately revert to an already archived payload.
        persist(
            replace(
                old,
                fetched_at=base + timedelta(seconds=21),
                observation_started_at=base + timedelta(seconds=20),
            )
        )
        persist(new)
        with self.fixture.factory() as db:
            lap = db.scalar(select(models.Lap))
            self.assertEqual(lap.id, identifier)
            self.assertEqual(lap.duration_seconds, Decimal("91.743"))
            self.assertEqual(
                len(
                    db.scalars(
                        select(models.TelemetrySourceRecord).where(
                            models.TelemetrySourceRecord.kind == "lap"
                        )
                    ).all()
                ),
                2,
            )

    def test_observation_migration_backfills_existing_rows_and_preserves_raw_data(self):
        import hashlib
        import importlib.util
        import json
        from dataclasses import replace
        from datetime import datetime, timedelta, timezone
        from decimal import Decimal
        from pathlib import Path
        from uuid import UUID, uuid4

        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from apps.api.tests.test_phase4 import provider, source_data
        from sqlalchemy import MetaData, Table, select

        from app import models
        from app.ingestion.telemetry import ENTITIES, persist_session_bundle

        path = (
            Path(__file__).parents[1]
            / "migrations/versions/0006_telemetry_observation_order.py"
        )
        spec = importlib.util.spec_from_file_location(path.stem, path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bundle = replace(provider().fetch_session(9999, [7]), fetched_at=base)
        with self.fixture.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
                for record in bundle.records:
                    identifier = uuid4()
                    connection.execute(
                        models.TelemetrySourceRecord.__table__.insert().values(
                            id=identifier,
                            provider="openf1",
                            session_id=self.fixture.session_id,
                            kind=record.kind,
                            source_key=record.source_key,
                            checksum=hashlib.sha256(
                                json.dumps(
                                    record.source_payload,
                                    sort_keys=True,
                                    separators=(",", ":"),
                                ).encode()
                            ).hexdigest(),
                            payload=record.source_payload,
                            fetched_at=bundle.fetched_at,
                        )
                    )
                    model, schema = ENTITIES[record.kind]
                    fields = {
                        **record.attributes,
                        "provider": "openf1",
                        "session_id": self.fixture.session_id,
                    }
                    if record.driver_number is not None:
                        fields["driver_id"] = self.fixture.driver_id
                    row = schema.model_validate(fields).model_dump()
                    row = {
                        key: value.hex if isinstance(value, UUID) else value
                        for key, value in row.items()
                    }
                    table = Table(
                        model.__tablename__, MetaData(), autoload_with=connection
                    )
                    connection.execute(
                        table.insert().values(
                            **row,
                            id=uuid4().hex,
                            source_key=record.source_key,
                            source_record_id=identifier.hex,
                            updated_at=base + timedelta(seconds=3),
                        )
                    )
                migration.upgrade()
                for model, _ in ENTITIES.values():
                    observed = connection.scalar(select(model.source_observed_at))
                    self.assertGreater(
                        observed.replace(tzinfo=timezone.utc),
                        base + timedelta(seconds=3),
                    )
                raws = (
                    connection.execute(select(models.TelemetrySourceRecord.payload))
                    .scalars()
                    .all()
                )
                self.assertEqual(
                    raws, [record.source_payload for record in bundle.records]
                )
                migration.downgrade()
                self.assertEqual(
                    connection.execute(select(models.TelemetrySourceRecord.payload))
                    .scalars()
                    .all(),
                    raws,
                )
                migration.upgrade()
        # Pre-migration A->B->A can point at the original A revision. An old B
        # fetch must not replace A after the watermark is backfilled.
        data = source_data()
        data["laps"][0]["lap_duration"] = 92.001
        stale = replace(
            provider(data).fetch_session(9999, [7]),
            fetched_at=base + timedelta(seconds=4),
            observation_started_at=base + timedelta(seconds=2),
        )
        with self.fixture.factory.begin() as db:
            persist_session_bundle(
                db,
                "openf1",
                self.fixture.session_id,
                9999,
                {7: self.fixture.driver_id},
                stale,
            )
            self.assertEqual(
                db.scalar(select(models.Lap.duration_seconds)), Decimal("91.743")
            )


class IdentityBatchTests(unittest.TestCase):
    def test_filtered_collections_keep_domain_contract_pagination_and_validation(self):
        from datetime import timezone
        from uuid import uuid4

        import httpx
        from apps.api.tests.test_phase4 import Phase4Tests
        from sqlalchemy import select
        from sqlalchemy.orm.attributes import set_committed_value

        from app import models
        from app.api.core import database, drivers
        from app.main import app

        fixture = Phase4Tests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with fixture.factory() as db:
            extra = models.Driver(given_name="Second", family_name="Driver")
            db.add(extra)
            db.commit()
            wanted = [fixture.driver_id, extra.id]
            self.assertEqual(len(drivers(db, 1, 0)), 1)
            held = []
            for model in (models.Driver, models.Circuit, models.Team):
                for row in db.scalars(select(model)):
                    for field in ("created_at", "updated_at"):
                        set_committed_value(
                            row, field, getattr(row, field).replace(tzinfo=timezone.utc)
                        )
                    held.append(row)
            app.dependency_overrides[database] = lambda: db
            self.addCleanup(app.dependency_overrides.clear)

            async def check():
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as http:
                    response = await http.get(
                        "/v1/drivers", params={"ids": str(wanted[0])}
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        [row["id"] for row in response.json()], [str(wanted[0])]
                    )
                    self.assertNotIn("provider", response.text)
                    response = await http.get(
                        "/v1/drivers",
                        params={
                            "ids": ",".join(map(str, wanted)),
                            "limit": 1,
                            "offset": 1,
                        },
                    )
                    self.assertEqual(len(response.json()), 1)
                    self.assertEqual(response.json()[0]["id"], str(sorted(wanted)[1]))
                    for path in ("drivers", "teams", "circuits"):
                        self.assertEqual(
                            (
                                await http.get(
                                    f"/v1/{path}", params={"ids": str(uuid4())}
                                )
                            ).json(),
                            [],
                        )
                        for invalid in ("", "bad-id", ",".join([str(uuid4())] * 201)):
                            self.assertEqual(
                                (
                                    await http.get(
                                        f"/v1/{path}", params={"ids": invalid}
                                    )
                                ).status_code,
                                422,
                            )

            asyncio.run(check())


@unittest.skipUnless(
    os.environ.get("F1_TEST_POSTGRES") == "1", "Opt-in isolated PostgreSQL check"
)
class PostgresProtectionTests(unittest.TestCase):
    def test_independent_connections_share_limits_and_release_slots(self):
        from unittest.mock import patch
        from uuid import uuid4

        from sqlalchemy import select
        from sqlalchemy.schema import CreateSchema, DropSchema

        from app.ai.protection import permit
        from app.db.session import get_engine
        from app.models import PitwallUsage

        # Only this disposable schema is written. Application tables/locks are
        # untouched; credentials are never rendered or included in diagnostics.
        schema = "phase12_test_" + uuid4().hex
        engine = get_engine().execution_options(schema_translate_map={None: schema})
        self.addCleanup(engine.dispose)
        namespace = uuid4().int % 2_000_000_000
        settings = SimpleNamespace(
            pitwall_requests_per_minute=2,
            pitwall_requests_per_day=2,
            pitwall_max_concurrent=1,
        )
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
            PitwallUsage.__table__.create(connection)
            connection.execute(
                PitwallUsage.__table__.insert().values(
                    id=1, minute=0, minute_count=0, day=0, day_count=0
                )
            )
        try:
            with patch("app.ai.protection.LOCK_NAMESPACE", namespace):
                with engine.connect() as first, permit(first, settings):
                    with (
                        engine.connect() as second,
                        self.assertRaises(HTTPException) as error,
                    ):
                        with permit(second, settings):
                            self.fail(
                                "Independent connection exceeded concurrency limit"
                            )
                    self.assertEqual(error.exception.status_code, 429)
                with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                    with engine.connect() as second, permit(second, settings):
                        raise RuntimeError("simulated failure")
                with (
                    engine.connect() as third,
                    self.assertRaises(HTTPException) as error,
                ):
                    with permit(third, settings):
                        self.fail("Shared usage limit did not hold")
                self.assertEqual(error.exception.status_code, 429)
                with engine.connect() as connection:
                    row = (
                        connection.execute(select(PitwallUsage.__table__))
                        .mappings()
                        .one()
                    )
                    self.assertEqual(row["day_count"], 2)
                    self.assertEqual(row["minute_count"], 2)
        finally:
            with engine.begin() as connection:
                PitwallUsage.__table__.drop(connection)
                connection.execute(DropSchema(schema))


if __name__ == "__main__":
    unittest.main()
