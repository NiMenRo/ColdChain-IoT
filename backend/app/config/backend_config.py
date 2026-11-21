import os
import json
from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import Mapping


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = float(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive number") from error
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _flow_weights() -> Mapping[tuple[str, str], float]:
    """Parse explicit WFQ flow weights without accepting ambiguous values."""
    raw_value = os.getenv("QOS_WFQ_FLOW_WEIGHTS", "").strip()
    if not raw_value:
        return MappingProxyType({})
    try:
        configured_weights = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise ValueError(
            "QOS_WFQ_FLOW_WEIGHTS must be a JSON object of "
            "'device_code:sensor_name' to positive weights"
        ) from error
    if not isinstance(configured_weights, dict):
        raise ValueError("QOS_WFQ_FLOW_WEIGHTS must be a JSON object")

    weights: dict[tuple[str, str], float] = {}
    for flow, weight in configured_weights.items():
        if not isinstance(flow, str) or flow.count(":") != 1:
            raise ValueError(
                "QOS_WFQ_FLOW_WEIGHTS keys must be 'device_code:sensor_name'"
            )
        device_code, sensor_name = (part.strip() for part in flow.split(":"))
        if not device_code or sensor_name not in {"temperature", "humidity", "energy"}:
            raise ValueError(
                "QOS_WFQ_FLOW_WEIGHTS keys need a device code and supported sensor"
            )
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise ValueError("QOS_WFQ_FLOW_WEIGHTS values must be positive numbers")
        normalized_weight = float(weight)
        if not isfinite(normalized_weight) or normalized_weight <= 0:
            raise ValueError("QOS_WFQ_FLOW_WEIGHTS values must be positive numbers")
        weights[(device_code, sensor_name)] = normalized_weight
    return MappingProxyType(weights)


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
    # Transport messages, not sensor work items. Kept under its existing name
    # for compatibility with callers until T12 changes transport admission.
    max_queue_size: int = field(
        default_factory=lambda: _positive_int("MAX_QUEUE_SIZE", 1000)
    )
    qos_high_quota: int = field(
        default_factory=lambda: _positive_int("QOS_HIGH_QUOTA", 4)
    )
    qos_medium_quota: int = field(
        default_factory=lambda: _positive_int("QOS_MEDIUM_QUOTA", 2)
    )
    qos_low_quota: int = field(
        default_factory=lambda: _positive_int("QOS_LOW_QUOTA", 1)
    )
    qos_wfq_flow_weights: Mapping[tuple[str, str], float] = field(
        default_factory=_flow_weights
    )
    qos_pending_capacity: int = field(
        default_factory=lambda: _positive_int("QOS_PENDING_CAPACITY", 3000)
    )
    qos_recent_trace_capacity: int = field(
        default_factory=lambda: _positive_int("QOS_RECENT_TRACE_CAPACITY", 1000)
    )
    qos_recent_failure_capacity: int = field(
        default_factory=lambda: _positive_int("QOS_RECENT_FAILURE_CAPACITY", 100)
    )
    qos_drain_timeout_s: float = field(
        default_factory=lambda: _positive_float("QOS_DRAIN_TIMEOUT_S", 30.0)
    )
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

    def effective_qos_config(self) -> dict[str, object]:
        """Return the non-secret QoS policy snapshot for APIs and experiments."""
        return {
            "class_quotas": {
                "high": self.qos_high_quota,
                "medium": self.qos_medium_quota,
                "low": self.qos_low_quota,
            },
            "wfq_flow_weights": {
                f"{device_code}:{sensor_name}": weight
                for (device_code, sensor_name), weight in self.qos_wfq_flow_weights.items()
            },
            "capacities": {
                "transport_messages": self.max_queue_size,
                "pending_work_items": self.qos_pending_capacity,
                "recent_trace_entries": self.qos_recent_trace_capacity,
                "recent_failure_entries": self.qos_recent_failure_capacity,
            },
            "timeouts": {
                "drain_s": self.qos_drain_timeout_s,
            },
        }
