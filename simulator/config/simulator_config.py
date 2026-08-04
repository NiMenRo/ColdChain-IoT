from dataclasses import dataclass


@dataclass
class SimulatorConfig:
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_qos: int = 0
    sampling_interval: float = 1.0
    topic_prefix: str = "coldchain/device"
    log_level: str = "INFO"
