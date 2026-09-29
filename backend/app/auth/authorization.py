"""Centralized role-based authorization (TSK-055 / TSK-057).

Re-exports authorization dependencies from the centralized security system
(app.security).
"""

from __future__ import annotations

from fastapi import HTTPException, status
from app.security.dependencies import (
    ADMIN,
    AUDITOR,
    AuthenticatedUser,
    OPERADOR,
    SUPERVISOR,
    authenticated,
    get_current_user,
    require_ack,
    require_admin,
    require_notification_write,
    require_roles,
)

__all__ = [
    "ADMIN",
    "AUDITOR",
    "AuthenticatedUser",
    "OPERADOR",
    "SUPERVISOR",
    "authenticated",
    "get_current_user",
    "require_ack",
    "require_admin",
    "require_notification_write",
    "require_roles",
]


def _forbidden(detail: str = "Forbidden") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
