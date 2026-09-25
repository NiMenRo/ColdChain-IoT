"""JWT creation and validation (TSK-054).

Minimal claims: sub (user id), role (for TSK-055), iat, exp.
No sensitive data is stored in the token.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import BackendConfig


def _auth_config() -> BackendConfig:
    return BackendConfig()


def create_access_token(
    user_id: uuid.UUID | str,
    role: str,
    *,
    secret: str | None = None,
    algorithm: str | None = None,
    expires_minutes: int | None = None,
) -> tuple[str, int]:
    """Create a signed JWT. Returns (token, expires_in_seconds)."""
    config = _auth_config()
    key = secret if secret is not None else config.require_jwt_secret()
    algo = algorithm or config.jwt_algorithm
    minutes = expires_minutes if expires_minutes is not None else config.jwt_expire_minutes
    now = datetime.now(timezone.utc)
    expires_in = int(minutes * 60)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, key, algorithm=algo), expires_in


def decode_token(
    token: str,
    *,
    secret: str | None = None,
    algorithm: str | None = None,
) -> dict:
    """Decode and validate a JWT.

    Raises jwt.ExpiredSignatureError on expiry and
    jwt.InvalidTokenError on any other problem. Callers map
    these to 401 responses.
    """
    config = _auth_config()
    key = secret if secret is not None else config.require_jwt_secret()
    algo = algorithm or config.jwt_algorithm
    return jwt.decode(token, key, algorithms=[algo])
