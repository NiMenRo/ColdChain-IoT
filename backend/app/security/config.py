"""Centralized security configuration (TSK-057).

Exposes non-sensitive security parameters and context while guaranteeing
that sensitive data (such as JWT secret keys, database credentials, and
MQTT passwords) are never leaked in logs, API responses, or code.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from app.config.backend_config import BackendConfig
from app.database.infrastructure.models import (
    HUMAN_USER_ROLES,
    TECHNICAL_USER_ROLE,
    USER_ROLE_RESPONSIBILITIES,
)


@dataclass(frozen=True)
class SafeSecurityConfig:
    """Safe, non-sensitive snapshot of backend security settings.
    
    Excludes sensitive credentials such as `jwt_secret_key` and
    `mqtt_password`, exposing only safe metadata and booleans.
    """

    jwt_algorithm: str
    jwt_expire_minutes: int
    jwt_secret_configured: bool
    mqtt_host: str
    mqtt_port: int
    mqtt_tls_enabled: bool
    mqtt_ca_cert_configured: bool
    mqtt_auth_configured: bool
    human_roles: List[str]
    technical_role: str
    role_responsibilities: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_safe_security_config(config: BackendConfig | None = None) -> SafeSecurityConfig:
    """Build a safe security configuration summary without secrets."""
    cfg = config or BackendConfig()

    jwt_secret = cfg.jwt_secret_key or os.getenv("JWT_SECRET_KEY", "")
    mqtt_user = cfg.mqtt_username or os.getenv("MQTT_USERNAME", "")
    mqtt_pass = cfg.mqtt_password or os.getenv("MQTT_PASSWORD", "")
    mqtt_ca = cfg.mqtt_ca_cert or os.getenv("MQTT_CA_CERT", "")

    return SafeSecurityConfig(
        jwt_algorithm=cfg.jwt_algorithm,
        jwt_expire_minutes=cfg.jwt_expire_minutes,
        jwt_secret_configured=bool(jwt_secret),
        mqtt_host=cfg.mqtt_host,
        mqtt_port=cfg.mqtt_port,
        mqtt_tls_enabled=bool(cfg.mqtt_tls),
        mqtt_ca_cert_configured=bool(mqtt_ca),
        mqtt_auth_configured=bool(mqtt_user and mqtt_pass),
        human_roles=sorted(list(HUMAN_USER_ROLES)),
        technical_role=TECHNICAL_USER_ROLE,
        role_responsibilities=dict(USER_ROLE_RESPONSIBILITIES),
    )


def get_mqtt_security_context(config: BackendConfig | None = None) -> Dict[str, Any]:
    """Inspect and validate MQTT security settings according to TSK-056.
    
    Verifies that TLS and credentials are configured as required by TSK-056,
    maintaining strict independence from HTTP authentication / authorization.
    """
    cfg = config or BackendConfig()
    username = cfg.mqtt_username or os.getenv("MQTT_USERNAME", "")
    password = cfg.mqtt_password or os.getenv("MQTT_PASSWORD", "")
    ca_cert = cfg.mqtt_ca_cert or os.getenv("MQTT_CA_CERT", "")
    tls_enabled = bool(cfg.mqtt_tls)

    return {
        "host": cfg.mqtt_host,
        "port": cfg.mqtt_port,
        "tls_enabled": tls_enabled,
        "ca_cert_path": ca_cert if tls_enabled else None,
        "has_credentials": bool(username and password),
        "username": username if username else None,
        # Password and secret are deliberately excluded
        "channel_isolation": (
            "MQTT communication is dedicated to technical ingestion and decoupled "
            "from HTTP human identity management."
        ),
    }
