"""Centralized authenticated-identity dependency (TSK-054).

Resolves the user from the Bearer token on every request and
re-checks is_active in the database, so a user deactivated after
the token was issued is rejected immediately (expiry alone is
not trusted for deactivation).

The role is carried in the identity for TSK-055 but no
authorization is enforced here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.tokens import decode_token
from app.database.infrastructure.models import TECHNICAL_USER_ROLE
from app.database.infrastructure.repositories import UserRepository
from app.database.infrastructure.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthenticatedUser:
    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    if credentials is None or not credentials.credentials:
        raise _unauthorized()
    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token has expired")
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token")
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (ValueError, TypeError, AttributeError):
        raise _unauthorized("Invalid token")
    user = UserRepository().get_by_id(db, user_id)
    if user is None:
        raise _unauthorized("Invalid token")
    if user.role == TECHNICAL_USER_ROLE:
        raise _unauthorized("Invalid token")
    if not user.is_active:
        raise _unauthorized("User is inactive")
    return AuthenticatedUser(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=bool(user.is_active),
    )
