from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .base_sensor import BaseSensor
from .sensor_status import SensorStatus


@dataclass
class HumidityMeasurement:
    """A single humidity reading from a sensor."""

    device_code: str
    value: float
    timestamp: datetime
    unit: str = "%"

    def __str__(self) -> str:
        return f"{self.value} {self.unit}"


class HumiditySensor(BaseSensor):
    """Simulates a humidity sensor attached to a cold chain device.

    The humidity evolves gradually from a starting value using small
    random increments bounded by *drift_range*, and is always clamped
    within [*min_humidity*, *max_humidity*].
    """

    def __init__(
        self,
        device: Any,
        min_humidity: float = 60.0,
        max_humidity: float = 90.0,
        sampling_interval_seconds: float = 10.0,
        drift_range: tuple[float, float] = (-1.0, 1.0),
        status: SensorStatus = SensorStatus.ACTIVE,
    ) -> None:
        super().__init__(
            device=device,
            sampling_interval_seconds=sampling_interval_seconds,
            status=status,
        )
        self.min_humidity = min_humidity
        self.max_humidity = max_humidity
        self.drift_range = drift_range
        self.current_humidity = round(
            random.uniform(min_humidity, max_humidity), 1
        )

    def read(self) -> HumidityMeasurement:
        """Advances *current_humidity* by a small random step and returns it."""

        delta = round(random.uniform(*self.drift_range), 1)
        next_hum = round(self.current_humidity + delta, 1)
        next_hum = max(self.min_humidity, min(next_hum, self.max_humidity))
        self.current_humidity = next_hum

        measurement = HumidityMeasurement(
            device_code=self.device.code,
            value=next_hum,
            timestamp=datetime.now(),
        )
        self._last_measurement = measurement
        return measurement
