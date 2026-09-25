"""TSK-054 authentication package.

Establishes the authenticated identity (who the user is) without
implementing role-based authorization (what the user may do).
RBAC belongs to TSK-055.
"""

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.auth.service import AuthService, InvalidCredentialsError

__all__ = ["AuthenticatedUser", "AuthService", "InvalidCredentialsError", "get_current_user"]
