"""Read MQTT state through the API without starting production services."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import AuthenticatedUser, get_current_user
from main import app as production_app, get_acquisition_status


@pytest.mark.parametrize("connected", [True, False, None])
def test_status_reports_client_state(monkeypatch, connected):
    monkeypatch.setattr(
        production_app.state, "mqtt_client",
        SimpleNamespace(is_connected=connected) if connected is not None else None,
        raising=False,
    )
    app = FastAPI()
    app.get("/acquisition/status")(get_acquisition_status)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid4(), email="auditor@example.com", name="Auditor",
        role="auditor", is_active=True,
    )
    with TestClient(app) as client:
        response = client.get("/acquisition/status")
    assert response.status_code == 200
    assert response.json() == {"connected": connected}


def test_status_requires_authentication():
    app = FastAPI()
    app.get("/acquisition/status")(get_acquisition_status)
    with TestClient(app) as client:
        assert client.get("/acquisition/status").status_code == 401
