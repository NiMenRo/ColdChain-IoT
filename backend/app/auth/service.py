"""Authentication and internal user management service (TSK-054).

No role-based authorization is implemented here: every method
operates without permission checks. RBAC belongs to TSK-055.
User management via HTTP API is intentionally NOT exposed in
TSK-054; this service is used by the login flow, the admin
bootstrap CLI and future TSK-055 endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.auth.password import hash_password, verify_password
from app.auth.tokens import create_access_token
from app.database.infrastructure.models import TECHNICAL_USER_ROLE, UserORM
from app.database.infrastructure.repositories import UserRepository


class InvalidCredentialsError(Exception):
    """Generic authentication failure.

    A single error type is used for unknown user, wrong password,
    inactive user and technical identities so callers cannot
    distinguish between them (mapped to one 401 message).
    """


class AuthService:
    def __init__(self, users: UserRepository | None = None) -> None:
        self._users = users or UserRepository()

    def authenticate(self, db: Session, *, email: str, password: str) -> UserORM:
        """Validate credentials and activity. Returns the user or raises."""
        user = self._users.get_by_email(db, email) if isinstance(email, str) else None
        if user is None:
            raise InvalidCredentialsError("invalid credentials")
        if user.role == TECHNICAL_USER_ROLE:
            # Technical identities never authenticate as human users.
            raise InvalidCredentialsError("invalid credentials")
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("invalid credentials")
        if not user.is_active:
            raise InvalidCredentialsError("invalid credentials")
        return user

    def login(self, db: Session, *, email: str, password: str) -> tuple[UserORM, str, int]:
        """Authenticate and issue a token. Returns (user, token, expires_in)."""
        user = self.authenticate(db, email=email, password=password)
        token, expires_in = create_access_token(user.id, user.role)
        return user, token, expires_in

    def create_user(
        self,
        db: Session,
        *,
        name: str,
        email: str,
        password: str,
        role: str,
        is_active: bool = True,
    ) -> UserORM:
        """Create a human user hashing the password (internal/CLI use)."""
        if not isinstance(password, str) or not password:
            raise ValueError("password must be a non-empty string")
        return self._users.create(
            db,
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=is_active,
        )

    def get_user(self, db: Session, user_id: uuid.UUID) -> UserORM | None:
        return self._users.get_by_id(db, user_id)

    def update_user(self, db: Session, user: UserORM, **fields) -> UserORM:
        """Update name/email/role/is_active (internal use, no RBAC yet)."""
        if "password" in fields:
            raise ValueError("use change_password to update the password")
        return self._users.update(db, user, **fields)

    def set_active(self, db: Session, user: UserORM, active: bool) -> UserORM:
        return self._users.update(db, user, is_active=active)

    def change_password(self, db: Session, user: UserORM, new_password: str) -> UserORM:
        if not isinstance(new_password, str) or not new_password:
            raise ValueError("password must be a non-empty string")
        return self._users.update(
            db, user, password_hash=hash_password(new_password)
        )

    @staticmethod
    def to_response(user: UserORM) -> dict:
        """Public user representation (never includes the password hash)."""
        created = user.created_at
        if isinstance(created, datetime) and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "is_active": bool(user.is_active),
            "created_at": created,
        }
