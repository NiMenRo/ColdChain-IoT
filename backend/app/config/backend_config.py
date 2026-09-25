import os
from dataclasses import dataclass, field


@dataclass
class BackendConfig:
    mqtt_host: str = "localhost"
    mqtt_port: int = field(
        default_factory=lambda: int(os.getenv("MQTT_PORT", "8883"))
    )
    mqtt_topic: str = "coldchain/device/+/telemetry"
    mqtt_qos: int = 0
    mqtt_username: str = field(default_factory=lambda: os.getenv("MQTT_USERNAME", ""))
    mqtt_password: str = field(default_factory=lambda: os.getenv("MQTT_PASSWORD", ""))
    mqtt_tls: bool = field(
        default_factory=lambda: os.getenv("MQTT_TLS", "true").strip().lower() == "true"
    )
    mqtt_ca_cert: str = field(default_factory=lambda: os.getenv("MQTT_CA_CERT", ""))
    max_queue_size: int = 1000
    log_level: str = "INFO"
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://coldchain:coldchain@localhost:5433/coldchain",
        )
    )
    jwt_algorithm: str = field(
        default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256")
    )
    jwt_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
    )
    jwt_secret_key: str = field(
        default_factory=lambda: os.getenv("JWT_SECRET_KEY", "")
    )

    def require_jwt_secret(self) -> str:
        """Return the configured JWT secret or fail with a clear error.

        The secret is mandatory outside tests: no default key and no
        hardcoded fallback are provided. Tests must set JWT_SECRET_KEY
        explicitly (e.g. a test-only value via environment).
        """
        secret = self.jwt_secret_key or os.getenv("JWT_SECRET_KEY", "")
        if not secret:
            raise RuntimeError(
                "JWT_SECRET_KEY is not configured. Set the JWT_SECRET_KEY "
                "environment variable (and optionally JWT_EXPIRE_MINUTES)."
            )
        return secret

    def mqtt_credentials(self) -> tuple[str | None, str | None, str | None]:
        """Return (username, password, ca_cert) for MQTT or fail clearly.

        TSK-056: the broker requires TLS + authentication. Missing
        values raise instead of silently falling back to anonymous
        plaintext. Values are never logged by callers.
        """
        username = self.mqtt_username or os.getenv("MQTT_USERNAME", "")
        password = self.mqtt_password or os.getenv("MQTT_PASSWORD", "")
        ca_cert = self.mqtt_ca_cert or os.getenv("MQTT_CA_CERT", "")
        if not username or not password:
            raise RuntimeError(
                "MQTT_USERNAME and MQTT_PASSWORD are not configured. "
                "Export them (see backend/.env.example); anonymous "
                "connections are rejected by the broker."
            )
        if self.mqtt_tls and not ca_cert:
            raise RuntimeError(
                "MQTT_CA_CERT is not configured. TLS verification "
                "requires an explicit CA certificate; it is never disabled."
            )
        return username, password, (ca_cert if self.mqtt_tls else None)
