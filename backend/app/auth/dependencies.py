"""Centralized authenticated-identity dependency (TSK-054 / TSK-057).

Re-exports authenticated-identity dependencies from the centralized
security system (app.security).
"""

from __future__ import annotations

from fastapi import HTTPException, status
from app.security.dependencies import (
    AuthenticatedUser,
    bearer_scheme,
    get_current_user,
)

__all__ = [
    "AuthenticatedUser",
    "bearer_scheme",
    "get_current_user",
]


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
