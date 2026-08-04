from dataclasses import dataclass


@dataclass
class BackendConfig:
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic: str = "coldchain/device/+/telemetry"
    mqtt_qos: int = 0
    max_queue_size: int = 1000
    log_level: str = "INFO"
