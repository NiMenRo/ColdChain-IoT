from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class DeviceOrigin:
    """Represents the device information extracted from an MQTT message."""

    device_code: str
    device_type: str
    raw_payload: dict[str, Any]


class DeviceOriginIdentifier:
    """Extracts the originating device from a validated MQTT payload."""

    def identify(self, payload: dict[str, Any]) -> DeviceOrigin:
        device_code = payload.get("device_code")
        device_type = payload.get("device_type")

        if not isinstance(device_code, str) or not device_code.strip():
            raise ValueError("Device code is required")
        if not isinstance(device_type, str) or not device_type.strip():
            raise ValueError("Device type is required")

        return DeviceOrigin(
            device_code=device_code,
            device_type=device_type,
            raw_payload=payload,
        )
