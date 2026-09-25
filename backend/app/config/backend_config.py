import os
from dataclasses import dataclass, field


@dataclass
class BackendConfig:
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic: str = "coldchain/device/+/telemetry"
    mqtt_qos: int = 0
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
