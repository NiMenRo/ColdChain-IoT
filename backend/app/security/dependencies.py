"""Reusable FastAPI security dependencies (TSK-057).

Centralizes all authentication, authorization, and security context
dependencies used by protected endpoints across the backend.
"""

from __future__ import annotations

from typing import Callable
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.security.service import AuthenticatedUser, SecurityService
from app.database.infrastructure.models import (
    HUMAN_USER_ROLES,
    TECHNICAL_USER_ROLE,
)

ADMIN = "admin"
SUPERVISOR = "supervisor"
OPERADOR = "operador"
AUDITOR = "auditor"
from app.database.infrastructure.session import get_db
from app.security.config import SafeSecurityConfig

bearer_scheme = HTTPBearer(auto_error=False)
_security_service_instance = SecurityService()


def get_security_service() -> SecurityService:
    """Dependency provider returning the centralized SecurityService instance."""
    return _security_service_instance


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    security_service: SecurityService = Depends(get_security_service),
) -> AuthenticatedUser:
    """Resolve and validate the authenticated human identity from Bearer token."""
    return security_service.authenticate_http(credentials, db)


def authenticated(
    current: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Dependency requiring any authenticated human user regardless of role."""
    return current


def require_roles(*roles: str) -> Callable[..., AuthenticatedUser]:
    """Dependency factory restricting access to users with specified human roles.
    
    Validates role names against HUMAN_USER_ROLES at route registration time.
    Raises HTTPException(401) if not authenticated.
    Raises HTTPException(403) if role is insufficient.
    """
    unknown = set(roles) - HUMAN_USER_ROLES
    if unknown:
        raise ValueError(f"unknown roles in authorization policy: {sorted(unknown)}")
    if not roles:
        raise ValueError("require_roles needs at least one role")

    def _check(
        current: AuthenticatedUser = Depends(get_current_user),
        security_service: SecurityService = Depends(get_security_service),
    ) -> AuthenticatedUser:
        return security_service.authorize(current, roles)

    return _check


# Predefined RBAC policies matching the backend matrix
require_admin = require_roles(ADMIN)
require_ack = require_roles(ADMIN, SUPERVISOR, OPERADOR)
require_notification_write = require_roles(ADMIN, SUPERVISOR)
require_auditor_or_above = require_roles(ADMIN, AUDITOR)


def get_safe_security_config_dep(
    security_service: SecurityService = Depends(get_security_service),
) -> SafeSecurityConfig:
    """Dependency providing the safe security configuration snapshot."""
    return security_service.get_safe_config()
