from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.api import router as auth_router
from app.auth.password_reset_service import RESET_EMAIL_RESPONSE
from app.auth.service import AuthService
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import PasswordResetTokenORM, UserORM
from app.database.infrastructure.session import get_db


@pytest.fixture
def reset_client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False)
    with test_session() as db:
        AuthService().create_user(
            db,
            name="Ana",
            email="ana@example.com",
            password="old-password",
            role="operador",
        )
        db.commit()

    app = FastAPI()
    app.include_router(auth_router)

    def override_get_db():
        with test_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://localhost:5173")
    monkeypatch.setenv("SMTP_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "alerts@example.com")
    client = TestClient(app)
    yield client, test_session
    client.close()
    engine.dispose()


def test_reset_request_sends_one_time_link_and_updates_password(
    reset_client, monkeypatch
):
    client, test_session = reset_client
    sent = []
    monkeypatch.setattr(
        "app.auth.password_reset_service.send_smtp_email",
        lambda config, recipient, subject, body: sent.append(
            (recipient, subject, body)
        ),
    )

    response = client.post(
        "/auth/password-reset/request", json={"email": "ANA@example.com"}
    )

    assert response.status_code == 202
    assert response.json()["message"] == RESET_EMAIL_RESPONSE
    assert response.headers["cache-control"] == "no-store"
    assert len(sent) == 1
    recipient, subject, body = sent[0]
    assert recipient == "ana@example.com"
    assert subject.startswith("ColdChain-IoT")
    token_match = re.search(r"#token=([A-Za-z0-9_-]+)", body)
    assert token_match is not None
    token = unquote(token_match.group(1))

    with test_session() as db:
        stored_token = db.query(PasswordResetTokenORM).one()
        assert stored_token.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert stored_token.token_hash != token

    confirm_response = client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "new_password": "new-password-123"},
    )
    assert confirm_response.status_code == 200
    assert confirm_response.headers["cache-control"] == "no-store"
    assert confirm_response.json()["message"] == "La contraseña se restableció correctamente."

    with test_session() as db:
        user = AuthService().authenticate(
            db, email="ana@example.com", password="new-password-123"
        )
        assert user.email == "ana@example.com"

    replay_response = client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "new_password": "another-password"},
    )
    assert replay_response.status_code == 400


def test_reset_request_does_not_disclose_unknown_account(
    reset_client, monkeypatch
):
    client, _ = reset_client
    sent = []
    monkeypatch.setattr(
        "app.auth.password_reset_service.send_smtp_email",
        lambda *args: sent.append(args),
    )

    response = client.post(
        "/auth/password-reset/request", json={"email": "unknown@example.com"}
    )

    assert response.status_code == 202
    assert response.json()["message"] == RESET_EMAIL_RESPONSE
    assert sent == []


def test_reset_request_reports_unconfigured_email_service_without_account_leak(
    reset_client, monkeypatch
):
    client, _ = reset_client
    monkeypatch.setenv("SMTP_ENABLED", "false")

    known = client.post(
        "/auth/password-reset/request", json={"email": "ana@example.com"}
    )
    unknown = client.post(
        "/auth/password-reset/request", json={"email": "unknown@example.com"}
    )

    assert known.status_code == unknown.status_code == 503
    assert known.json() == unknown.json()


def test_expired_reset_link_is_rejected(reset_client, monkeypatch):
    client, test_session = reset_client
    sent = []
    monkeypatch.setattr(
        "app.auth.password_reset_service.send_smtp_email",
        lambda config, recipient, subject, body: sent.append(body),
    )
    client.post("/auth/password-reset/request", json={"email": "ana@example.com"})
    token = unquote(re.search(r"#token=([A-Za-z0-9_-]+)", sent[0]).group(1))

    with test_session() as db:
        reset_token = db.query(PasswordResetTokenORM).one()
        reset_token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    response = client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "new_password": "new-password-123"},
    )
    assert response.status_code == 400
