from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class NormalizedReading:
    """Uniform structure for all telemetry readings."""

    device_code: str
    device_type: str
    sensor_name: str
    value: float
    timestamp: str
    raw_value: Any


class TelemetryNormalizer:
    """Transforms validated MQTT readings into a standard internal representation."""

    SENSOR_FIELDS = {
        "temperature": "temperature",
        "humidity": "humidity",
        "energy": "energy",
    }

    ENERGY_STATE_MAP = {
        "on": 1.0,
        "off": 0.0,
    }

    @classmethod
    def _normalize_value(cls, field_name: str, value: Any) -> float:
        if field_name == "energy":
            if isinstance(value, str):
                return float(cls.ENERGY_STATE_MAP.get(value.strip().lower(), 0.0))
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
            raise ValueError("Energy value must be numeric or 'on'/'off'")

        return float(value)

    def normalize(self, message: dict[str, Any]) -> list[NormalizedReading]:
        payload = message.get("payload", {})
        device_origin = message.get("device_origin", {})
        device_code = device_origin.get("device_code")
        device_type = device_origin.get("device_type")

        if not isinstance(device_code, str) or not device_code.strip():
            raise ValueError("Device code is required for normalization")
        if not isinstance(device_type, str) or not device_type.strip():
            raise ValueError("Device type is required for normalization")

        timestamp = payload.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp.strip():
            raise ValueError("Timestamp is required for normalization")

        normalized_readings: list[NormalizedReading] = []
        for field_name, sensor_name in self.SENSOR_FIELDS.items():
            if field_name in payload:
                value = payload[field_name]
                normalized_readings.append(
                    NormalizedReading(
                        device_code=device_code,
                        device_type=device_type,
                        sensor_name=sensor_name,
                        value=self._normalize_value(field_name, value),
                        timestamp=timestamp,
                        raw_value=value,
                    )
                )

        if not normalized_readings:
            raise ValueError("No readable telemetry fields found")

        return normalized_readings
