"""Accounts/authorization without upstream requests or local application writes."""

import asyncio
import importlib.util
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
import test_phase4 as fixture
from fastapi import Request
from sqlalchemy import event as orm_event
from sqlalchemy import select
from sqlalchemy.orm.attributes import set_committed_value


class AuthTests(unittest.TestCase):
    def setUp(self):
        fixture.Phase4Tests.setUp(self)
        data = fixture.source_data()
        data["laps"].append({**data["laps"][0], "lap_number": 2})
        fixture.Phase4Tests.import_data(self, data)
        from app import models
        from app.api.auth import admission, unsafe_request
        from app.api.core import database
        from app.main import app

        self.app = app

        def db():
            with self.factory() as session:
                yield session

        def allowed(request: Request):
            unsafe_request(request)
            yield

        app.dependency_overrides[database] = db
        app.dependency_overrides[admission] = allowed
        self.addCleanup(app.dependency_overrides.clear)

        @orm_event.listens_for(self.factory, "loaded_as_persistent")
        def utc_fields(db, row):
            for key in (
                "created_at",
                "updated_at",
                "starts_at",
                "ends_at",
                "fetched_at",
                "timestamp",
                "source_observed_at",
                "expires_at",
            ):
                value = getattr(row, key, None)
                if isinstance(value, datetime) and value.tzinfo is None:
                    set_committed_value(row, key, value.replace(tzinfo=timezone.utc))

        with self.factory() as db:
            session = db.get(models.Session, self.session_id)
            event = db.get(models.Event, session.event_id)
            laps = db.scalars(select(models.Lap).order_by(models.Lap.lap_number)).all()
            self.preset = {
                "title": "Recorded pair",
                "comparison_type": "telemetry_laps",
                "configuration": {
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
                },
            }

    def request(self, method, path, *, token=None, guarded=True, **kwargs):
        async def call():
            headers = {"X-F1-Auth": "1"} if guarded else {}
            if token:
                headers["Cookie"] = f"f1_session={token}"
            headers.update(kwargs.pop("headers", {}))
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app), base_url="http://test"
            ) as client:
                return await client.request(method, path, headers=headers, **kwargs)

        return asyncio.run(call())

    def register(self, username="tester"):
        response = self.request(
            "POST",
            "/v1/auth/register",
            json={"username": username, "password": "A-long-test-password!"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json(), response.cookies["f1_session"]

    def test_registration_hash_session_me_login_logout(self):
        from argon2 import PasswordHasher

        from app import models

        user, token = self.register()
        self.assertEqual(
            self.request("GET", "/v1/auth/me", token=token).json()["id"], user["id"]
        )
        with self.factory() as db:
            stored = db.get(models.User, UUID(user["id"]))
            self.assertTrue(
                PasswordHasher().verify(stored.password_hash, "A-long-test-password!")
            )
            session = db.scalar(select(models.AuthSession))
            self.assertNotEqual(session.token_hash, token)
            self.assertNotIn("password_hash", user)
        self.assertIn(
            "HttpOnly",
            self.request(
                "POST",
                "/v1/auth/login",
                json={"username": "TESTER", "password": "A-long-test-password!"},
            ).headers["set-cookie"],
        )
        login = self.request(
            "POST",
            "/v1/auth/login",
            token=token,
            json={"username": "tester", "password": "A-long-test-password!"},
        )
        new_token = login.cookies["f1_session"]
        self.assertNotEqual(token, new_token)
        self.assertEqual(
            self.request("GET", "/v1/auth/me", token=token).status_code, 401
        )
        self.assertEqual(
            self.request("POST", "/v1/auth/logout", token=new_token).status_code, 204
        )
        self.assertEqual(
            self.request("GET", "/v1/auth/me", token=new_token).status_code, 401
        )

    def test_failures_validation_csrf_and_expiry(self):
        user, token = self.register()
        wrong = self.request(
            "POST",
            "/v1/auth/login",
            json={"username": "tester", "password": "Wrong-password-123"},
        )
        missing = self.request(
            "POST",
            "/v1/auth/login",
            json={"username": "nobody", "password": "Wrong-password-123"},
        )
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.json(), missing.json())
        invalid = self.request(
            "POST",
            "/v1/auth/register",
            json={"username": "x", "password": "sensitive-invalid"},
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertNotIn("sensitive-invalid", invalid.text)
        self.assertEqual(
            self.request(
                "POST",
                "/v1/auth/login",
                guarded=False,
                json={"username": "tester", "password": "A-long-test-password!"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.request(
                "POST",
                "/v1/auth/logout",
                token=token,
                headers={"Origin": "http://untrusted.example"},
            ).status_code,
            403,
        )
        from app import models

        with self.factory.begin() as db:
            db.scalar(select(models.AuthSession)).expires_at = datetime.now(
                timezone.utc
            ) - timedelta(seconds=1)
        self.assertEqual(
            self.request("GET", "/v1/auth/me", token=token).status_code, 401
        )

    def test_user_scoped_crud_and_unauthenticated_rejection(self):
        self.assertEqual(
            self.request("POST", "/v1/comparisons", json=self.preset).status_code, 401
        )
        a, token_a = self.register("driver-a")
        created = self.request(
            "POST", "/v1/comparisons", token=token_a, json=self.preset
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.headers["cache-control"], "no-store")
        identifier = created.json()["id"]
        self.assertEqual(
            self.request(
                "POST",
                "/v1/comparisons",
                token=token_a,
                guarded=False,
                json=self.preset,
            ).status_code,
            403,
        )
        b, token_b = self.register("driver-b")
        self.assertEqual(
            self.request("GET", "/v1/comparisons", token=token_b).json(), []
        )
        for method in ("GET", "PATCH", "DELETE"):
            kwargs = {"json": {"title": "Stolen"}} if method == "PATCH" else {}
            self.assertEqual(
                self.request(
                    method, f"/v1/comparisons/{identifier}", token=token_b, **kwargs
                ).status_code,
                404,
            )
        self.assertEqual(
            self.request(
                "POST", "/v1/comparisons", token=token_b, json=self.preset
            ).status_code,
            201,
        )
        own = self.request("GET", f"/v1/comparisons/{identifier}", token=token_a).json()
        self.assertIn("season=2025", own["open_url"])
        self.assertEqual(
            len(self.request("GET", "/v1/comparisons", token=token_a).json()), 1
        )
        self.assertEqual(
            self.request(
                "PATCH",
                f"/v1/comparisons/{identifier}",
                token=token_a,
                json={"title": "Mine"},
            ).json()["title"],
            "Mine",
        )
        self.assertEqual(
            self.request(
                "DELETE", f"/v1/comparisons/{identifier}", token=token_a
            ).status_code,
            204,
        )

    def test_public_data_is_accessible_without_account(self):
        for path in (
            f"/v1/sessions/{self.session_id}/laps",
            f"/v1/sessions/{self.session_id}/replay",
            "/v1/seasons",
        ):
            self.assertEqual(self.request("GET", path, guarded=False).status_code, 200)
        response = self.request(
            "GET", f"/v1/sessions/{self.session_id}/strategy", guarded=False
        )
        self.assertNotIn(response.status_code, (401, 403))

    def test_legacy_presets_require_explicit_operator_assignment(self):
        from app import models
        from app.accounts.__main__ import assign_legacy
        from app.schemas.comparisons import ComparisonCreate
        from app.services.comparisons import apply_configuration

        user, token = self.register()
        workspace = uuid4()
        with self.factory.begin() as db:
            row = models.SavedComparison(
                owner_id=workspace,
                title="Preserved legacy",
                comparison_type="telemetry_laps",
            )
            apply_configuration(db, row, ComparisonCreate.model_validate(self.preset))
            db.add(row)
            db.flush()
            identifier = row.id
        self.assertEqual(self.request("GET", "/v1/comparisons", token=token).json(), [])
        with self.factory() as db:
            self.assertEqual(assign_legacy(db, workspace, UUID(user["id"])), 1)
        self.assertEqual(
            self.request(
                "GET", f"/v1/comparisons/{identifier}", token=token
            ).status_code,
            404,
        )
        with self.factory() as db:
            self.assertEqual(
                assign_legacy(db, workspace, UUID(user["id"]), apply=True), 1
            )
            self.assertEqual(
                assign_legacy(db, workspace, UUID(user["id"]), apply=True), 0
            )
        restored = self.request(
            "GET", f"/v1/comparisons/{identifier}", token=token
        ).json()
        self.assertEqual(restored["configuration"], self.preset["configuration"])

    def test_cookie_flags_and_bounded_session_count(self):
        user, token = self.register()
        from app import models

        with patch("app.api.auth.get_settings") as config:
            from app.core.config import Settings

            config.return_value = Settings(_env_file=None, auth_cookie_secure=True)
            response = self.request(
                "POST",
                "/v1/auth/login",
                json={"username": "tester", "password": "A-long-test-password!"},
            )
        self.assertIn("Secure", response.headers["set-cookie"])
        for _ in range(6):
            self.request(
                "POST",
                "/v1/auth/login",
                json={"username": "tester", "password": "A-long-test-password!"},
            )
        with self.factory() as db:
            self.assertEqual(len(db.scalars(select(models.AuthSession)).all()), 5)
        oversized = self.request(
            "POST",
            "/v1/auth/login",
            json={"username": "tester", "password": "x" * 5000},
        )
        self.assertEqual(oversized.status_code, 413)
        self.assertNotIn("xxxxx", oversized.text)

    def test_password_whitespace_is_preserved_and_required_for_login(self):
        password = "  A-long-test-password!  "
        registered = self.request(
            "POST",
            "/v1/auth/register",
            json={"username": " exact-name ", "password": password},
        )
        self.assertEqual(registered.status_code, 201)
        self.assertEqual(registered.json()["username"], "exact-name")
        exact = self.request(
            "POST",
            "/v1/auth/login",
            json={"username": "EXACT-NAME", "password": password},
        )
        trimmed = self.request(
            "POST",
            "/v1/auth/login",
            json={"username": "exact-name", "password": password.strip()},
        )
        self.assertEqual(exact.status_code, 200)
        self.assertEqual(trimmed.status_code, 401)


@unittest.skipUnless(
    os.environ.get("F1_TEST_POSTGRES") == "1", "Opt-in isolated PostgreSQL check"
)
class PostgresAccountTests(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import text
        from sqlalchemy.schema import CreateSchema, DropSchema

        from app import models
        from app.db.session import get_engine

        self.schema = "accounts_test_" + uuid4().hex
        self.engine = get_engine().execution_options(
            schema_translate_map={None: self.schema}
        )
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as conn:
            conn.execute(CreateSchema(self.schema))

        def cleanup():
            with self.engine.begin() as conn:
                models.Base.metadata.drop_all(conn)
                conn.execute(DropSchema(self.schema))

        self.addCleanup(cleanup)
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        self.legacy_id, self.workspace = uuid4(), uuid4()
        with self.engine.begin() as conn:
            conn.execute(text(f'SET LOCAL search_path TO "{self.schema}"'))
            context = MigrationContext.configure(
                conn, opts={"target_metadata": models.Base.metadata}
            )
            with Operations.context(context):
                for path in sorted(
                    (Path(__file__).parents[1] / "migrations/versions").glob("*.py")
                ):
                    spec = importlib.util.spec_from_file_location(path.stem, path)
                    migration = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(migration)
                    if path.stem == "0010_user_accounts":
                        conn.execute(
                            text(
                                "INSERT INTO saved_comparisons "
                                "(id,owner_id,title,comparison_type,season,"
                                "source_route,configuration) VALUES "
                                "(:id,:owner,'Legacy preset','telemetry_laps',"
                                "2025,'/telemetry',CAST(:configuration AS json))"
                            ),
                            {
                                "id": self.legacy_id,
                                "owner": self.workspace,
                                "configuration": '{"version":1,"season":2025}',
                            },
                        )
                        self.migration = migration
                    migration.upgrade()

    def test_schema_legacy_preservation_constraints_and_safe_rollback(self):
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm import Session

        from app import models
        from app.accounts.__main__ import assign_legacy
        from app.services.auth import hasher

        with self.engine.begin() as conn:
            conn.execute(text(f'SET LOCAL search_path TO "{self.schema}"'))
            context = MigrationContext.configure(
                conn, opts={"target_metadata": models.Base.metadata}
            )
            self.assertEqual(compare_metadata(context, models.Base.metadata), [])
        with Session(self.engine) as db:
            row = db.get(models.SavedComparison, self.legacy_id)
            self.assertEqual(row.owner_id, self.workspace)
            self.assertIsNone(row.user_id)
            self.assertEqual(row.configuration, {"version": 1, "season": 2025})
            user = models.User(
                username="test-owner",
                password_hash=hasher.hash("Password-for-isolated-test!"),
            )
            db.add(user)
            db.commit()
            user_id = user.id
            self.assertEqual(assign_legacy(db, self.workspace, user_id, apply=True), 1)
        with self.engine.begin() as conn:
            conn.execute(text(f'SET LOCAL search_path TO "{self.schema}"'))
            context = MigrationContext.configure(conn)
            with (
                Operations.context(context),
                self.assertRaisesRegex(RuntimeError, "preservation plan"),
            ):
                self.migration.downgrade()
        with Session(self.engine) as db:
            self.assertIsNone(db.get(models.SavedComparison, self.legacy_id).owner_id)
            with self.assertRaises(IntegrityError):
                db.execute(
                    models.User.__table__.delete().where(models.User.id == user_id)
                )
                db.commit()
            db.rollback()
            row = db.get(models.SavedComparison, self.legacy_id)
            row.owner_id = self.workspace
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()
            row.user_id = None
            row.owner_id = self.workspace
            db.commit()
            db.execute(models.User.__table__.delete().where(models.User.id == user_id))
            db.commit()
        with self.engine.begin() as conn:
            conn.execute(text(f'SET LOCAL search_path TO "{self.schema}"'))
            context = MigrationContext.configure(
                conn, opts={"target_metadata": models.Base.metadata}
            )
            with Operations.context(context):
                self.migration.downgrade()
                self.migration.upgrade()
            self.assertEqual(compare_metadata(context, models.Base.metadata), [])

    def test_database_shared_admission_bounds_and_failure_recovery(self):
        from fastapi import HTTPException

        from app.ai.protection import LOCK_NAMESPACE as PITWALL_NAMESPACE
        from app.core.config import Settings
        from app.services.auth_protection import NAMESPACE, permit

        self.assertNotEqual(NAMESPACE, PITWALL_NAMESPACE)
        settings = Settings(
            _env_file=None, auth_requests_per_minute=2, auth_max_concurrent=1
        )
        with self.assertRaisesRegex(RuntimeError, "simulated"):
            with self.engine.connect() as first, permit(first, settings, now=6000):
                with (
                    self.engine.connect() as second,
                    self.assertRaises(HTTPException) as error,
                ):
                    with permit(second, settings, now=6000):
                        self.fail("Overlapping hashes admitted")
                self.assertEqual(error.exception.status_code, 429)
                raise RuntimeError("simulated hash failure")
        with (
            self.engine.connect() as connection,
            permit(connection, settings, now=6000),
        ):
            pass
        with (
            self.engine.connect() as connection,
            self.assertRaises(HTTPException) as error,
        ):
            with permit(connection, settings, now=6000):
                self.fail("Rate limit bypassed")
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(error.exception.headers["Retry-After"], "60")
        with (
            self.engine.connect() as connection,
            permit(connection, settings, now=6060),
        ):
            pass


if __name__ == "__main__":
    unittest.main()
