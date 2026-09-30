"""Integration tests for TSK-059.1's immutable audit API."""

from __future__ import annotations

import os
import unittest

os.environ["JWT_SECRET_KEY"] = "test-only-secret-with-32-plus-bytes!!"
os.environ["JWT_EXPIRE_MINUTES"] = "60"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.audit.api import router as audit_router
from app.auth.service import AuthService
from app.auth.tokens import create_access_token
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import AuditLogORM
from app.database.infrastructure.session import get_db
from app.users.api import router as users_router


class AuditApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(engine)
        cls.Session = sessionmaker(bind=engine, future=True)
        cls.ids = {}
        with cls.Session() as db:
            service = AuthService()
            for name, email, role in [
                ("Admin", "admin@example.com", "admin"),
                ("Auditor", "auditor@example.com", "auditor"),
                ("Operator", "operator@example.com", "operador"),
            ]:
                user = service.create_user(
                    db, name=name, email=email, password="pass-1234", role=role
                )
                cls.ids[role] = user.id
            db.commit()

    def setUp(self):
        app = FastAPI()
        app.include_router(users_router)
        app.include_router(audit_router)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def _headers(self, role: str):
        with self.Session() as db:
            user = AuthService().get_user(db, self.ids[role])
            token, _ = create_access_token(user.id, user.role)
        return {"Authorization": f"Bearer {token}"}

    def test_successful_user_actions_are_recorded_atomically(self):
        response = self.client.post(
            "/users",
            headers=self._headers("admin"),
            json={
                "name": "New User",
                "email": "new@example.com",
                "password": "new-pass-1",
                "role": "operador",
            },
        )
        self.assertEqual(response.status_code, 201)
        user_id = response.json()["id"]

        response = self.client.patch(
            f"/users/{user_id}",
            headers=self._headers("admin"),
            json={"name": "Renamed User"},
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            f"/users/{user_id}/password",
            headers=self._headers("admin"),
            json={"new_password": "rotated-password-1"},
        )
        self.assertEqual(response.status_code, 200)

        with self.Session() as db:
            entries = db.query(AuditLogORM).order_by(AuditLogORM.created_at).all()
            self.assertEqual([entry.action for entry in entries], [
                "user.create", "user.update", "user.password_reset",
            ])
            self.assertTrue(all(entry.actor_user_id == self.ids["admin"] for entry in entries))
            self.assertTrue(all(entry.resource == f"users/{user_id}" for entry in entries))
            self.assertTrue(all(entry.outcome == "success" for entry in entries))

    def test_failed_user_operation_does_not_create_a_success_audit_entry(self):
        with self.Session() as db:
            before = db.query(AuditLogORM).count()
        response = self.client.post(
            "/users",
            headers=self._headers("admin"),
            json={
                "name": "Duplicate",
                "email": "admin@example.com",
                "password": "new-pass-1",
                "role": "operador",
            },
        )
        self.assertEqual(response.status_code, 409)
        with self.Session() as db:
            self.assertEqual(db.query(AuditLogORM).count(), before)

    def test_auditor_and_admin_can_read_but_no_one_can_write(self):
        for role in ("auditor", "admin"):
            response = self.client.get("/audit-logs", headers=self._headers(role))
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("password", str(response.json()).lower())
        self.assertEqual(self.client.get("/audit-logs").status_code, 401)
        self.assertEqual(
            self.client.get("/audit-logs", headers=self._headers("operador")).status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/audit-logs", headers=self._headers("auditor")).status_code,
            405,
        )
        self.assertEqual(
            self.client.patch("/audit-logs/anything", headers=self._headers("auditor")).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
