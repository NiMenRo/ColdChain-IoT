"""Automatic device code generation (CAVA-*/VITRINA-*).

Covers sequencing per type, gap tolerance, unknown types and the
ignored client-supplied code contract.
"""

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
from app.database.infrastructure.models import DeviceORM
from app.database.infrastructure.session import get_db
from app.devices.api import router
from app.devices.codes import code_prefix, next_device_code


def _session_factory():
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
    return sessionmaker(bind=engine, future=True)


def test_prefixes_match_seed_convention():
    assert code_prefix("cold_room") == "CAVA"
    assert code_prefix("refrigerated_showcase") == "VITRINA"


def test_sequence_continues_and_skips_gaps():
    Session = _session_factory()
    with Session() as db:
        assert next_device_code(db, "cold_room") == "CAVA-001"
        db.add(DeviceORM(code="CAVA-001", name="A", location="L", device_type="cold_room", status="active"))
        db.add(DeviceORM(code="CAVA-003", name="B", location="L", device_type="cold_room", status="active"))
        db.add(DeviceORM(code="LEGACY-X", name="C", location="L", device_type="cold_room", status="active"))
        db.commit()
        assert next_device_code(db, "cold_room") == "CAVA-002"
        assert next_device_code(db, "refrigerated_showcase") == "VITRINA-001"


def test_unknown_device_type_raises():
    Session = _session_factory()
    with Session() as db:
        try:
            next_device_code(db, "toaster")
        except (KeyError, ValueError):
            return
        raise AssertionError("expected KeyError/ValueError for unknown device_type")


def _client():
    Session = _session_factory()
    with Session() as db:
        user = AuthService().create_user(
            db, name="Admin", email="admin@example.com",
            password="pass-1234", role="admin",
        )
        db.commit()
        user_id = user.id
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
        id=user_id, email="admin@example.com", name="Admin",
        role="admin", is_active=True,
    )
    return TestClient(app)


def _create(client, **over):
    body = {
        "name": "Cava",
        "location": "Lab",
        "device_type": "cold_room",
        "sensors": ["temperature"],
    }
    body.update(over)
    return client.post("/devices", json=body)


def test_codes_are_sequential_per_type_and_client_code_ignored():
    client = _client()
    first = _create(client, code="CLIENT-IGNORED")
    assert first.status_code == 201, first.text
    assert first.json()["device"]["code"] == "CAVA-001"
    second = _create(client)
    assert second.status_code == 201, second.text
    assert second.json()["device"]["code"] == "CAVA-002"
    vitrina = _create(client, device_type="refrigerated_showcase")
    assert vitrina.status_code == 201, vitrina.text
    assert vitrina.json()["device"]["code"] == "VITRINA-001"


def test_invalid_device_type_is_400():
    client = _client()
    r = _create(client, device_type="toaster")
    assert r.status_code == 400, r.text


def test_missing_code_field_still_creates():
    client = _client()
    r = client.post("/devices", json={
        "name": "Sin codigo",
        "location": "Lab",
        "device_type": "cold_room",
        "sensors": ["temperature"],
    })
    assert r.status_code == 201, r.text
    assert r.json()["device"]["code"].startswith("CAVA-")
    assert uuid.UUID(r.json()["device"]["id"])
