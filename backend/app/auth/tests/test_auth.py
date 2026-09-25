"""TSK-054 authentication tests (unittest + isolated FastAPI app)."""

from __future__ import annotations

import os
import unittest
import uuid

os.environ["JWT_SECRET_KEY"] = "test-only-secret-with-32-plus-bytes!!"
os.environ["JWT_EXPIRE_MINUTES"] = "60"

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.api import router as auth_router
from app.auth.dependencies import get_current_user
from app.auth.password import hash_password, verify_password
from app.auth.service import AuthService, InvalidCredentialsError
from app.auth.tokens import create_access_token, decode_token
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import UserORM
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


class PasswordTestCase(unittest.TestCase):
    def test_hash_is_not_plaintext(self):
        hashed = hash_password("s3cret-pass")
        self.assertNotEqual(hashed, "s3cret-pass")
        self.assertTrue(hashed.startswith("$2"))

    def test_verify_correct_and_incorrect(self):
        hashed = hash_password("s3cret-pass")
        self.assertTrue(verify_password("s3cret-pass", hashed))
        self.assertFalse(verify_password("wrong-pass", hashed))

    def test_verify_legacy_placeholder_never_passes(self):
        self.assertFalse(verify_password("anything", "!"))
        self.assertFalse(verify_password("", hash_password("x")))
        with self.assertRaises(ValueError):
            hash_password("")


class ServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.Session = _make_session_factory()
        self.service = AuthService()

    def _create(self, email="ana@example.com", password="s3cret-pass", **kw):
        with self.Session() as db:
            user = self.service.create_user(
                db, name="Ana", email=email, password=password, role="admin", **kw
            )
            db.commit()
            db.refresh(user)
            return user.id

    def test_create_stores_hash(self):
        uid = self._create()
        with self.Session() as db:
            user = self.service.get_user(db, uid)
            self.assertNotEqual(user.password_hash, "s3cret-pass")
            self.assertTrue(verify_password("s3cret-pass", user.password_hash))
            self.assertTrue(user.is_active)

    def test_authenticate_ok(self):
        self._create()
        with self.Session() as db:
            user = self.service.authenticate(db, email="ana@example.com", password="s3cret-pass")
            self.assertEqual(user.email, "ana@example.com")

    def test_authenticate_email_normalized(self):
        self._create()
        with self.Session() as db:
            user = self.service.authenticate(db, email="  ANA@EXAMPLE.COM ", password="s3cret-pass")
            self.assertEqual(user.email, "ana@example.com")

    def test_authenticate_failures_are_indistinguishable(self):
        self._create()
        with self.Session() as db:
            for email, password in [
                ("nobody@example.com", "s3cret-pass"),
                ("ana@example.com", "wrong-pass"),
            ]:
                with self.assertRaises(InvalidCredentialsError) as ctx:
                    self.service.authenticate(db, email=email, password=password)
                self.assertEqual(str(ctx.exception), "invalid credentials")

    def test_authenticate_inactive_rejected(self):
        uid = self._create()
        with self.Session() as db:
            user = self.service.get_user(db, uid)
            self.service.set_active(db, user, False)
            db.commit()
        with self.Session() as db:
            with self.assertRaises(InvalidCredentialsError):
                self.service.authenticate(db, email="ana@example.com", password="s3cret-pass")

    def test_authenticate_system_identity_rejected(self):
        with self.Session() as db:
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
            with self.assertRaises(InvalidCredentialsError):
                self.service.authenticate(
                    db, email="system@coldchain.local", password="!"
                )

    def test_management_update_and_password_change(self):
        uid = self._create()
        with self.Session() as db:
            user = self.service.get_user(db, uid)
            self.service.update_user(db, user, name="Ana Ruiz")
            self.service.change_password(db, user, "nueva-clave-9")
            db.commit()
        with self.Session() as db:
            user = self.service.authenticate(
                db, email="ana@example.com", password="nueva-clave-9"
            )
            self.assertEqual(user.name, "Ana Ruiz")


class TokenTestCase(unittest.TestCase):
    def setUp(self):
        self.Session = _make_session_factory()
        self.service = AuthService()
        with self.Session() as db:
            user = self.service.create_user(
                db, name="Ana", email="ana@example.com", password="s3cret-pass", role="operador"
            )
            db.commit()
            db.refresh(user)
            self.uid = user.id

    def test_token_identifies_user_and_role(self):
        token, expires_in = create_access_token(self.uid, "operador")
        self.assertGreater(expires_in, 0)
        payload = decode_token(token)
        self.assertEqual(payload["sub"], str(self.uid))
        self.assertEqual(payload["role"], "operador")
        self.assertIn("exp", payload)
        self.assertIn("iat", payload)
        self.assertNotIn("password_hash", payload)

    def test_tampered_token_rejected(self):
        token, _ = create_access_token(self.uid, "operador")
        with self.assertRaises(jwt.InvalidTokenError):
            decode_token(token + "tampered")

    def test_expired_token_rejected(self):
        token, _ = create_access_token(self.uid, "operador", expires_minutes=-1)
        with self.assertRaises(jwt.ExpiredSignatureError):
            decode_token(token)


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.Session = _make_session_factory()
        self.service = AuthService()
        with self.Session() as db:
            self.service.create_user(
                db, name="Ana", email="ana@example.com", password="s3cret-pass", role="admin"
            )
            self.service.create_user(
                db, name="Beto", email="beto@example.com", password="beto-pass-1", role="auditor"
            )
            db.commit()
        app = FastAPI()
        app.include_router(auth_router)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        # get_current_user uses get_db internally, so the override applies.
        self.client = TestClient(app)

    def _login(self, email="ana@example.com", password="s3cret-pass"):
        return self.client.post("/auth/login", json={"email": email, "password": password})

    def test_login_ok_returns_token_without_hash(self):
        r = self._login()
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("access_token", body)
        self.assertEqual(body["token_type"], "bearer")
        self.assertGreater(body["expires_in"], 0)
        self.assertNotIn("password_hash", body)

    def test_login_failures_share_generic_message(self):
        bodies = set()
        for email, password in [
            ("nobody@example.com", "s3cret-pass"),
            ("ana@example.com", "wrong-pass"),
        ]:
            r = self.client.post("/auth/login", json={"email": email, "password": password})
            self.assertEqual(r.status_code, 401)
            bodies.add(r.json()["detail"])
        self.assertEqual(bodies, {"Invalid credentials"})

    def test_login_inactive_shares_generic_message(self):
        with self.Session() as db:
            user = self.service._users.get_by_email(db, "ana@example.com")
            self.service.set_active(db, user, False)
            db.commit()
        r = self._login()
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["detail"], "Invalid credentials")

    def test_me_returns_token_owner_with_role(self):
        token = self._login().json()["access_token"]
        r = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["email"], "ana@example.com")
        self.assertEqual(body["role"], "admin")
        self.assertTrue(body["is_active"])
        self.assertNotIn("password_hash", body)

    def test_me_ignores_client_user_id(self):
        # There is no user_id field: identity always comes from the token.
        token = self.client.post(
            "/auth/login", json={"email": "beto@example.com", "password": "beto-pass-1"}
        ).json()["access_token"]
        r = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.json()["email"], "beto@example.com")

    def test_me_missing_invalid_expired_rejected(self):
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        r = self.client.get("/auth/me", headers={"Authorization": "Bearer not-a-token"})
        self.assertEqual(r.status_code, 401)
        with self.Session() as db:
            user = self.service._users.get_by_email(db, "ana@example.com")
            token, _ = create_access_token(user.id, user.role, expires_minutes=-1)
        r = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 401)

    def test_deactivated_token_holder_rejected(self):
        token = self._login().json()["access_token"]
        with self.Session() as db:
            user = self.service._users.get_by_email(db, "ana@example.com")
            self.service.set_active(db, user, False)
            db.commit()
        r = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 401)


class SecretConfigTestCase(unittest.TestCase):
    def test_missing_secret_fails_clearly(self):
        from app.config import BackendConfig

        config = BackendConfig(jwt_secret_key="")
        old = os.environ.pop("JWT_SECRET_KEY", None)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                config.require_jwt_secret()
            self.assertIn("JWT_SECRET_KEY", str(ctx.exception))
        finally:
            if old is not None:
                os.environ["JWT_SECRET_KEY"] = old


if __name__ == "__main__":
    unittest.main()
