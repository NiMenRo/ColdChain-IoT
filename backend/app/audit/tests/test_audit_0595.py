"""TSK-059.5 — audit old/new, user.update, password secrecy, system-config audit."""

from __future__ import annotations

import json
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

from app.audit.api import router as audit_router
from app.audit.service import AuditService
from app.auth.service import AuthService
from app.auth.tokens import create_access_token
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import AuditLogORM, SystemConfigORM
from app.database.infrastructure.repositories import AuditLogRepository
from app.database.infrastructure.session import get_db
from app.system_config.api import router as system_config_router
from app.users.api import router as users_router


class Audit0595Tests(unittest.TestCase):
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
            db.add(
                SystemConfigORM(
                    min_temperature=0.0,
                    max_temperature=4.0,
                    min_humidity=85.0,
                    max_humidity=90.0,
                    qos_algorithm="wfq",
                    qos_enabled=True,
                )
            )
            db.commit()

    def setUp(self):
        app = FastAPI()
        app.include_router(users_router)
        app.include_router(audit_router)
        app.include_router(system_config_router)

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

    def _audit_rows(self, action=None):
        with self.Session() as db:
            q = db.query(AuditLogORM).order_by(AuditLogORM.created_at)
            if action:
                q = q.filter_by(action=action)
            return q.all()

    # --- old/new plumbing -------------------------------------------------

    def test_old_new_nullable_and_exposed(self):
        with self.Session() as db:
            AuditService().record(
                db,
                actor_user_id=self.ids["admin"],
                action="probe.noop",
                resource="probe/1",
                old_value={"a": 1},
                new_value=None,
            )
            db.commit()
        rows = self._audit_rows("probe.noop")
        assert rows[-1].old_value == json.dumps({"a": 1}, sort_keys=True)
        assert rows[-1].new_value is None
        body = self.client.get("/audit-logs", headers=self._headers("auditor")).json()
        probe = [r for r in body["results"] if r["action"] == "probe.noop"][-1]
        assert probe["old_value"] == json.dumps({"a": 1}, sort_keys=True)
        assert probe["new_value"] is None

    def test_forbidden_keys_raise(self):
        with self.Session() as db:
            repo = AuditLogRepository()
            for bad in ("password", "new_password", "password_hash", "hash", "token", "secret"):
                with self.assertRaises(ValueError):
                    repo.create(
                        db,
                        actor_user_id=self.ids["admin"],
                        action="probe.bad",
                        resource="probe/1",
                        new_value={bad: "x"},
                    )
                with self.assertRaises(ValueError):
                    repo.create(
                        db,
                        actor_user_id=self.ids["admin"],
                        action="probe.bad",
                        resource="probe/1",
                        new_value={"outer": {bad: "x"}},
                    )
            db.rollback()

    def test_audit_api_still_read_only(self):
        assert self.client.post("/audit-logs", headers=self._headers("admin")).status_code == 405
        assert self.client.patch("/audit-logs/anything", headers=self._headers("admin")).status_code == 404

    # --- user.update -------------------------------------------------------

    def test_user_update_records_old_new(self):
        with self.Session() as db:
            target = AuthService().create_user(
                db, name="Target", email="target@example.com", password="pass-1234", role="auditor"
            )
            db.commit()
            target_id = target.id
        before = len(self._audit_rows("user.update"))
        r = self.client.patch(
            f"/users/{target_id}",
            json={"role": "operador"},
            headers=self._headers("admin"),
        )
        assert r.status_code == 200, r.text
        rows = self._audit_rows("user.update")
        assert len(rows) == before + 1
        row = rows[-1]
        assert json.loads(row.old_value) == {"role": "auditor"}
        assert json.loads(row.new_value) == {"role": "operador"}
        assert str(row.actor_user_id) == str(self.ids["admin"])
        assert row.resource == f"users/{target_id}"
        assert row.outcome == "success"

    def test_password_reset_leaks_no_secrets(self):
        with self.Session() as db:
            target = AuthService().create_user(
                db, name="Pwr", email="pwr@example.com", password="pass-1234", role="operador"
            )
            db.commit()
            target_id = target.id
        r = self.client.post(
            f"/users/{target_id}/password",
            json={"new_password": "n3w-s3cret-pass"},
            headers=self._headers("admin"),
        )
        assert r.status_code == 200, r.text
        rows = self._audit_rows("user.password_reset")
        assert rows, "expected a password_reset audit row"
        row = rows[-1]
        assert row.old_value is None and row.new_value is None
        # Secret *values* (passwords, hashes) must never appear; the action
        # name "user.password_reset" itself is expected and harmless.
        blob = " ".join(
            str(v)
            for row in self._audit_rows()
            for v in (row.resource, row.outcome, row.old_value, row.new_value)
            if v
        )
        for secret in ("pass-1234", "n3w-s3cret-pass", "$2b$", "$2a$", "$2y$"):
            assert secret not in blob, f"secret leak: {secret}"
        for row in self._audit_rows():
            for v in (row.old_value, row.new_value):
                if v:
                    lowered = v.lower()
                    assert "password" not in lowered and "hash" not in lowered
                    assert "token" not in lowered and "secret" not in lowered

    # --- system-config ------------------------------------------------------

    def test_system_config_update_audited(self):
        before = len(self._audit_rows("system_config.update"))
        r = self.client.put(
            "/system-config",
            json={"max_temperature": 6.0},
            headers=self._headers("admin"),
        )
        assert r.status_code == 200, r.text
        rows = self._audit_rows("system_config.update")
        assert len(rows) == before + 1
        row = rows[-1]
        assert json.loads(row.old_value) == {
            "min_temperature": 0.0,
            "max_temperature": 4.0,
            "min_humidity": 85.0,
            "max_humidity": 90.0,
        }
        assert json.loads(row.new_value)["max_temperature"] == 6.0
        assert row.resource.startswith("system_configs/")
        assert "qos" not in (row.old_value or "") + (row.new_value or "")
        # restore for other tests
        r = self.client.put(
            "/system-config", json={"max_temperature": 4.0}, headers=self._headers("admin")
        )
        assert r.status_code == 200, r.text

    def test_system_config_invalid_leaves_no_success_audit(self):
        before = len(self._audit_rows("system_config.update"))
        r = self.client.put(
            "/system-config",
            json={"min_temperature": 10.0, "max_temperature": 4.0},
            headers=self._headers("admin"),
        )
        assert r.status_code in (400, 422), r.text
        assert len(self._audit_rows("system_config.update")) == before

    def test_system_config_forbidden_leaves_no_audit(self):
        before = len(self._audit_rows("system_config.update"))
        r = self.client.put(
            "/system-config",
            json={"max_temperature": 5.0},
            headers=self._headers("operador"),
        )
        assert r.status_code == 403, r.text
        assert len(self._audit_rows("system_config.update")) == before


if __name__ == "__main__":
    unittest.main()
