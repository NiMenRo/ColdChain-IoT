"""Security dependencies exposed to HTTP APIs (TSK-057/TSK-058).

This module is the single integration point for REST routers.  The actual
credential verification and RBAC policy live in the authentication modules
implemented by TSK-054 and TSK-055; they are deliberately re-exported here
instead of being recreated by each API endpoint.
"""

from app.auth.authorization import (
    authenticated,
    require_ack,
    require_admin,
    require_notification_write,
    require_roles,
)
from app.auth.dependencies import AuthenticatedUser, get_current_user

__all__ = [
    "AuthenticatedUser",
    "authenticated",
    "get_current_user",
    "require_ack",
    "require_admin",
    "require_notification_write",
    "require_roles",
]
