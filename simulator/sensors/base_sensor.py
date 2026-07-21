from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from .sensor_status import SensorStatus


class BaseSensor(ABC):
    """Abstract base for all sensor types in the cold chain simulation."""

    def __init__(
        self,
        device: Any,
        sampling_interval_seconds: float = 10.0,
        status: SensorStatus = SensorStatus.ACTIVE,
    ) -> None:
        self.device = device
        self.sampling_interval_seconds = sampling_interval_seconds
        self.status = status
        self._last_measurement: Any = None

    @abstractmethod
    def read(self) -> Any:
        """Generates and returns a new measurement."""
        ...

    @property
    def last_measurement(self) -> Any:
        """Returns the most recent measurement, if any."""
        return self._last_measurement

    def __repr__(self) -> str:
        return f"{type(self).__name__}(device={self.device.code}, status={self.status.value})"
