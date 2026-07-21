from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .base_sensor import BaseSensor
from .sensor_status import SensorStatus


@dataclass
class TemperatureMeasurement:
    """A single temperature reading from a sensor."""

    device_code: str
    value: float
    timestamp: datetime
    unit: str = "°C"

    def __str__(self) -> str:
        return f"{self.value} {self.unit}"


class TemperatureSensor(BaseSensor):
    """Simulates a temperature sensor attached to a cold chain device.

    The temperature evolves gradually from a starting value using small
    random increments bounded by *drift_range*, and is always clamped
    within [*min_temperature*, *max_temperature*].
    """

    def __init__(
        self,
        device: Any,
        min_temperature: float = -2.0,
        max_temperature: float = 8.0,
        sampling_interval_seconds: float = 10.0,
        drift_range: tuple[float, float] = (-0.3, 0.3),
        status: SensorStatus = SensorStatus.ACTIVE,
    ) -> None:
        super().__init__(
            device=device,
            sampling_interval_seconds=sampling_interval_seconds,
            status=status,
        )
        self.min_temperature = min_temperature
        self.max_temperature = max_temperature
        self.drift_range = drift_range
        self.current_temperature = round(
            random.uniform(min_temperature, max_temperature), 1
        )

    def read(self) -> TemperatureMeasurement:
        """Advances *current_temperature* by a small random step and returns it."""

        delta = round(random.uniform(*self.drift_range), 1)
        next_temp = round(self.current_temperature + delta, 1)
        next_temp = max(self.min_temperature, min(next_temp, self.max_temperature))
        self.current_temperature = next_temp

        measurement = TemperatureMeasurement(
            device_code=self.device.code,
            value=next_temp,
            timestamp=datetime.now(),
        )
        self._last_measurement = measurement
        return measurement
