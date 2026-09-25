"""TSK-054 authentication + TSK-055 authorization package.

get_current_user establishes the authenticated identity (who the
user is); authorization.require_roles decides what the user may
do. The technical identity `system` stays outside both flows.
"""

from app.auth.authorization import (
    authenticated,
    require_admin,
    require_roles,
)
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.auth.service import AuthService, InvalidCredentialsError

__all__ = [
    "AuthenticatedUser",
    "AuthService",
    "InvalidCredentialsError",
    "authenticated",
    "get_current_user",
    "require_admin",
    "require_roles",
]
