from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from ..telemetry_trace import emission_trace

logger = logging.getLogger(__name__)


class MessageValidationError(ValueError):
    """Raised when a MQTT message payload does not meet the expected structure."""


class MQTTMessageValidator:
    """Validates inbound MQTT payloads before they reach the backend pipeline."""

    REQUIRED_FIELDS = ("device_code", "device_type", "timestamp")
    NUMERIC_READING_FIELDS = ("temperature", "humidity")
    ENERGY_VALID_STATES = ("on", "off")

    def __init__(self) -> None:
        self._invalid_messages: list[dict[str, Any]] = []

    def validate(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise MessageValidationError("Payload must be a JSON object")
        try:
            emission_trace(payload)
        except (ValueError, TypeError, AttributeError) as exc:
            raise MessageValidationError(f"Invalid emission trace: {exc}") from exc

        missing_fields = [field for field in self.REQUIRED_FIELDS if field not in payload]
        if missing_fields:
            raise MessageValidationError(
                f"Missing required fields: {', '.join(missing_fields)}"
            )

        for field in self.REQUIRED_FIELDS:
            value = payload[field]
            if not isinstance(value, str) or not value.strip():
                raise MessageValidationError(f"Field '{field}' must be a non-empty string")

        try:
            datetime.fromisoformat(payload["timestamp"])
        except ValueError as exc:
            raise MessageValidationError("Field 'timestamp' must be a valid ISO-8601 datetime") from exc

        if "reading_timestamps" in payload:
            times = payload["reading_timestamps"]
            if not isinstance(times, dict) or any(
                name not in ("temperature", "humidity", "energy") or name not in payload
                for name in times
            ):
                raise MessageValidationError("reading_timestamps must map present sensors to ISO timestamps")
            for value in times.values():
                try:
                    if not isinstance(value, str):
                        raise ValueError("timestamp must be a string")
                    datetime.fromisoformat(value)
                except ValueError as exc:
                    raise MessageValidationError("Invalid per-sensor timestamp") from exc

        if not self._has_reading(payload):
            raise MessageValidationError(
                "Payload must contain at least one telemetry reading field"
            )

        for field in self.NUMERIC_READING_FIELDS:
            if field in payload and (not isinstance(payload[field], (int, float)) or isinstance(payload[field], bool)):
                raise MessageValidationError(f"Field '{field}' must be numeric")

        if "energy" in payload:
            # TSK-059.4 — canonical energy representation is on/off (lowercase).
            # Numeric payloads are rejected: no producer or test sends them.
            energy_val = payload["energy"]
            if isinstance(energy_val, str):
                if energy_val.strip().lower() not in self.ENERGY_VALID_STATES:
                    raise MessageValidationError("Field 'energy' must be 'on' or 'off'")
            else:
                raise MessageValidationError("Field 'energy' must be 'on' or 'off'")

        return payload

    def register_invalid(self, payload: Any, reason: str, topic: Optional[str] = None) -> None:
        self._invalid_messages.append(
            {
                "topic": topic,
                "reason": reason,
                "payload": payload,
            }
        )

    def get_invalid_messages(self) -> list[dict[str, Any]]:
        return list(self._invalid_messages)

    @classmethod
    def _has_reading(cls, payload: dict[str, Any]) -> bool:
        return any(field in payload for field in cls.NUMERIC_READING_FIELDS + ("energy",))
