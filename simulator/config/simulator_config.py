import os
from dataclasses import dataclass, field


@dataclass
class SimulatorConfig:
    mqtt_host: str = "localhost"
    mqtt_port: int = field(
        default_factory=lambda: int(os.getenv("MQTT_PORT", "8883"))
    )
    mqtt_qos: int = 0
    mqtt_username: str = field(default_factory=lambda: os.getenv("MQTT_USERNAME", ""))
    mqtt_password: str = field(default_factory=lambda: os.getenv("MQTT_PASSWORD", ""))
    mqtt_tls: bool = field(
        default_factory=lambda: os.getenv("MQTT_TLS", "true").strip().lower() == "true"
    )
    mqtt_ca_cert: str = field(default_factory=lambda: os.getenv("MQTT_CA_CERT", ""))
    sampling_interval: float = 1.0
    topic_prefix: str = "coldchain/device"
    log_level: str = "INFO"
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://coldchain:coldchain@localhost:5433/coldchain",
        )
    )

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
                "Export them (see simulator/.env.example); anonymous "
                "connections are rejected by the broker."
            )
        if self.mqtt_tls and not ca_cert:
            raise RuntimeError(
                "MQTT_CA_CERT is not configured. TLS verification "
                "requires an explicit CA certificate; it is never disabled."
            )
        return username, password, (ca_cert if self.mqtt_tls else None)
