"""Central System Security Package (TSK-057).

Integrates and provides reusable authentication (TSK-054), authorization
RBAC (TSK-055), and security configuration (TSK-056) for backend endpoints.
"""

from app.auth.dependencies import AuthenticatedUser
from app.database.infrastructure.models import (
    HUMAN_USER_ROLES,
    TECHNICAL_USER_ROLE,
    USER_ROLE_RESPONSIBILITIES,
)
from app.security.config import (
    SafeSecurityConfig,
    get_mqtt_security_context,
    get_safe_security_config,
)
from app.security.dependencies import (
    ADMIN,
    AUDITOR,
    OPERADOR,
    SUPERVISOR,
    authenticated,
    get_current_user,
    get_safe_security_config_dep,
    get_security_service,
    require_ack,
    require_admin,
    require_auditor_or_above,
    require_notification_write,
    require_roles,
)
from app.security.service import SecurityService

__all__ = [
    "ADMIN",
    "AUDITOR",
    "AuthenticatedUser",
    "HUMAN_USER_ROLES",
    "OPERADOR",
    "SUPERVISOR",
    "SafeSecurityConfig",
    "SecurityService",
    "TECHNICAL_USER_ROLE",
    "USER_ROLE_RESPONSIBILITIES",
    "authenticated",
    "get_current_user",
    "get_mqtt_security_context",
    "get_safe_security_config",
    "get_safe_security_config_dep",
    "get_security_service",
    "require_ack",
    "require_admin",
    "require_auditor_or_above",
    "require_notification_write",
    "require_roles",
]
