"""TSK-059.5 — alert.acknowledge persistence + audit, notification audits."""

from __future__ import annotations

import json
import os
import unittest
import uuid
from datetime import datetime, timezone

os.environ["JWT_SECRET_KEY"] = "test-only-secret-with-32-plus-bytes!!"
os.environ["JWT_EXPIRE_MINUTES"] = "60"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.auth.service import AuthService
from app.auth.tokens import create_access_token
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import AlertORM, AuditLogORM, DeviceORM
from app.database.infrastructure.session import get_db
from app.events.domain import Alert
from app.history.api.router import router as history_router
from app.notifications.api import router as notifications_router
from app.notifications.domain import Notification, NotificationChannel, NotificationStatus


class AckAuditTests(unittest.TestCase):
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
                ("Supervisor", "sup@example.com", "supervisor"),
                ("Operator", "op@example.com", "operador"),
                ("Auditor", "aud@example.com", "auditor"),
            ]:
                user = service.create_user(
                    db, name=name, email=email, password="pass-1234", role=role
                )
                cls.ids[role] = user.id
            device = DeviceORM(
                code="CAVA-ACK", name="Cava", location="Lab",
                device_type="cold_room", status="active",
            )
            db.add(device)
            db.commit()
            cls.device_id = device.id

    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(notifications_router)
        self.app.include_router(history_router)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self._role = "admin"
        self.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=self.ids[self._role],
            email=f"{self._role}@example.com",
            name=self._role.title(),
            role=self._role,
            is_active=True,
        )
        self.app.state.alerts = []
        self.app.state.notifications = []
        self.client = TestClient(self.app)

    def _headers(self):
        return {"Authorization": f"Bearer {self._token()}"}

    def _token(self):
        with self.Session() as db:
            user = AuthService().get_user(db, self.ids[self._role])
            token, _ = create_access_token(user.id, user.role)
        return token

    def _as(self, role):
        self._role = role
        self.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=self.ids[role],
            email=f"{role}@example.com",
            name=role.title(),
            role=role,
            is_active=True,
        )

    def _seed_alert(self, acknowledged=False):
        alert_id = uuid.uuid4()
        with self.Session() as db:
            db.add(
                AlertORM(
                    id=alert_id,
                    device_id=self.device_id,
                    user_id=self.ids["admin"],
                    type="TEMPERATURE_EXCEEDED",
                    message="too warm",
                    criticality=8.0,
                    acknowledged=acknowledged,
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
        self.app.state.alerts.append(
            Alert(
                id=alert_id,
                device_id=self.device_id,
                user_id=self.ids["admin"],
                type="TEMPERATURE_EXCEEDED",
                message="too warm",
                criticality=8.0,
                acknowledged=acknowledged,
                created_at=datetime.now(timezone.utc),
            )
        )
        return alert_id

    def _audit(self, action):
        with self.Session() as db:
            return db.query(AuditLogORM).filter_by(action=action).order_by(AuditLogORM.created_at).all()

    # --- acknowledge ------------------------------------------------------

    def test_ack_persists_and_audits_first_time(self):
        alert_id = self._seed_alert(acknowledged=False)
        before = len(self._audit("alert.acknowledge"))
        r = self.client.post(f"/notifications/alerts/{alert_id}/acknowledge", headers=self._headers())
        assert r.status_code == 200, r.text
        with self.Session() as db:
            row = db.query(AlertORM).filter_by(id=alert_id).first()
            assert row.acknowledged is True
        rows = self._audit("alert.acknowledge")
        assert len(rows) == before + 1
        assert json.loads(rows[-1].old_value) == {"acknowledged": False}
        assert json.loads(rows[-1].new_value) == {"acknowledged": True}
        assert rows[-1].resource == f"alerts/{alert_id}"
        assert str(rows[-1].actor_user_id) == str(self.ids["admin"])
        # history reflects persistence
        h = self.client.get(f"/history/alerts/{alert_id}", headers=self._headers())
        assert h.status_code == 200, h.text
        assert h.json()["acknowledged"] is True

    def test_ack_idempotent_second_time_nulls(self):
        alert_id = self._seed_alert(acknowledged=False)
        self.client.post(f"/notifications/alerts/{alert_id}/acknowledge", headers=self._headers())
        before = len(self._audit("alert.acknowledge"))
        r = self.client.post(f"/notifications/alerts/{alert_id}/acknowledge", headers=self._headers())
        assert r.status_code == 200, r.text
        rows = self._audit("alert.acknowledge")
        assert len(rows) == before + 1
        assert rows[-1].old_value is None and rows[-1].new_value is None

    def test_ack_forbidden_leaves_no_audit_or_change(self):
        alert_id = self._seed_alert(acknowledged=False)
        before = len(self._audit("alert.acknowledge"))
        self._as("auditor")
        r = self.client.post(f"/notifications/alerts/{alert_id}/acknowledge", headers=self._headers())
        assert r.status_code == 403, r.text
        assert len(self._audit("alert.acknowledge")) == before
        with self.Session() as db:
            assert db.query(AlertORM).filter_by(id=alert_id).first().acknowledged is False

    def test_ack_missing_alert_404_no_audit(self):
        before = len(self._audit("alert.acknowledge"))
        r = self.client.post(
            f"/notifications/alerts/{uuid.uuid4()}/acknowledge", headers=self._headers()
        )
        assert r.status_code == 404, r.text
        assert len(self._audit("alert.acknowledge")) == before

    # --- notifications -----------------------------------------------------

    def test_process_audited(self):
        alert_id = self._seed_alert(acknowledged=False)
        before = len(self._audit("notification.process"))
        r = self.client.post(
            "/notifications/process", json={"alert_id": str(alert_id)}, headers=self._headers()
        )
        assert r.status_code == 201, r.text
        rows = self._audit("notification.process")
        assert len(rows) == before + 1
        assert rows[-1].resource.startswith("notifications/")
        assert rows[-1].old_value is None and rows[-1].new_value is None

    def test_status_change_audited_with_old_new(self):
        alert_id = self._seed_alert(acknowledged=False)
        r = self.client.post(
            "/notifications/process", json={"alert_id": str(alert_id)}, headers=self._headers()
        )
        notif_id = r.json()["notification"]["id"]
        # process() delivers immediately, so the stored status is already sent
        before = len(self._audit("notification.status"))
        r = self.client.patch(
            f"/notifications/{notif_id}/status", json={"status": "failed"}, headers=self._headers()
        )
        assert r.status_code == 200, r.text
        rows = self._audit("notification.status")
        assert len(rows) == before + 1
        assert json.loads(rows[-1].old_value) == {"status": "sent"}
        assert json.loads(rows[-1].new_value) == {"status": "failed"}
        assert rows[-1].resource == f"notifications/{notif_id}"

    def test_status_invalid_no_audit(self):
        alert_id = self._seed_alert(acknowledged=False)
        r = self.client.post(
            "/notifications/process", json={"alert_id": str(alert_id)}, headers=self._headers()
        )
        notif_id = r.json()["notification"]["id"]
        before = len(self._audit("notification.status"))
        r = self.client.patch(
            f"/notifications/{notif_id}/status", json={"status": "bogus"}, headers=self._headers()
        )
        assert r.status_code == 400, r.text
        assert len(self._audit("notification.status")) == before

    def test_status_forbidden_no_audit(self):
        notif = Notification(
            id=uuid.uuid4(),
            alert_id=uuid.uuid4(),
            channel=NotificationChannel.DASHBOARD,
            status=NotificationStatus.PENDING,
            notification_date=datetime.now(timezone.utc),
        )
        self.app.state.notifications.append(notif)
        before = len(self._audit("notification.status"))
        self._as("operador")
        r = self.client.patch(
            f"/notifications/{notif.id}/status", json={"status": "sent"}, headers=self._headers()
        )
        assert r.status_code == 403, r.text
        assert len(self._audit("notification.status")) == before


if __name__ == "__main__":
    unittest.main()
