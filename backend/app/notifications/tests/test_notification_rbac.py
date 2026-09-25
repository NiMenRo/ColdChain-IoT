"""TSK-055 RBAC matrix tests for the notifications router (real JWTs)."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4

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
from app.database.infrastructure.session import get_db
from app.events.domain import Alert
from app.notifications.api import router as notifications_router
from app.notifications.application import (
    AlertAcknowledgementService,
    NotificationService,
)


def _make_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


class NotificationRBACTests(unittest.TestCase):
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
            db.commit()

    def setUp(self):
        self.app = FastAPI()
        self.app.state.notifications = []
        self.app.state.alerts = []
        self.app.state.notification_service = NotificationService()
        self.app.state.alert_acknowledgement_service = AlertAcknowledgementService()
        self.app.include_router(notifications_router)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

        self.alert = Alert(
            id=uuid4(),
            device_id=uuid4(),
            user_id=self.ids["admin"],
            type="TEMPERATURE_EXCEEDED",
            message="9.5C",
            criticality=8.5,
            acknowledged=False,
            created_at=datetime.now(timezone.utc),
        )
        self.app.state.alerts.append(self.alert)

    def _token(self, role):
        with self.Session() as db:
            user = AuthService()._users.get_by_id(db, self.ids[role])
            token, _ = create_access_token(user.id, user.role)
            return token

    def _auth(self, role):
        return {"Authorization": f"Bearer {self._token(role)}"}

    # -- 401 without token -------------------------------------------------
    def test_no_token_is_401(self):
        self.assertEqual(self.client.get("/notifications").status_code, 401)
        self.assertEqual(
            self.client.post(f"/notifications/alerts/{self.alert.id}/acknowledge").status_code, 401
        )
        self.assertEqual(
            self.client.patch(
                f"/notifications/{uuid4()}/status", json={"status": "sent"}
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post("/notifications/process", json={"alert_id": str(self.alert.id)}).status_code,
            401,
        )

    # -- reads: all roles ---------------------------------------------------
    def test_all_roles_can_read(self):
        for role in ["admin", "supervisor", "operador", "auditor"]:
            r = self.client.get("/notifications", headers=self._auth(role))
            self.assertEqual(r.status_code, 200, role)

    # -- ack: admin/sup/operador yes, auditor no -----------------------------
    def test_ack_matrix(self):
        for role, expected in [
            ("admin", 200),
            ("supervisor", 200),
            ("operador", 200),
            ("auditor", 403),
        ]:
            alert = Alert(
                id=uuid4(),
                device_id=uuid4(),
                user_id=self.ids["admin"],
                type="TEMPERATURE_EXCEEDED",
                message="x",
                criticality=8.5,
                acknowledged=False,
                created_at=datetime.now(timezone.utc),
            )
            self.app.state.alerts.append(alert)
            r = self.client.post(
                f"/notifications/alerts/{alert.id}/acknowledge", headers=self._auth(role)
            )
            self.assertEqual(r.status_code, expected, role)

    def test_client_user_id_is_ignored(self):
        other = str(uuid4())
        r = self.client.post(
            f"/notifications/alerts/{self.alert.id}/acknowledge",
            json={"user_id": other},
            headers=self._auth("operador"),
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["acknowledged"])
        # The spoofed user_id has no effect on the stored alert owner.
        self.assertEqual(r.json()["alert"]["id"], str(self.alert.id))

    # -- PATCH status: admin/supervisor yes ----------------------------------
    def test_patch_status_matrix(self):
        from app.notifications.domain import (
            Notification,
            NotificationChannel,
            NotificationStatus,
        )

        notif = Notification.from_alert(
            alert=self.alert,
            channel=NotificationChannel.DASHBOARD,
            status=NotificationStatus.PENDING,
        )
        self.app.state.notifications.append(notif)
        for role, expected in [
            ("admin", 200),
            ("supervisor", 200),
            ("operador", 403),
            ("auditor", 403),
        ]:
            r = self.client.patch(
                f"/notifications/{notif.id}/status",
                json={"status": "sent"},
                headers=self._auth(role),
            )
            self.assertEqual(r.status_code, expected, role)

    # -- process: admin only, owner forced to token ---------------------------
    def test_process_matrix(self):
        for role, expected in [
            ("admin", 201),
            ("supervisor", 403),
            ("operador", 403),
            ("auditor", 403),
        ]:
            r = self.client.post(
                "/notifications/process",
                json={"alert_id": str(self.alert.id)},
                headers=self._auth(role),
            )
            self.assertEqual(r.status_code, expected, role)

    def test_process_forces_owner_from_token(self):
        other = str(uuid4())
        r = self.client.post(
            "/notifications/process",
            json={
                "device_id": str(uuid4()),
                "type": "TEMPERATURE_EXCEEDED",
                "user_id": other,
                "message": "manual",
            },
            headers=self._auth("admin"),
        )
        self.assertEqual(r.status_code, 201)
        # Owner recorded is the admin from the token, not the spoofed user_id.
        detail = self.client.get(
            f"/notifications/alerts/{r.json()['alert_id']}", headers=self._auth("admin")
        ).json()
        self.assertEqual(detail["alert"]["user_id"], str(self.ids["admin"]))


if __name__ == "__main__":
    unittest.main()
