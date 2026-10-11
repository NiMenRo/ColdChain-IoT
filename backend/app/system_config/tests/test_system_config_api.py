"""TSK-059.4 — admin-only PUT /system-config."""

import sys
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.auth.service import AuthService
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import SystemConfigORM
from app.database.infrastructure.session import get_db
from app.system_config.api import router


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


def _client(role="admin", seed=True):
    engine = _engine()
    Session = sessionmaker(bind=engine, future=True)
    user_id = None
    if seed:
        s = Session()
        # TSK-059.5 — audit FK requires a real actor row.
        user = AuthService().create_user(
            s, name=role.title(), email=f"{role}@example.com",
            password="pass-1234", role=role,
        )
        user_id = user.id
        s.add(
            SystemConfigORM(
                min_temperature=0.0,
                max_temperature=4.0,
                min_humidity=85.0,
                max_humidity=90.0,
                qos_algorithm="wfq",
                qos_enabled=True,
            )
        )
        s.commit()
        s.close()

    app = FastAPI()
    app.include_router(router)

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=user_id or uuid.uuid4(),
        email=f"{role}@example.com",
        name=role.title(),
        role=role,
        is_active=True,
    )
    return TestClient(app)


def test_admin_can_update_thresholds():
    c = _client(role="admin")
    r = c.put("/system-config", json={"max_temperature": 6.0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["max_temperature"] == 6.0
    assert body["min_temperature"] == 0.0
    # response exposes only administrable fields
    assert set(body) == {"id", "min_temperature", "max_temperature", "min_humidity", "max_humidity"}


def test_inverted_range_rejected():
    c = _client(role="admin")
    r = c.put("/system-config", json={"min_temperature": 10.0, "max_temperature": 4.0})
    assert r.status_code in (400, 422), r.text
    r = c.put("/system-config", json={"min_humidity": 95.0, "max_humidity": 90.0})
    assert r.status_code in (400, 422), r.text


def test_empty_body_rejected():
    c = _client(role="admin")
    r = c.put("/system-config", json={})
    assert r.status_code == 400, r.text


def test_qos_fields_not_accepted():
    c = _client(role="admin")
    r = c.put(
        "/system-config",
        json={"max_temperature": 5.0, "qos_algorithm": "fifo", "qos_enabled": False},
    )
    assert r.status_code in (200, 422), r.text
    if r.status_code == 200:
        assert "qos_algorithm" not in r.json()
        assert "qos_enabled" not in r.json()


def test_non_admin_forbidden():
    for role in ("supervisor", "operador", "auditor"):
        c = _client(role=role)
        r = c.put("/system-config", json={"max_temperature": 5.0})
        assert r.status_code == 403, (role, r.text)


def test_unauthenticated_rejected():
    engine = _engine()
    Session = sessionmaker(bind=engine, future=True)
    from fastapi import FastAPI as _FastAPI

    app = _FastAPI()
    app.include_router(router)

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    c = TestClient(app)
    r = c.put("/system-config", json={"max_temperature": 5.0})
    assert r.status_code in (401, 403), r.text


def test_missing_config_returns_404():
    c = _client(role="admin", seed=False)
    r = c.put("/system-config", json={"max_temperature": 5.0})
    assert r.status_code == 404, r.text
