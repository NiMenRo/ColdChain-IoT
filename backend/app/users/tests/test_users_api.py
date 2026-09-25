"""TSK-055 user management tests (admin-only endpoints)."""

from __future__ import annotations

import os
import unittest
import uuid

os.environ["JWT_SECRET_KEY"] = "test-only-secret-with-32-plus-bytes!!"
os.environ["JWT_EXPIRE_MINUTES"] = "60"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.service import AuthService
from app.auth.tokens import create_access_token
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import UserORM
from app.database.infrastructure.session import get_db
from app.users.api import router as users_router


def _make_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


class UsersApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Session = _make_session_factory()
        svc = AuthService()
        cls.ids = {}
        with cls.Session() as db:
            for name, email, role in [
                ("Admin", "admin@example.com", "admin"),
                ("Sup", "sup@example.com", "supervisor"),
                ("Ope", "ope@example.com", "operador"),
                ("Audi", "audi@example.com", "auditor"),
            ]:
                user = svc.create_user(
                    db, name=name, email=email, password="pass-1234", role=role
                )
                cls.ids[role] = user.id
            db.add(
                UserORM(
                    id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
                    name="system",
                    email="system@coldchain.local",
                    password_hash="!",
                    role="system",
                    is_active=True,
                )
            )
            db.commit()

    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(users_router)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

    def _token(self, role):
        with self.Session() as db:
            user = AuthService()._users.get_by_id(db, self.ids[role])
            token, _ = create_access_token(user.id, user.role)
            return token

    def _auth(self, role):
        return {"Authorization": f"Bearer {self._token(role)}"}

    # -- authn/z -------------------------------------------------------------
    def test_no_token_is_401(self):
        self.assertEqual(self.client.get("/users").status_code, 401)
        self.assertEqual(self.client.post("/users", json={}).status_code, 401)

    def test_non_admin_is_403(self):
        for role in ["supervisor", "operador", "auditor"]:
            r = self.client.get("/users", headers=self._auth(role))
            self.assertEqual(r.status_code, 403, role)
            r = self.client.post(
                "/users",
                json={"name": "X", "email": "x@example.com", "password": "pass-1234", "role": "operador"},
                headers=self._auth(role),
            )
            self.assertEqual(r.status_code, 403, role)

    # -- admin CRUD ------------------------------------------------------------
    def test_admin_lists_and_reads_without_hash(self):
        r = self.client.get("/users", headers=self._auth("admin"))
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["total"], 4)
        for item in r.json()["results"]:
            self.assertNotIn("password_hash", item)
        uid = self.ids["operador"]
        r = self.client.get(f"/users/{uid}", headers=self._auth("admin"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["email"], "ope@example.com")
        r = self.client.get(f"/users/{uuid.uuid4()}", headers=self._auth("admin"))
        self.assertEqual(r.status_code, 404)

    def test_admin_creates_user_hashed(self):
        r = self.client.post(
            "/users",
            json={"name": "New", "email": "new@example.com", "password": "new-pass-1", "role": "operador"},
            headers=self._auth("admin"),
        )
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["email"], "new@example.com")
        self.assertNotIn("password_hash", body)
        with self.Session() as db:
            user = AuthService()._users.get_by_email(db, "new@example.com")
            self.assertTrue(user.password_hash.startswith("$2"))
        # duplicate email -> 409
        r = self.client.post(
            "/users",
            json={"name": "Dup", "email": "new@example.com", "password": "new-pass-1", "role": "operador"},
            headers=self._auth("admin"),
        )
        self.assertEqual(r.status_code, 409)
        # invalid role -> 400
        r = self.client.post(
            "/users",
            json={"name": "Bad", "email": "bad@example.com", "password": "new-pass-1", "role": "viewer"},
            headers=self._auth("admin"),
        )
        self.assertEqual(r.status_code, 400)

    def test_admin_updates_and_deactivates(self):
        uid = self.ids["operador"]
        r = self.client.patch(
            f"/users/{uid}", json={"role": "supervisor"}, headers=self._auth("admin")
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["role"], "supervisor")
        # restore
        self.client.patch(f"/users/{uid}", json={"role": "operador"}, headers=self._auth("admin"))
        r = self.client.patch(
            f"/users/{uid}", json={"is_active": False}, headers=self._auth("admin")
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["is_active"])
        # deactivated user token is rejected even on admin routes
        token = self._token("operador")
        r = self.client.get(
            "/users", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(r.status_code, 401)
        # reactivate for other tests
        self.client.patch(f"/users/{uid}", json={"is_active": True}, headers=self._auth("admin"))

    def test_admin_cannot_change_own_role(self):
        uid = self.ids["admin"]
        r = self.client.patch(
            f"/users/{uid}", json={"role": "operador"}, headers=self._auth("admin")
        )
        self.assertEqual(r.status_code, 403)

    def test_system_user_untouchable(self):
        sys_id = "00000000-0000-0000-0000-000000000000"
        r = self.client.patch(
            f"/users/{sys_id}", json={"name": "hacked"}, headers=self._auth("admin")
        )
        self.assertEqual(r.status_code, 403)
        r = self.client.post(
            f"/users/{sys_id}/password",
            json={"new_password": "x"},
            headers=self._auth("admin"),
        )
        self.assertEqual(r.status_code, 403)

    def test_admin_resets_password(self):
        uid = self.ids["auditor"]
        r = self.client.post(
            f"/users/{uid}/password",
            json={"new_password": "rotated-99"},
            headers=self._auth("admin"),
        )
        self.assertEqual(r.status_code, 200)
        with self.Session() as db:
            user = AuthService().authenticate(
                db, email="audi@example.com", password="rotated-99"
            )
            self.assertEqual(user.id, uid)
        # restore original password for other tests
        with self.Session() as db:
            user = AuthService()._users.get_by_id(db, uid)
            AuthService().change_password(db, user, "pass-1234")
            db.commit()


if __name__ == "__main__":
    unittest.main()
