"""Centralized Security Service (TSK-057).

Integrates and provides reusable authentication (TSK-054), authorization
RBAC (TSK-055), and security configuration (TSK-056) for backend services
and protected endpoints without duplicating domain logic.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Collection, Dict

import jwt
from dataclasses import dataclass
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.auth.service import AuthService
from app.auth.tokens import decode_token
from app.config.backend_config import BackendConfig
from app.database.infrastructure.models import (
    HUMAN_USER_ROLES,
    TECHNICAL_USER_ROLE,
)
from app.database.infrastructure.repositories import UserRepository
from app.security.config import (
    SafeSecurityConfig,
    get_mqtt_security_context,
    get_safe_security_config,
)

logger = logging.getLogger(__name__)


@dataclass
class AuthenticatedUser:
    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool


class SecurityService:
    """Central system security service."""

    def __init__(
        self,
        config: BackendConfig | None = None,
        auth_service: AuthService | None = None,
        user_repo: UserRepository | None = None,
    ) -> None:
        self._config = config or BackendConfig()
        self._auth_service = auth_service or AuthService()
        self._users = user_repo or UserRepository()

    @property
    def config(self) -> BackendConfig:
        return self._config

    @property
    def auth_service(self) -> AuthService:
        return self._auth_service

    @property
    def user_repository(self) -> UserRepository:
        return self._users

    # --- HTTP Authentication (TSK-054 integration) ---

    def authenticate_http(
        self,
        credentials: HTTPAuthorizationCredentials | None,
        db: Session,
    ) -> AuthenticatedUser:
        """Authenticate an HTTP request from Bearer credentials.
        
        Returns an AuthenticatedUser if valid.
        Raises HTTPException(401) on any authentication error.
        Strictly isolates the technical identity `system`, which is never
        permitted to access endpoints via human user tokens.
        """
        if credentials is None or not credentials.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        return self.authenticate_token(credentials.credentials, db)

    def authenticate_token(self, token: str, db: Session) -> AuthenticatedUser:
        """Validate a JWT token string against database state.
        
        Decodes the token using TSK-054 logic and verifies user status in DB.
        """
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        try:
            user_id = uuid.UUID(str(payload.get("sub")))
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        user = self._users.get_by_id(db, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        # Separate technical identity: `system` is rejected for human HTTP sessions
        if user.role == TECHNICAL_USER_ROLE:
            logger.warning(
                "Attempted HTTP authentication using technical identity '%s'",
                TECHNICAL_USER_ROLE,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User is inactive",
            )

        return AuthenticatedUser(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            is_active=bool(user.is_active),
        )

    # --- Role-Based Access Control (TSK-055 integration) ---

    def authorize(
        self,
        user: AuthenticatedUser,
        allowed_roles: Collection[str],
    ) -> AuthenticatedUser:
        """Validate that the authenticated user possesses one of the allowed roles.
        
        Unknown roles fail closed at declaration time (raises ValueError).
        Users without sufficient roles raise HTTPException(403).
        The technical identity `system` is never granted human roles.
        """
        role_set = set(allowed_roles)
        unknown = role_set - HUMAN_USER_ROLES
        if unknown:
            raise ValueError(f"unknown roles in authorization policy: {sorted(unknown)}")
        if not role_set:
            raise ValueError("authorize requires at least one allowed role")

        if user.role == TECHNICAL_USER_ROLE or user.role not in role_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )

        return user

    def is_authorized(
        self,
        user: AuthenticatedUser,
        allowed_roles: Collection[str],
    ) -> bool:
        """Check if user role matches allowed roles without raising exceptions."""
        try:
            self.authorize(user, allowed_roles)
            return True
        except (HTTPException, ValueError):
            return False

    # --- Centralized Security Configuration (TSK-054, TSK-055, TSK-056) ---

    def get_safe_config(self) -> SafeSecurityConfig:
        """Return safe, non-sensitive backend security configuration."""
        return get_safe_security_config(self._config)

    def validate_mqtt_security(self) -> Dict[str, Any]:
        """Validate MQTT security configuration compliance according to TSK-056.
        
        Ensures broker credentials and TLS verification parameters are in place,
        respecting separation from HTTP authentication.
        """
        context = get_mqtt_security_context(self._config)
        # Verify credentials readiness without mutating MQTTClient behavior
        username, password, ca_cert = self._config.mqtt_credentials()
        context["verified"] = bool(username and password and (ca_cert or not self._config.mqtt_tls))
        return context
