"""Private references, owner isolation and non-destructive collection removal."""

import os
import unittest
from uuid import uuid4

import test_v2_auth as auth_fixture
from sqlalchemy import func, select


class WorkspaceTests(unittest.TestCase):
    setUp = auth_fixture.AuthTests.setUp
    request = auth_fixture.AuthTests.request
    register = auth_fixture.AuthTests.register

    def collection(self, token, title="Australia analysis"):
        response = self.request(
            "POST",
            "/v1/collections",
            token=token,
            json={"title": title, "description": "Recorded material"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def ref(self, kind):
        config = self.preset["configuration"]
        return {
            "reference_type": kind,
            "reference_id": config[
                {"event": "event_id", "session": "session_id", "driver": "driver_a_id"}[
                    kind
                ]
            ],
            "season": 2025,
        }

    def test_collection_crud_is_private_and_preserves_public_data(self):
        _, a = self.register("owner-a")
        _, b = self.register("owner-b")
        row = self.collection(a)
        path = "/v1/collections/" + row["id"]
        self.assertEqual(self.request("GET", "/v1/collections", token=b).json(), [])
        for method, kwargs in [
            ("GET", {}),
            ("PATCH", {"json": {"title": "stolen"}}),
            ("DELETE", {}),
        ]:
            forbidden = self.request(method, path, token=b, **kwargs)
            missing = self.request(
                method, "/v1/collections/" + str(uuid4()), token=b, **kwargs
            )
            self.assertEqual(forbidden.status_code, 404)
            self.assertEqual(forbidden.json(), missing.json())
        updated = self.request(
            "PATCH", path, token=a, json={"title": "Renamed", "description": "Updated"}
        )
        self.assertEqual(updated.json()["title"], "Renamed")
        self.assertEqual(updated.json()["description"], "Updated")
        self.assertEqual(self.request("DELETE", path, token=a).status_code, 204)
        self.assertEqual(self.request("GET", path, token=a).status_code, 404)
        self.assertEqual(
            self.request(
                "GET", "/v1/events/" + self.ref("event")["reference_id"]
            ).status_code,
            200,
        )

    def test_items_reopen_exact_context_duplicates_remove_and_isolation(self):
        _, a = self.register("owner-a")
        _, b = self.register("owner-b")
        row = self.collection(a)
        path = "/v1/collections/" + row["id"]
        for kind in ("event", "driver", "session"):
            ref = self.ref(kind)
            added = self.request("POST", path + "/items", token=a, json=ref)
            self.assertEqual(added.status_code, 201, added.text)
            item = added.json()
            self.assertIn("season=2025", item["open_url"])
            self.assertIn(ref["reference_id"], item["open_url"])
            repeated = self.request("POST", path + "/items", token=a, json=ref)
            self.assertEqual(repeated.status_code, 201)
            self.assertEqual(repeated.json()["id"], item["id"])
            self.assertEqual(
                self.request(
                    "DELETE", path + "/items/" + item["id"], token=b
                ).status_code,
                404,
            )
        detail = self.request("GET", path, token=a).json()
        self.assertEqual(detail["item_count"], 3)
        self.assertEqual(len(detail["items"]), 3)
        item = detail["items"][0]
        self.assertEqual(
            self.request("DELETE", path + "/items/" + item["id"], token=a).status_code,
            204,
        )
        self.assertEqual(self.request("GET", path, token=a).json()["item_count"], 2)

    def test_saved_comparison_reference_survives_deletion_without_leaking(self):
        _, a = self.register("owner-a")
        _, b = self.register("owner-b")
        comparison = self.request(
            "POST", "/v1/comparisons", token=a, json=self.preset
        ).json()
        path = "/v1/collections/" + self.collection(a)["id"]
        ref = {
            "reference_type": "comparison",
            "reference_id": comparison["id"],
            "season": 2025,
        }
        self.assertEqual(
            self.request(
                "POST",
                "/v1/collections/" + self.collection(b)["id"] + "/items",
                token=b,
                json=ref,
            ).status_code,
            422,
        )
        added = self.request("POST", path + "/items", token=a, json=ref)
        self.assertEqual(added.status_code, 201, added.text)
        self.assertIn(
            "/comparisons/" + comparison["id"] + "/open", added.json()["open_url"]
        )
        self.request("DELETE", "/v1/comparisons/" + comparison["id"], token=a)
        item = self.request("GET", path, token=a).json()["items"][0]
        self.assertEqual(item["availability"], "unavailable")
        self.assertEqual(item["reference_id"], comparison["id"])
        self.assertIsNone(item["open_url"])
        self.assertIn("unavailable", item["notices"][0])

    def test_favorite_unfavorite_driver_and_event_private_idempotent(self):
        _, a = self.register("owner-a")
        _, b = self.register("owner-b")
        for kind in ("driver", "event"):
            response = self.request(
                "POST", "/v1/favorites", token=a, json=self.ref(kind)
            )
            self.assertEqual(response.status_code, 201, response.text)
            row = response.json()
            repeat = self.request("POST", "/v1/favorites", token=a, json=self.ref(kind))
            self.assertEqual(repeat.json()["id"], row["id"])
            self.assertEqual(self.request("GET", "/v1/favorites", token=b).json(), [])
            self.assertEqual(
                self.request(
                    "DELETE", "/v1/favorites/" + row["id"], token=b
                ).status_code,
                404,
            )
            own = self.request(
                "GET",
                "/v1/favorites",
                token=a,
                params={
                    "reference_type": kind,
                    "reference_id": self.ref(kind)["reference_id"],
                },
            )
            self.assertEqual(len(own.json()), 1)
            self.assertEqual(
                self.request(
                    "DELETE", "/v1/favorites/" + row["id"], token=a
                ).status_code,
                204,
            )
        self.assertEqual(self.request("GET", "/v1/favorites", token=a).json(), [])

    def test_validation_csrf_auth_and_missing_records(self):
        _, token = self.register()
        path = "/v1/collections/" + self.collection(token)["id"]
        for invalid in (
            {"title": "  "},
            {"title": "x" * 121},
            {"title": "x", "user_id": str(uuid4())},
        ):
            self.assertEqual(
                self.request(
                    "POST", "/v1/collections", token=token, json=invalid
                ).status_code,
                422,
            )
        for invalid in (
            {**self.ref("event"), "season": 2024},
            {**self.ref("session"), "reference_id": str(uuid4())},
            {**self.ref("driver"), "reference_type": "telemetry"},
        ):
            self.assertEqual(
                self.request(
                    "POST", path + "/items", token=token, json=invalid
                ).status_code,
                422,
            )
        self.assertEqual(
            self.request(
                "POST", "/v1/favorites", token=token, json=self.ref("session")
            ).status_code,
            422,
        )
        self.assertEqual(
            self.request(
                "POST",
                "/v1/collections",
                token=token,
                guarded=False,
                json={"title": "x"},
            ).status_code,
            403,
        )
        for url in ("/v1/collections", "/v1/favorites"):
            self.assertEqual(self.request("GET", url).status_code, 401)
            self.assertEqual(
                self.request(
                    "POST",
                    url,
                    json={"title": "x"} if "collections" in url else self.ref("event"),
                ).status_code,
                401,
            )
        self.assertEqual(
            self.request(
                "GET", "/v1/drivers/" + self.ref("driver")["reference_id"]
            ).status_code,
            200,
        )

    def test_private_mutations_keep_admission_and_pagination_bounded(self):
        from fastapi import HTTPException

        from app.api.auth import admission

        _, token = self.register()
        path = "/v1/collections/" + self.collection(token)["id"]
        self.collection(token, "Second collection")
        first = self.request(
            "GET", "/v1/collections", token=token, params={"limit": 1}
        ).json()
        second = self.request(
            "GET", "/v1/collections", token=token, params={"limit": 1, "offset": 1}
        ).json()
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first[0]["id"], second[0]["id"])
        self.assertEqual(
            self.request(
                "GET", "/v1/favorites", token=token, params={"limit": 201}
            ).status_code,
            422,
        )

        def exhausted():
            raise HTTPException(429, "Bounded", headers={"Retry-After": "60"})

        self.app.dependency_overrides[admission] = exhausted
        for method, url, body in [
            ("POST", "/v1/collections", {"title": "Blocked"}),
            ("PATCH", path, {"title": "Blocked"}),
            ("DELETE", path, None),
            ("POST", path + "/items", self.ref("event")),
            ("DELETE", path + "/items/" + str(uuid4()), None),
            ("POST", "/v1/favorites", self.ref("driver")),
            ("DELETE", "/v1/favorites/" + str(uuid4()), None),
        ]:
            response = self.request(
                method, url, token=token, **({"json": body} if body is not None else {})
            )
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers["Retry-After"], "60")
        self.assertNotEqual(
            self.request("GET", path, token=token).json()["title"], "Blocked"
        )

    def test_account_deletion_removes_only_owned_workspace_and_presets(self):
        from app import models

        _, a = self.register("owner-a")
        _, b = self.register("owner-b")
        for token in (a, b):
            path = "/v1/collections/" + self.collection(token)["id"]
            self.request("POST", path + "/items", token=token, json=self.ref("event"))
            self.request("POST", "/v1/favorites", token=token, json=self.ref("driver"))
        self.assertEqual(
            self.request(
                "DELETE",
                "/v1/auth/account",
                token=a,
                json={
                    "current_password": "A-long-test-password!",
                    "confirmation": "DELETE",
                },
            ).status_code,
            204,
        )
        self.assertEqual(len(self.request("GET", "/v1/collections", token=b).json()), 1)
        self.assertEqual(len(self.request("GET", "/v1/favorites", token=b).json()), 1)
        with self.factory() as db:
            for model in (models.Collection, models.CollectionItem, models.Favorite):
                self.assertEqual(db.scalar(select(func.count()).select_from(model)), 1)
            self.assertIsNotNone(db.get(models.Session, self.session_id))


@unittest.skipUnless(os.environ.get("F1_TEST_POSTGRES") == "1", "Isolated PostgreSQL")
class PostgresWorkspaceTests(unittest.TestCase):
    setUp = auth_fixture.PostgresAccountTests.setUp
    request = auth_fixture.AuthTests.request
    register = auth_fixture.AuthTests.register

    def test_model_migration_and_owner_constraints(self):
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm import Session

        from app import models

        with self.engine.begin() as conn:
            conn.execute(text(f'SET LOCAL search_path TO "{self.schema}"'))
            self.assertEqual(
                compare_metadata(
                    MigrationContext.configure(conn), models.Base.metadata
                ),
                [],
            )
        with Session(self.engine) as db:
            a = models.User(username="workspace-a", password_hash="test-only-hash")
            b = models.User(username="workspace-b", password_hash="test-only-hash")
            db.add_all([a, b])
            db.flush()
            collection = models.Collection(user_id=a.id, title="Private")
            db.add(collection)
            db.commit()
            collection_id = collection.id
            self.assertEqual(
                db.scalars(
                    select(models.Collection).where(models.Collection.user_id == b.id)
                ).all(),
                [],
            )
            db.add(models.Collection(user_id=uuid4(), title="Invalid owner"))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()
            db.execute(models.User.__table__.delete().where(models.User.id == a.id))
            db.commit()
            self.assertIsNone(db.get(models.Collection, collection_id))

    def test_postgres_api_ownership_and_overlapping_duplicate_adds(self):
        from concurrent.futures import ThreadPoolExecutor

        from fastapi import Request
        from sqlalchemy.orm import sessionmaker

        from app import models
        from app.api.auth import admission, unsafe_request
        from app.api.core import database
        from app.main import app

        self.app = app
        factory = sessionmaker(self.engine)

        def database_override():
            with factory() as db:
                yield db

        def guarded(request: Request):
            unsafe_request(request)
            yield

        app.dependency_overrides[database] = database_override
        app.dependency_overrides[admission] = guarded
        self.addCleanup(app.dependency_overrides.clear)
        with factory.begin() as db:
            season = models.Season(year=2025)
            driver = models.Driver(given_name="Recorded", family_name="Driver")
            db.add_all([season, driver])
            db.flush()
            reference = {
                "reference_type": "driver",
                "reference_id": str(driver.id),
                "season": 2025,
            }
        _, a = self.register("postgres-a")
        _, b = self.register("postgres-b")
        collection = self.request(
            "POST", "/v1/collections", token=a, json={"title": "Private"}
        ).json()
        path = "/v1/collections/" + collection["id"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: self.request(
                        "POST", path + "/items", token=a, json=reference
                    ),
                    range(2),
                )
            )
        self.assertTrue(all(r.status_code == 201 for r in responses))
        self.assertEqual(responses[0].json()["id"], responses[1].json()["id"])
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: self.request(
                        "POST", "/v1/favorites", token=a, json=reference
                    ),
                    range(2),
                )
            )
        self.assertTrue(all(r.status_code == 201 for r in responses))
        favorite_id = responses[0].json()["id"]
        self.assertEqual(favorite_id, responses[1].json()["id"])
        self.assertEqual(self.request("GET", path, token=b).status_code, 404)
        self.assertEqual(
            self.request("PATCH", path, token=b, json={"title": "Other"}).status_code,
            404,
        )
        self.assertEqual(
            self.request("POST", path + "/items", token=b, json=reference).status_code,
            404,
        )
        self.assertEqual(self.request("GET", "/v1/favorites", token=b).json(), [])
        self.assertEqual(
            self.request("DELETE", "/v1/favorites/" + favorite_id, token=b).status_code,
            404,
        )
        self.assertEqual(
            self.request(
                "DELETE",
                "/v1/auth/account",
                token=a,
                json={
                    "current_password": "A-long-test-password!",
                    "confirmation": "DELETE",
                },
            ).status_code,
            204,
        )
        self.assertEqual(
            self.request("GET", "/v1/drivers/" + reference["reference_id"]).status_code,
            200,
        )
