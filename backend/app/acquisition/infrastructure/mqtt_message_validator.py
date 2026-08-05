import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MessageValidationError(ValueError):
    """Raised when a MQTT message payload does not meet the expected structure."""


class MQTTMessageValidator:
    """Validates inbound MQTT payloads before they reach the backend pipeline."""

    REQUIRED_FIELDS = ("device_code", "device_type", "timestamp")
    OPTIONAL_READING_FIELDS = ("temperature", "humidity", "energy")

    def __init__(self) -> None:
        self._invalid_messages: list[dict[str, Any]] = []

    def validate(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise MessageValidationError("Payload must be a JSON object")

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

        if not self._has_reading(payload):
            raise MessageValidationError(
                "Payload must contain at least one telemetry reading field"
            )

        for field in self.OPTIONAL_READING_FIELDS:
            if field in payload and (not isinstance(payload[field], (int, float)) or isinstance(payload[field], bool)):
                raise MessageValidationError(f"Field '{field}' must be numeric")

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
        return any(field in payload for field in cls.OPTIONAL_READING_FIELDS)
