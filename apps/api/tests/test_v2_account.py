"""Account settings use real persisted auth; no application or provider writes."""

import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import test_v2_auth as auth_fixture
from sqlalchemy import func, select


class AccountSettingsTests(unittest.TestCase):
    setUp = auth_fixture.AuthTests.setUp
    request = auth_fixture.AuthTests.request
    register = auth_fixture.AuthTests.register

    def test_profile_is_authenticated_scoped_and_secret_free(self):
        self.assertEqual(self.request("GET", "/v1/auth/account").status_code, 401)
        a, token = self.register("account-a")
        self.request("POST", "/v1/comparisons", token=token, json=self.preset)
        self.register("account-b")
        profile = self.request("GET", "/v1/auth/account", token=token)
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.headers["cache-control"], "no-store")
        body = profile.json()
        self.assertEqual(body["id"], a["id"])
        self.assertEqual(body["saved_comparison_count"], 1)
        self.assertTrue(body["created_at"])
        self.assertEqual(len(body["sessions"]), 1)
        self.assertTrue(body["sessions"][0]["is_current"])
        self.assertEqual(
            set(body["sessions"][0]), {"created_at", "expires_at", "is_current"}
        )
        self.assertNotIn(token, profile.text)
        self.assertNotIn("password", profile.text)

    def test_username_validation_conflict_session_preservation_and_isolation(self):
        a, token = self.register("account-a")
        b, other = self.register("account-b")
        response = self.request(
            "PATCH", "/v1/auth/username", token=token, json={"username": " New-Name "}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "new-name")
        self.assertEqual(
            self.request("GET", "/v1/auth/me", token=token).json()["id"], a["id"]
        )
        self.assertEqual(
            self.request(
                "PATCH",
                "/v1/auth/username",
                token=token,
                json={"username": "ACCOUNT-B"},
            ).status_code,
            409,
        )
        for payload in ({"username": "x"}, {"username": "valid", "user_id": b["id"]}):
            self.assertEqual(
                self.request(
                    "PATCH", "/v1/auth/username", token=token, json=payload
                ).status_code,
                422,
            )
        self.assertEqual(
            self.request("GET", "/v1/auth/me", token=other).json()["username"],
            "account-b",
        )
        self.assertEqual(
            self.request(
                "PATCH",
                "/v1/auth/username",
                token=token,
                guarded=False,
                json={"username": "valid"},
            ).status_code,
            403,
        )

    def test_password_requires_current_rotates_current_and_revokes_only_own_sessions(
        self,
    ):
        a, token = self.register("account-a")
        second = self.request(
            "POST",
            "/v1/auth/login",
            json={"username": "account-a", "password": "A-long-test-password!"},
        ).cookies["f1_session"]
        b, other = self.register("account-b")
        payload = {
            "current_password": "wrong-password",
            "new_password": "  New-password-for-test!  ",
        }
        wrong = self.request("POST", "/v1/auth/password", token=token, json=payload)
        self.assertEqual(wrong.status_code, 400)
        self.assertNotIn(payload["current_password"], wrong.text)
        self.assertEqual(
            self.request("GET", "/v1/auth/me", token=second).status_code, 200
        )
        response = self.request(
            "POST",
            "/v1/auth/password",
            token=token,
            json={**payload, "current_password": "A-long-test-password!"},
        )
        self.assertEqual(response.status_code, 204)
        refreshed = response.cookies["f1_session"]
        self.assertNotEqual(refreshed, token)
        for expired in (token, second):
            self.assertEqual(
                self.request("GET", "/v1/auth/me", token=expired).status_code, 401
            )
        self.assertEqual(
            self.request("GET", "/v1/auth/me", token=refreshed).status_code, 200
        )
        self.assertEqual(
            self.request("GET", "/v1/auth/me", token=other).status_code, 200
        )
        self.assertEqual(
            self.request(
                "POST",
                "/v1/auth/login",
                json={"username": "account-a", "password": "A-long-test-password!"},
            ).status_code,
            401,
        )
        from app import models
        from app.services.auth import hasher

        with self.factory() as db:
            stored = db.get(models.User, UUID(a["id"])).password_hash
            self.assertTrue(hasher.verify(stored, payload["new_password"]))
        self.assertEqual(
            self.request(
                "POST",
                "/v1/auth/login",
                json={"username": "account-a", "password": payload["new_password"]},
            ).status_code,
            200,
        )

    def test_other_sessions_revocation_keeps_current_and_other_users(self):
        a, token = self.register("account-a")
        second = self.request(
            "POST",
            "/v1/auth/login",
            json={"username": "account-a", "password": "A-long-test-password!"},
        ).cookies["f1_session"]
        b, other = self.register("account-b")
        response = self.request("GET", "/v1/auth/account", token=token)
        self.assertEqual(response.status_code, 200)
        profile = response.json()
        self.assertEqual(sum(row["is_current"] for row in profile["sessions"]), 1)
        self.assertEqual(len(profile["sessions"]), 2)
        self.assertEqual(
            self.request(
                "POST", "/v1/auth/sessions/revoke-others", token=token
            ).status_code,
            204,
        )
        self.assertEqual(
            self.request("GET", "/v1/auth/me", token=second).status_code, 401
        )
        for valid in (token, other):
            self.assertEqual(
                self.request("GET", "/v1/auth/me", token=valid).status_code, 200
            )

    def test_delete_requires_password_confirmation_preserves_public_and_other_users(
        self,
    ):
        from app import models

        a, token = self.register("account-a")
        b, other = self.register("account-b")
        self.request("POST", "/v1/comparisons", token=token, json=self.preset)
        other_preset = self.request(
            "POST", "/v1/comparisons", token=other, json=self.preset
        ).json()["id"]
        with self.factory() as db:
            public = {
                cls: db.scalar(select(func.count()).select_from(cls))
                for cls in (
                    models.Event,
                    models.Session,
                    models.Lap,
                    models.TelemetrySample,
                    models.TelemetrySourceRecord,
                )
            }
            legacy = models.SavedComparison(
                owner_id=uuid4(),
                title="Unassigned legacy",
                comparison_type="telemetry_laps",
                season=2025,
                source_route="/telemetry",
                configuration={"version": 1, "season": 2025},
            )
            db.add(legacy)
            db.commit()
            legacy_id = legacy.id
        for payload, code in (
            ({"current_password": "A-long-test-password!"}, 422),
            ({"current_password": "wrong-password", "confirmation": "DELETE"}, 400),
            (
                {
                    "current_password": "A-long-test-password!",
                    "confirmation": "DELETE",
                    "user_id": b["id"],
                },
                422,
            ),
        ):
            self.assertEqual(
                self.request(
                    "DELETE", "/v1/auth/account", token=token, json=payload
                ).status_code,
                code,
            )
        self.assertEqual(
            self.request(
                "DELETE",
                "/v1/auth/account",
                token=token,
                json={
                    "current_password": "A-long-test-password!",
                    "confirmation": "DELETE",
                },
            ).status_code,
            204,
        )
        self.assertEqual(
            self.request("GET", "/v1/auth/me", token=token).status_code, 401
        )
        self.assertEqual(
            self.request(
                "GET", f"/v1/comparisons/{other_preset}", token=other
            ).status_code,
            200,
        )
        with self.factory() as db:
            self.assertIsNone(db.get(models.User, UUID(a["id"])))
            self.assertIsNotNone(db.get(models.User, UUID(b["id"])))
            self.assertIsNotNone(db.get(models.SavedComparison, legacy_id))
            self.assertEqual(
                db.scalar(
                    select(func.count())
                    .select_from(models.AuthSession)
                    .where(models.AuthSession.user_id == UUID(a["id"]))
                ),
                0,
            )
            for cls, count in public.items():
                self.assertEqual(
                    db.scalar(select(func.count()).select_from(cls)), count
                )

    def test_new_settings_credentials_are_bounded_and_sanitized(self):
        a, token = self.register()
        invalid = self.request(
            "POST",
            "/v1/auth/password",
            token=token,
            json={"current_password": "sensitive-input", "new_password": "short"},
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertNotIn("sensitive-input", invalid.text)
        for path, method in (
            ("/v1/auth/password", "POST"),
            ("/v1/auth/account", "DELETE"),
        ):
            self.assertEqual(
                self.request(
                    method, path, token=token, json={"current_password": "x" * 5000}
                ).status_code,
                413,
            )

    def test_expired_sessions_hidden_and_settings_cannot_target_another_user(self):
        from app import models

        a, token = self.register("account-a")
        b, other = self.register("account-b")
        extra = self.request(
            "POST",
            "/v1/auth/login",
            json={"username": "account-a", "password": "A-long-test-password!"},
        ).cookies["f1_session"]
        from app.services.auth import token_hash

        with self.factory.begin() as db:
            db.scalar(
                select(models.AuthSession).where(
                    models.AuthSession.token_hash == token_hash(extra)
                )
            ).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.assertEqual(
            len(
                self.request("GET", "/v1/auth/account", token=token).json()["sessions"]
            ),
            1,
        )
        self.assertEqual(
            self.request(
                "POST",
                "/v1/auth/password",
                token=token,
                json={
                    "current_password": "A-long-test-password!",
                    "new_password": "Another-valid-password!",
                    "user_id": b["id"],
                },
            ).status_code,
            422,
        )
        self.assertEqual(
            self.request(
                "POST",
                "/v1/auth/password",
                token=other,
                json={
                    "current_password": "incorrect",
                    "new_password": "Another-valid-password!",
                },
            ).status_code,
            400,
        )
        for path, method, body in (
            ("/v1/auth/username", "PATCH", {"username": "fresh-name"}),
            (
                "/v1/auth/password",
                "POST",
                {
                    "current_password": "A-long-test-password!",
                    "new_password": "New-valid-password!",
                },
            ),
            ("/v1/auth/sessions/revoke-others", "POST", None),
            (
                "/v1/auth/account",
                "DELETE",
                {"current_password": "A-long-test-password!", "confirmation": "DELETE"},
            ),
        ):
            kwargs = {"json": body} if body else {}
            self.assertEqual(self.request(method, path, **kwargs).status_code, 401)
        self.assertEqual(
            self.request("GET", "/v1/auth/me", token=other).json()["username"],
            "account-b",
        )

    def test_settings_admission_rejection_prevents_writes(self):
        from fastapi import HTTPException

        from app.api.auth import admission

        a, token = self.register()

        def denied():
            raise HTTPException(
                429, "Account requests are busy", headers={"Retry-After": "5"}
            )

        self.app.dependency_overrides[admission] = denied
        for path, method, body in (
            ("/v1/auth/username", "PATCH", {"username": "fresh-name"}),
            (
                "/v1/auth/password",
                "POST",
                {
                    "current_password": "A-long-test-password!",
                    "new_password": "New-valid-password!",
                },
            ),
            ("/v1/auth/sessions/revoke-others", "POST", None),
            (
                "/v1/auth/account",
                "DELETE",
                {"current_password": "A-long-test-password!", "confirmation": "DELETE"},
            ),
        ):
            kwargs = {"json": body} if body else {}
            response = self.request(method, path, token=token, **kwargs)
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers["Retry-After"], "5")
        self.assertEqual(
            self.request("GET", "/v1/auth/me", token=token).json()["username"], "tester"
        )


@unittest.skipUnless(
    os.environ.get("F1_TEST_POSTGRES") == "1", "Isolated PostgreSQL settings checks"
)
class PostgresAccountSettingsTests(unittest.TestCase):
    request = auth_fixture.AuthTests.request
    register = auth_fixture.AuthTests.register

    def setUp(self):
        auth_fixture.PostgresAccountTests.setUp(self)
        from fastapi import Request
        from sqlalchemy.orm import sessionmaker

        from app.api.auth import admission, unsafe_request
        from app.api.core import database
        from app.main import app

        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.app = app

        def db():
            with self.factory() as db:
                yield db

        def allowed(request: Request):
            unsafe_request(request)
            yield

        app.dependency_overrides[database] = db
        app.dependency_overrides[admission] = allowed
        self.addCleanup(app.dependency_overrides.clear)

    def test_login_cannot_reissue_session_with_password_verified_before_a_change(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from unittest.mock import patch

        from sqlalchemy import delete, event

        from app import models
        from app.services.auth import hasher, verify_password

        a, token = self.register("locked-account")
        queried, verified = Event(), Event()

        def query_started(conn, cursor, statement, parameters, context, many):
            if "users.username =" in statement:
                queried.set()

        def checking(*args):
            verified.set()
            return verify_password(*args)

        event.listen(self.engine, "before_cursor_execute", query_started)
        self.addCleanup(
            event.remove, self.engine, "before_cursor_execute", query_started
        )
        with self.factory() as db:
            user = db.scalar(
                select(models.User)
                .where(models.User.id == UUID(a["id"]))
                .with_for_update()
            )
            user.password_hash = hasher.hash("A-new-test-password!")
            db.execute(
                delete(models.AuthSession).where(models.AuthSession.user_id == user.id)
            )
            with (
                ThreadPoolExecutor(max_workers=1) as pool,
                patch("app.api.auth.verify_password", side_effect=checking),
            ):
                future = pool.submit(
                    self.request,
                    "POST",
                    "/v1/auth/login",
                    json={
                        "username": "locked-account",
                        "password": "A-long-test-password!",
                    },
                )
                try:
                    self.assertTrue(queried.wait(5), "Login query did not start")
                    self.assertFalse(
                        verified.wait(0.2),
                        "Password verification ran before acquiring the account lock",
                    )
                finally:
                    db.commit()
                self.assertEqual(future.result(timeout=5).status_code, 401)

    def test_stale_authenticated_write_rechecks_session_after_revocation(self):
        from sqlalchemy import delete

        from app import models
        from app.services.auth import locked_session_user

        a, token = self.register("revoked-account")
        with self.factory() as stale:
            self.assertIsNotNone(stale.get(models.User, UUID(a["id"])))
            with self.factory.begin() as writer:
                writer.execute(
                    delete(models.AuthSession).where(
                        models.AuthSession.user_id == UUID(a["id"])
                    )
                )
            self.assertIsNone(locked_session_user(stale, token))


if __name__ == "__main__":
    unittest.main()
