"""Comprehensive test suite for the Centralized Security Service (TSK-057).

Tests:
- Integration of TSK-054 authentication without logic duplication.
- Integration of TSK-055 RBAC without logic duplication.
- Integration of TSK-056 MQTT security configuration without modification.
- Reusable FastAPI dependencies (authenticated, require_roles, require_admin, require_ack, require_notification_write).
- Strict separation of the technical identity `system` from human roles.
- Correct differentiation between 401 (Authentication) and 403 (Authorization).
- Safe configuration exposure without leaking secrets (jwt_secret_key, mqtt_password).
- QoS schedulers (FIFO, Round Robin, WFQ) and telemetry remain independent.
"""

from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

os.environ["JWT_SECRET_KEY"] = "test-only-secret-with-32-plus-bytes!!"
os.environ["JWT_EXPIRE_MINUTES"] = "60"
os.environ["MQTT_USERNAME"] = "backend_test"
os.environ["MQTT_PASSWORD"] = "mqtt_secret_test"
os.environ["MQTT_TLS"] = "true"
os.environ["MQTT_CA_CERT"] = "mock/ca.crt"

import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.password import hash_password
from app.auth.service import AuthService
from app.auth.tokens import create_access_token
from app.config.backend_config import BackendConfig
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import (
    HUMAN_USER_ROLES,
    TECHNICAL_USER_ROLE,
    UserORM,
)
from app.database.infrastructure.repositories import UserRepository
from app.database.infrastructure.session import get_db
from app.security import (
    AuthenticatedUser,
    SafeSecurityConfig,
    SecurityService,
    authenticated,
    get_current_user,
    get_mqtt_security_context,
    get_safe_security_config,
    get_safe_security_config_dep,
    get_security_service,
    require_ack,
    require_admin,
    require_auditor_or_above,
    require_notification_write,
    require_roles,
)


def _make_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


class SecurityServiceUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Session = _make_session_factory()
        cls.user_repo = UserRepository()
        cls.auth_service = AuthService(cls.user_repo)
        cls.security_service = SecurityService(
            auth_service=cls.auth_service,
            user_repo=cls.user_repo,
        )

        with cls.Session() as db:
            cls.admin_user = UserORM(
                id=uuid.uuid4(),
                name="Admin User",
                email="admin@test.local",
                password_hash=hash_password("admin_pass"),
                role="admin",
                is_active=True,
            )
            cls.supervisor_user = UserORM(
                id=uuid.uuid4(),
                name="Supervisor User",
                email="sup@test.local",
                password_hash=hash_password("sup_pass"),
                role="supervisor",
                is_active=True,
            )
            cls.operador_user = UserORM(
                id=uuid.uuid4(),
                name="Operador User",
                email="op@test.local",
                password_hash=hash_password("op_pass"),
                role="operador",
                is_active=True,
            )
            cls.auditor_user = UserORM(
                id=uuid.uuid4(),
                name="Auditor User",
                email="aud@test.local",
                password_hash=hash_password("aud_pass"),
                role="auditor",
                is_active=True,
            )
            cls.inactive_user = UserORM(
                id=uuid.uuid4(),
                name="Inactive User",
                email="inactive@test.local",
                password_hash=hash_password("inactive_pass"),
                role="operador",
                is_active=False,
            )
            cls.system_user = UserORM(
                id=uuid.uuid4(),
                name="System Tech",
                email="system@test.local",
                password_hash=hash_password("system_pass"),
                role="system",
                is_active=True,
            )
            db.add_all([
                cls.admin_user,
                cls.supervisor_user,
                cls.operador_user,
                cls.auditor_user,
                cls.inactive_user,
                cls.system_user,
            ])
            db.commit()

    def test_authenticate_http_valid_token(self):
        token, _ = create_access_token(self.admin_user.id, self.admin_user.role)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        with self.Session() as db:
            user = self.security_service.authenticate_http(creds, db)
            self.assertEqual(user.id, self.admin_user.id)
            self.assertEqual(user.role, "admin")
            self.assertTrue(user.is_active)

    def test_authenticate_http_missing_credentials(self):
        with self.Session() as db:
            with self.assertRaises(HTTPException) as ctx:
                self.security_service.authenticate_http(None, db)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertEqual(ctx.exception.detail, "Not authenticated")

    def test_authenticate_http_invalid_token_format(self):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid-token-string")
        with self.Session() as db:
            with self.assertRaises(HTTPException) as ctx:
                self.security_service.authenticate_http(creds, db)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertEqual(ctx.exception.detail, "Invalid token")

    def test_authenticate_http_expired_token(self):
        # Create an already expired token
        secret = os.environ["JWT_SECRET_KEY"]
        payload = {
            "sub": str(self.admin_user.id),
            "role": "admin",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=10),
            "iat": datetime.now(timezone.utc) - timedelta(minutes=30),
        }
        token = jwt.encode(payload, secret, algorithm="HS256")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        with self.Session() as db:
            with self.assertRaises(HTTPException) as ctx:
                self.security_service.authenticate_http(creds, db)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertEqual(ctx.exception.detail, "Token has expired")

    def test_authenticate_http_inactive_user_rejected(self):
        token, _ = create_access_token(self.inactive_user.id, self.inactive_user.role)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        with self.Session() as db:
            with self.assertRaises(HTTPException) as ctx:
                self.security_service.authenticate_http(creds, db)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertEqual(ctx.exception.detail, "User is inactive")

    def test_technical_system_identity_rejected_by_http_authentication(self):
        token, _ = create_access_token(self.system_user.id, self.system_user.role)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        with self.Session() as db:
            with self.assertRaises(HTTPException) as ctx:
                self.security_service.authenticate_http(creds, db)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertEqual(ctx.exception.detail, "Invalid token")

    def test_technical_system_identity_never_authorized_for_human_roles(self):
        system_user = AuthenticatedUser(
            id=self.system_user.id,
            email=self.system_user.email,
            name=self.system_user.name,
            role="system",
            is_active=True,
        )
        with self.assertRaises(HTTPException) as ctx:
            self.security_service.authorize(system_user, ["admin"])
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, "Forbidden")

        # Also verify with is_authorized
        self.assertFalse(self.security_service.is_authorized(system_user, ["admin", "operador"]))

    def test_authorize_success_and_forbidden_differentiation(self):
        operador = AuthenticatedUser(
            id=self.operador_user.id,
            email=self.operador_user.email,
            name=self.operador_user.name,
            role="operador",
            is_active=True,
        )
        # Operador allowed in require_ack roles
        ack_roles = ("admin", "supervisor", "operador")
        result = self.security_service.authorize(operador, ack_roles)
        self.assertEqual(result.id, operador.id)
        self.assertTrue(self.security_service.is_authorized(operador, ack_roles))

        # Operador denied in admin-only
        with self.assertRaises(HTTPException) as ctx:
            self.security_service.authorize(operador, ["admin"])
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, "Forbidden")
        self.assertFalse(self.security_service.is_authorized(operador, ["admin"]))

    def test_authorize_fails_closed_on_unknown_roles(self):
        user = AuthenticatedUser(
            id=self.admin_user.id,
            email=self.admin_user.email,
            name=self.admin_user.name,
            role="admin",
            is_active=True,
        )
        with self.assertRaises(ValueError):
            self.security_service.authorize(user, ["superuser"])

        with self.assertRaises(ValueError):
            self.security_service.authorize(user, [])

        with self.assertRaises(ValueError):
            require_roles("invalid_role")

        with self.assertRaises(ValueError):
            require_roles()

    def test_safe_security_config_does_not_leak_secrets(self):
        safe_cfg = self.security_service.get_safe_config()
        self.assertIsInstance(safe_cfg, SafeSecurityConfig)
        data = safe_cfg.to_dict()

        # Non-sensitive settings are present
        self.assertEqual(data["jwt_algorithm"], "HS256")
        self.assertEqual(data["jwt_expire_minutes"], 60)
        self.assertTrue(data["jwt_secret_configured"])
        self.assertEqual(data["mqtt_port"], 8883)
        self.assertTrue(data["mqtt_tls_enabled"])
        self.assertTrue(data["mqtt_ca_cert_configured"])
        self.assertTrue(data["mqtt_auth_configured"])
        self.assertEqual(data["human_roles"], ["admin", "auditor", "operador", "supervisor"])
        self.assertEqual(data["technical_role"], "system")

        # Secrets must NOT be present
        self.assertNotIn("jwt_secret_key", data)
        self.assertNotIn("mqtt_password", data)
        self.assertNotIn("test-only-secret-with-32-plus-bytes!!", str(data))
        self.assertNotIn("mqtt_secret_test", str(data))

    def test_validate_mqtt_security_integration(self):
        mqtt_ctx = self.security_service.validate_mqtt_security()
        self.assertIsInstance(mqtt_ctx, dict)
        self.assertEqual(mqtt_ctx["port"], 8883)
        self.assertTrue(mqtt_ctx["tls_enabled"])
        self.assertTrue(mqtt_ctx["has_credentials"])
        self.assertEqual(mqtt_ctx["username"], "backend_test")
        self.assertTrue(mqtt_ctx["verified"])
        self.assertNotIn("mqtt_secret_test", str(mqtt_ctx))


class ProtectedEndpointsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Session = _make_session_factory()
        with cls.Session() as db:
            cls.admin = UserORM(
                id=uuid.uuid4(),
                name="Admin User",
                email="admin@app.local",
                password_hash=hash_password("pw"),
                role="admin",
                is_active=True,
            )
            cls.supervisor = UserORM(
                id=uuid.uuid4(),
                name="Supervisor User",
                email="sup@app.local",
                password_hash=hash_password("pw"),
                role="supervisor",
                is_active=True,
            )
            cls.operador = UserORM(
                id=uuid.uuid4(),
                name="Operador User",
                email="op@app.local",
                password_hash=hash_password("pw"),
                role="operador",
                is_active=True,
            )
            cls.auditor = UserORM(
                id=uuid.uuid4(),
                name="Auditor User",
                email="aud@app.local",
                password_hash=hash_password("pw"),
                role="auditor",
                is_active=True,
            )
            cls.inactive = UserORM(
                id=uuid.uuid4(),
                name="Inactive User",
                email="inact@app.local",
                password_hash=hash_password("pw"),
                role="admin",
                is_active=False,
            )
            cls.system = UserORM(
                id=uuid.uuid4(),
                name="System Tech",
                email="sys@app.local",
                password_hash=hash_password("pw"),
                role="system",
                is_active=True,
            )
            db.add_all([cls.admin, cls.supervisor, cls.operador, cls.auditor, cls.inactive, cls.system])
            db.commit()

        app = FastAPI()

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

        @app.get("/api/authenticated-only", dependencies=[Depends(authenticated)])
        def get_auth_only(current: AuthenticatedUser = Depends(authenticated)):
            return {"user": current.email, "role": current.role}

        @app.get("/api/admin-only", dependencies=[Depends(require_admin)])
        def get_admin_only():
            return {"status": "admin_granted"}

        @app.post("/api/ack", dependencies=[Depends(require_ack)])
        def post_ack():
            return {"status": "ack_processed"}

        @app.post("/api/notifications/manage", dependencies=[Depends(require_notification_write)])
        def post_notifications_write():
            return {"status": "notification_saved"}

        @app.get("/api/audit", dependencies=[Depends(require_auditor_or_above)])
        def get_audit():
            return {"status": "audit_granted"}

        @app.get("/api/security-config")
        def get_config(cfg: SafeSecurityConfig = Depends(get_safe_security_config_dep)):
            return cfg.to_dict()

        cls.client = TestClient(app)

    def _token(self, user: UserORM) -> str:
        token, _ = create_access_token(user.id, user.role)
        return token

    def test_unauthenticated_request_returns_401(self):
        resp = self.client.get("/api/authenticated-only")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["detail"], "Not authenticated")

    def test_invalid_token_returns_401(self):
        resp = self.client.get(
            "/api/authenticated-only",
            headers={"Authorization": "Bearer not-a-valid-token"},
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["detail"], "Invalid token")

    def test_inactive_user_returns_401(self):
        token = self._token(self.inactive)
        resp = self.client.get(
            "/api/authenticated-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["detail"], "User is inactive")

    def test_system_technical_identity_returns_401_on_http(self):
        token = self._token(self.system)
        resp = self.client.get(
            "/api/authenticated-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["detail"], "Invalid token")

    def test_any_active_human_can_access_authenticated_endpoint(self):
        for user in [self.admin, self.supervisor, self.operador, self.auditor]:
            token = self._token(user)
            resp = self.client.get(
                "/api/authenticated-only",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["role"], user.role)

    def test_rbac_admin_only_endpoint(self):
        # Admin succeeds
        admin_token = self._token(self.admin)
        resp = self.client.get(
            "/api/admin-only",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)

        # Supervisor, operador, auditor get 403 Forbidden
        for user in [self.supervisor, self.operador, self.auditor]:
            token = self._token(user)
            resp = self.client.get(
                "/api/admin-only",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(resp.json()["detail"], "Forbidden")

    def test_rbac_ack_endpoint(self):
        # Admin, supervisor, operador pass
        for user in [self.admin, self.supervisor, self.operador]:
            token = self._token(user)
            resp = self.client.post(
                "/api/ack",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(resp.status_code, 200)

        # Auditor gets 403 Forbidden
        auditor_token = self._token(self.auditor)
        resp = self.client.post(
            "/api/ack",
            headers={"Authorization": f"Bearer {auditor_token}"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], "Forbidden")

    def test_rbac_notification_write_endpoint(self):
        # Admin, supervisor pass
        for user in [self.admin, self.supervisor]:
            token = self._token(user)
            resp = self.client.post(
                "/api/notifications/manage",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(resp.status_code, 200)

        # Operador and auditor get 403 Forbidden
        for user in [self.operador, self.auditor]:
            token = self._token(user)
            resp = self.client.post(
                "/api/notifications/manage",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(resp.status_code, 403)

    def test_safe_security_config_endpoint(self):
        resp = self.client.get("/api/security-config")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["jwt_algorithm"], "HS256")
        self.assertIn("admin", data["human_roles"])
        self.assertNotIn("jwt_secret_key", data)
        self.assertNotIn("mqtt_password", data)


class PipelineIndependenceTests(unittest.TestCase):
    """Verify that classification and QoS pipeline modules have no security coupling."""

    def test_qos_schedulers_independent_of_security(self):
        from app.qos.application.fifo_scheduler import FIFOScheduler
        from app.qos.application.round_robin_scheduler import RoundRobinScheduler
        from app.qos.application.wfq_scheduler import WFQScheduler

        fifo = FIFOScheduler()
        rr = RoundRobinScheduler()
        wfq = WFQScheduler()

        self.assertIsNotNone(fifo)
        self.assertIsNotNone(rr)
        self.assertIsNotNone(wfq)

        # schedulers operate strictly on domain packets/queues without auth
        self.assertFalse(hasattr(fifo, "security_service"))
        self.assertFalse(hasattr(rr, "security_service"))
        self.assertFalse(hasattr(wfq, "security_service"))

    def test_normalizer_independent_of_security(self):
        from app.acquisition.normalizer import TelemetryNormalizer

        normalizer = TelemetryNormalizer()
        self.assertIsNotNone(normalizer)
        self.assertFalse(hasattr(normalizer, "security_service"))


if __name__ == "__main__":
    unittest.main()
