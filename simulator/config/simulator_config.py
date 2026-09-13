import os
from dataclasses import dataclass, field


@dataclass
class SimulatorConfig:
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_qos: int = 0
    sampling_interval: float = 1.0
    topic_prefix: str = "coldchain/device"
    log_level: str = "INFO"
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://coldchain:coldchain@localhost:5433/coldchain",
        )
    )
