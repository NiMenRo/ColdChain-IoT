"""TSK-055 authorization tests (centralized RBAC layer)."""

from __future__ import annotations

import os
import unittest

os.environ["JWT_SECRET_KEY"] = "test-only-secret-with-32-plus-bytes!!"
os.environ["JWT_EXPIRE_MINUTES"] = "60"

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.authorization import (
    authenticated,
    require_admin,
    require_roles,
)
from app.auth.dependencies import get_current_user
from app.auth.service import AuthService
from app.auth.tokens import create_access_token
from app.database.infrastructure.base import Base
from app.database.infrastructure.session import get_db


def _make_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def _build_app(session_factory):
    app = FastAPI()

    @app.get("/open-auth", dependencies=[Depends(authenticated)])
    def open_auth():
        return {"ok": True}

    @app.get("/admin-only", dependencies=[Depends(require_admin)])
    def admin_only():
        return {"ok": True}

    @app.post("/ack", dependencies=[Depends(require_roles("admin", "supervisor", "operador"))])
    def ack():
        return {"ok": True}

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


class AuthorizationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Session = _make_session_factory()
        svc = AuthService()
        with cls.Session() as db:
            for name, email, role in [
                ("Admin", "admin@example.com", "admin"),
                ("Sup", "sup@example.com", "supervisor"),
                ("Ope", "ope@example.com", "operador"),
                ("Audi", "audi@example.com", "auditor"),
            ]:
                svc.create_user(
                    db, name=name, email=email, password="pass-1234", role=role
                )
            db.commit()
        cls.client = _build_app(cls.Session)

    def _token(self, email, password="pass-1234"):
        with self.Session() as db:
            user = AuthService().authenticate(db, email=email, password=password)
            token, _ = create_access_token(user.id, user.role)
            return token

    def _auth(self, email):
        return {"Authorization": f"Bearer {self._token(email)}"}

    def test_missing_token_is_401_not_403(self):
        for path, method in [("/open-auth", "get"), ("/admin-only", "get"), ("/ack", "post")]:
            r = getattr(self.client, method)(path)
            self.assertEqual(r.status_code, 401, path)

    def test_invalid_token_is_401(self):
        r = self.client.get("/admin-only", headers={"Authorization": "Bearer junk"})
        self.assertEqual(r.status_code, 401)

    def test_any_role_passes_authenticated_only(self):
        for email in ["admin@example.com", "sup@example.com", "ope@example.com", "audi@example.com"]:
            r = self.client.get("/open-auth", headers=self._auth(email))
            self.assertEqual(r.status_code, 200, email)

    def test_admin_only(self):
        self.assertEqual(
            self.client.get("/admin-only", headers=self._auth("admin@example.com")).status_code, 200
        )
        for email in ["sup@example.com", "ope@example.com", "audi@example.com"]:
            r = self.client.get("/admin-only", headers=self._auth(email))
            self.assertEqual(r.status_code, 403, email)

    def test_ack_roles(self):
        for email in ["admin@example.com", "sup@example.com", "ope@example.com"]:
            r = self.client.post("/ack", headers=self._auth(email))
            self.assertEqual(r.status_code, 200, email)
        r = self.client.post("/ack", headers=self._auth("audi@example.com"))
        self.assertEqual(r.status_code, 403)

    def test_unknown_role_fails_closed(self):
        with self.assertRaises(ValueError):
            require_roles("superadmin")
        with self.assertRaises(ValueError):
            require_roles("system")
        with self.assertRaises(ValueError):
            require_roles()


if __name__ == "__main__":
    unittest.main()
