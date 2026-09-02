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
