"""Centralized role-based authorization (TSK-055).

Human roles only: admin, supervisor, operador, auditor.
The technical identity `system` is rejected by get_current_user
and never reaches these checks: it is NOT a fifth RBAC role,
it stays outside the human authorization flow.

Usage on endpoints::

    @router.get("/x", dependencies=[Depends(authenticated)])
    @router.post("/y", dependencies=[Depends(require_roles("admin"))])

401 comes exclusively from get_current_user (missing/invalid/
expired token, unknown or inactive user). 403 comes exclusively
from require_roles (valid identity, insufficient role).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.database.infrastructure.models import HUMAN_USER_ROLES

# Explicit human-role policy surface. `system` is intentionally
# absent: it must never be granted human permissions.
ADMIN = "admin"
SUPERVISOR = "supervisor"
OPERADOR = "operador"
AUDITOR = "auditor"


def _forbidden(detail: str = "Forbidden") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def authenticated(
    current: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Require any authenticated human (no role distinction)."""
    return current


def require_roles(*roles: str):
    """Dependency factory allowing only the given human roles.

    Unknown role names fail closed at registration time.
    """

    unknown = set(roles) - HUMAN_USER_ROLES
    if unknown:
        raise ValueError(f"unknown roles in authorization policy: {sorted(unknown)}")
    if not roles:
        raise ValueError("require_roles needs at least one role")

    def _check(
        current: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if current.role not in roles:
            raise _forbidden()
        return current

    return _check


# Prebuilt policies matching the definitive TSK-055 matrix.
require_admin = require_roles(ADMIN)
require_ack = require_roles(ADMIN, SUPERVISOR, OPERADOR)
require_notification_write = require_roles(ADMIN, SUPERVISOR)
