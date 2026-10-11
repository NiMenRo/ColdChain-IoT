"""Fase C — persistent history, unread counter and read state (owner-scoped).

Covers: owner isolation (own rows only, foreign ids -> 404), persistent
history filters, unread-count accuracy, mark read / read-all idempotency,
read-vs-acknowledge independence, POST /process persistence + duplicate +
force-redispatch + DB recovery, 401 without token, and real-JWT access for
all human roles.
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4

os.environ["JWT_SECRET_KEY"] = "test-only-secret-with-32-plus-bytes!!"
os.environ["JWT_EXPIRE_MINUTES"] = "60"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.auth.service import AuthService
from app.auth.tokens import create_access_token
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import AlertORM, DeviceORM, UserORM
from app.database.infrastructure.session import get_db
from app.events.domain import Alert
from app.notifications.api import router as notifications_router
from app.notifications.application import (
    AlertAcknowledgementService,
    DashboardNotificationChannel,
    NotificationChannelRegistry,
    NotificationChannelSender,
    NotificationManager,
    NotificationSendRequest,
    NotificationService,
)


class FailingDashboardChannel(NotificationChannelSender):
    from app.notifications.domain import NotificationChannel as _Ch

    channel = _Ch.DASHBOARD

    def _deliver(self, request: NotificationSendRequest) -> str:
        raise RuntimeError("transport down")


def _engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, connection_record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    return engine


class PersistentReadAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = _engine()
        self.Session = sessionmaker(bind=self.engine, future=True)
        with self.Session() as db:
            self.owner = UserORM(name="Owner", email="owner@example.com",
                                 password_hash="h", role="admin")
            self.other = UserORM(name="Other", email="other@example.com",
                                 password_hash="h", role="operador")
            db.add_all([self.owner, self.other])
            db.flush()
            self.device = DeviceORM(code="CAVA-001", name="Cava", location="Lab",
                                    device_type="cold_room", status="active")
            db.add(self.device)
            db.flush()
            self.alert_row = AlertORM(
                device_id=self.device.id, user_id=self.owner.id,
                type="TEMPERATURE_EXCEEDED", message="Too warm", criticality=8.0,
                acknowledged=False, created_at=datetime.now(timezone.utc))
            db.add(self.alert_row)
            db.commit()
            self.owner_id, self.other_id = self.owner.id, self.other.id
            self.device_id, self.alert_id = self.device.id, self.alert_row.id

        self.app = FastAPI()
        self.app.state.notifications = []
        self.app.state.alerts = []
        self.app.state.notification_service = NotificationService()
        self.app.state.alert_acknowledgement_service = AlertAcknowledgementService()
        self.app.include_router(notifications_router)
        self._act_as(self.owner_id, "owner@example.com", "Owner", "admin")

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

        # Runtime mirror of the persisted alert (ack endpoints are memory-based).
        self.app.state.alerts.append(Alert(
            id=self.alert_id, device_id=self.device_id, user_id=self.owner_id,
            type="TEMPERATURE_EXCEEDED", message="Too warm", criticality=8.0,
            acknowledged=False, created_at=datetime.now(timezone.utc)))

    def tearDown(self) -> None:
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _act_as(self, user_id, email, name, role):
        self.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=user_id, email=email, name=name, role=role, is_active=True)

    def _dispatch(self, **body):
        payload = {"alert_id": str(self.alert_id)}
        payload.update(body)
        return self.client.post("/notifications/process", json=payload)

    # -- persistent history & unread counter ---------------------------------

    def test_empty_history_and_zero_unread(self):
        r = self.client.get("/notifications/persistent")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"count": 0, "notifications": []})
        r = self.client.get("/notifications/unread-count")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"unread": 0})

    def test_process_persists_and_counts_unread(self):
        r = self._dispatch()
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertTrue(data["success"])
        self.assertFalse(data["duplicate"])
        self.assertTrue(data["persisted"])

        r = self.client.get("/notifications/persistent")
        body = r.json()
        self.assertEqual(body["count"], 1)
        notif = body["notifications"][0]
        self.assertFalse(notif["is_read"])
        self.assertIsNone(notif["read_at"])
        self.assertIsNotNone(notif["alert"])
        self.assertEqual(notif["alert"]["id"], str(self.alert_id))

        r = self.client.get("/notifications/unread-count")
        self.assertEqual(r.json(), {"unread": 1})

    def test_history_is_owner_scoped(self):
        self.assertEqual(self._dispatch().status_code, 201)
        self._act_as(self.other_id, "other@example.com", "Other", "operador")
        self.assertEqual(
            self.client.get("/notifications/persistent").json(),
            {"count": 0, "notifications": []})
        self.assertEqual(
            self.client.get("/notifications/unread-count").json(), {"unread": 0})

    def test_history_filters(self):
        self.assertEqual(self._dispatch().status_code, 201)
        nid = self.client.get("/notifications/persistent").json()["notifications"][0]["id"]
        aid = str(self.alert_id)
        self.assertEqual(
            self.client.get("/notifications/persistent",
                            params={"status": "sent"}).json()["count"], 1)
        self.assertEqual(
            self.client.get("/notifications/persistent",
                            params={"status": "failed"}).json()["count"], 0)
        self.assertEqual(
            self.client.get("/notifications/persistent",
                            params={"channel": "dashboard"}).json()["count"], 1)
        self.assertEqual(
            self.client.get("/notifications/persistent",
                            params={"channel": "sms"}).json()["count"], 0)
        self.assertEqual(
            self.client.get("/notifications/persistent",
                            params={"is_read": "false"}).json()["count"], 1)
        self.assertEqual(
            self.client.get("/notifications/persistent",
                            params={"is_read": "true"}).json()["count"], 0)
        self.assertEqual(
            self.client.get("/notifications/persistent",
                            params={"alert_id": aid}).json()["count"], 1)
        self.assertEqual(
            self.client.get("/notifications/persistent",
                            params={"limit": 1}).json()["count"], 1)
        self.assertEqual(nid[:8], nid[:8])  # id present and stable
        for params, code in [({"status": "nope"}, 400), ({"channel": "nope"}, 400),
                             ({"is_read": "maybe"}, 400), ({"limit": 0}, 400),
                             ({"limit": 201}, 400),
                             ({"alert_id": "not-a-uuid"}, 400)]:
            self.assertEqual(
                self.client.get("/notifications/persistent", params=params).status_code,
                code, params)

    # -- read state ------------------------------------------------------------

    def test_mark_read_and_idempotency(self):
        self.assertEqual(self._dispatch().status_code, 201)
        nid = self.client.get("/notifications/persistent").json()["notifications"][0]["id"]

        r = self.client.patch(f"/notifications/{nid}/read")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["notification"]["is_read"])
        self.assertIsNotNone(r.json()["notification"]["read_at"])
        self.assertEqual(self.client.get("/notifications/unread-count").json(),
                         {"unread": 0})
        # Idempotent repeat keeps working and keeps the timestamp.
        first = r.json()["notification"]["read_at"]
        r = self.client.patch(f"/notifications/{nid}/read")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["notification"]["read_at"], first)

        self._act_as(self.other_id, "other@example.com", "Other", "operador")
        self.assertEqual(
            self.client.patch(f"/notifications/{nid}/read").status_code, 404)
        self.assertEqual(
            self.client.patch(f"/notifications/{uuid4()}/read").status_code, 404)
        self.assertEqual(
            self.client.patch("/notifications/not-a-uuid/read").status_code, 400)

    def test_read_all(self):
        self.assertEqual(self._dispatch().status_code, 201)
        self.assertEqual(self._dispatch().status_code, 201)  # duplicate, no new row
        r = self.client.post("/notifications/read-all")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"updated": 1})
        self.assertEqual(self.client.get("/notifications/unread-count").json(),
                         {"unread": 0})
        self.assertEqual(self.client.post("/notifications/read-all").json(),
                         {"updated": 0})

    def test_read_and_acknowledge_are_independent(self):
        self.assertEqual(self._dispatch().status_code, 201)
        nid = self.client.get("/notifications/persistent").json()["notifications"][0]["id"]

        # Acknowledge the alert: is_read must NOT change.
        r = self.client.post(f"/notifications/alerts/{self.alert_id}/acknowledge")
        self.assertEqual(r.status_code, 200)
        notif = self.client.get("/notifications/persistent").json()["notifications"][0]
        self.assertFalse(notif["is_read"])
        self.assertTrue(notif["alert"]["acknowledged"])

        # Mark the notification read: alert stays acknowledged (untouched by read).
        self.assertEqual(self.client.patch(f"/notifications/{nid}/read").status_code, 200)
        notif = self.client.get("/notifications/persistent").json()["notifications"][0]
        self.assertTrue(notif["is_read"])
        self.assertTrue(notif["alert"]["acknowledged"])

    # -- process semantics -----------------------------------------------------

    def test_duplicate_process_does_not_resend(self):
        first = self._dispatch()
        self.assertTrue(first.json()["success"])
        second = self._dispatch()
        data = second.json()
        self.assertEqual(second.status_code, 201)
        self.assertTrue(data["duplicate"])
        self.assertTrue(data["persisted"])
        self.assertEqual(
            self.client.get("/notifications/persistent").json()["count"], 1)

    def test_force_redispatch_updates_failed_row(self):
        self.app.state.notification_service = NotificationService(
            manager=NotificationManager(default_channel="dashboard"),
            channel_registry=NotificationChannelRegistry(
                channels=[FailingDashboardChannel()]))
        failed = self._dispatch()
        self.assertEqual(failed.status_code, 201)
        self.assertFalse(failed.json()["success"])

        # Repair the channel, then redispatch with force: same row adopts SENT.
        self.app.state.notification_service = NotificationService()
        redelivered = self._dispatch(force=True)
        data = redelivered.json()
        self.assertEqual(redelivered.status_code, 201)
        self.assertTrue(data["redelivered"])
        body = self.client.get("/notifications/persistent").json()
        self.assertEqual(body["count"], 1)  # still a single row, no duplicate
        self.assertEqual(body["notifications"][0]["status"], "sent")

    def test_force_on_delivered_row_is_409(self):
        self.assertTrue(self._dispatch().json()["success"])
        r = self._dispatch(force=True)
        self.assertEqual(r.status_code, 409)

    def test_process_recovers_alert_from_db_after_restart(self):
        # Simulate a restart: runtime lists are empty, the alert row survives.
        self.app.state.alerts.clear()
        self.app.state.notifications.clear()
        r = self._dispatch()
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["persisted"])
        body = self.client.get("/notifications/persistent").json()
        self.assertEqual(body["count"], 1)
        # Ownership preserved from the alert row (owner, not someone else).
        with self.Session() as db:
            from app.database.infrastructure.models import NotificationORM
            row = db.query(NotificationORM).first()
            self.assertEqual(row.user_id, self.owner_id)

    # -- auth ------------------------------------------------------------------

    def test_new_endpoints_require_auth(self):
        del self.app.dependency_overrides[get_current_user]
        self.assertEqual(self.client.get("/notifications/persistent").status_code, 401)
        self.assertEqual(self.client.get("/notifications/unread-count").status_code, 401)
        self.assertEqual(
            self.client.patch(f"/notifications/{uuid4()}/read").status_code, 401)
        self.assertEqual(self.client.post("/notifications/read-all").status_code, 401)


class PersistentReadRoleTests(unittest.TestCase):
    """Real-JWT access: every human role can use the read API on own rows."""

    @classmethod
    def setUpClass(cls):
        cls.engine = _engine()
        cls.Session = sessionmaker(bind=cls.engine, future=True)
        svc = AuthService()
        cls.ids = {}
        with cls.Session() as db:
            for name, email, role in [
                ("Admin", "r-admin@example.com", "admin"),
                ("Sup", "r-sup@example.com", "supervisor"),
                ("Ope", "r-ope@example.com", "operador"),
                ("Audi", "r-audi@example.com", "auditor"),
            ]:
                user = svc.create_user(
                    db, name=name, email=email, password="pass-1234", role=role)
                cls.ids[role] = user.id
            db.commit()

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

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

    def _token(self, role):
        with self.Session() as db:
            user = AuthService()._users.get_by_id(db, self.ids[role])
            token, _ = create_access_token(user.id, user.role)
            return token

    def test_all_roles_read_own_scope(self):
        for role in ["admin", "supervisor", "operador", "auditor"]:
            headers = {"Authorization": f"Bearer {self._token(role)}"}
            self.assertEqual(
                self.client.get("/notifications/persistent", headers=headers).status_code,
                200, role)
            self.assertEqual(
                self.client.get("/notifications/unread-count", headers=headers).status_code,
                200, role)
            self.assertEqual(
                self.client.post("/notifications/read-all", headers=headers).status_code,
                200, role)
