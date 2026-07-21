from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from .device_type import DeviceType, DeviceStatus

if TYPE_CHECKING:
    from sensors.base_sensor import BaseSensor


@dataclass
class Device:
    """Represents a physical IoT device in the cold chain."""

    id: str
    code: str
    name: str
    location: str
    device_type: DeviceType
    status: DeviceStatus = DeviceStatus.ACTIVE
    registration_date: datetime = field(default_factory=datetime.now)

    sensors: list[BaseSensor] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"[{self.code}] {self.name} | "
            f"{self.location} | "
            f"{self.device_type.value} | "
            f"{self.status.value}"
        )

    def short_info(self) -> str:
        """Returns a one-line summary of the device."""
        return f"{self.code} - {self.name} ({self.status.value})"

    def add_sensor(self, sensor: BaseSensor) -> None:
        """Associates a sensor with this device."""
        self.sensors.append(sensor)

    def remove_sensor(self, sensor: BaseSensor) -> None:
        """Removes a sensor from this device, if present."""
        if sensor in self.sensors:
            self.sensors.remove(sensor)

    def get_sensors(self) -> list[BaseSensor]:
        """Returns all sensors currently associated with this device."""
        return list(self.sensors)
