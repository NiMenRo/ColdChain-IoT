from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Union

from .base_sensor import BaseSensor
from .sensor_status import SensorStatus


class EnergyState(str, Enum):
    """Represents the electrical feed state of a refrigerated device.

    The accepted values are the natural on/off states that map cleanly to the
    physical notion of an energized refrigerated cabinet.
    """

    ON = "on"
    POWERED = "on"
    OFF = "off"
    POWER_LOSS = "off"
    POWER_FAILURE = "off"


EnergyStatus = EnergyState
PowerState = EnergyState


@dataclass
class EnergyStatusMeasurement:
    """A single electrical supply-state reading from a sensor."""

    device_code: str
    value: str
    timestamp: datetime
    unit: str = "state"

    def __str__(self) -> str:
        return f"{self.value} {self.unit}"


class EnergyStatusSensor(BaseSensor):
    """Simulates the energy feed state for a refrigerated IoT device.

    The sensor keeps the current electrical state unchanged until an external
    scenario intentionally updates it. Every state transition records the
    timestamp when the new state became active.
    """

    def __init__(
        self,
        device: Any,
        initial_state: Union[EnergyState, str] = EnergyState.ON,
        sampling_interval_seconds: float = 10.0,
        status: SensorStatus = SensorStatus.ACTIVE,
    ) -> None:
        super().__init__(
            device=device,
            sampling_interval_seconds=sampling_interval_seconds,
            status=status,
        )
        self.current_state = self._normalize_state(initial_state)
        self.current_energy_state = self.current_state
        self.last_state_change_timestamp = datetime.now()

    @staticmethod
    def _normalize_state(state: Union[EnergyState, str]) -> EnergyState:
        if isinstance(state, EnergyState):
            return state
        if isinstance(state, str):
            normalized = state.strip().lower()
            for option in EnergyState:
                if option.value == normalized:
                    return option
        raise ValueError(f"Unsupported energy state value: {state}")

    @property
    def state(self) -> EnergyState:
        return self.current_state

    @state.setter
    def state(self, new_state: Union[EnergyState, str]) -> None:
        self.current_state = self._normalize_state(new_state)
        self.current_energy_state = self.current_state
        self.last_state_change_timestamp = datetime.now()

    @property
    def current_power_state(self) -> EnergyState:
        return self.current_state

    @current_power_state.setter
    def current_power_state(self, new_state: Union[EnergyState, str]) -> None:
        self.state = new_state

    @property
    def is_powered(self) -> bool:
        return self.current_state == EnergyState.ON

    def set_state(self, new_state: Union[EnergyState, str]) -> EnergyState:
        """Updates the persisted energy state and records the change moment."""
        self.state = new_state
        return self.current_state

    def set_power_state(self, new_state: Union[EnergyState, str]) -> EnergyState:
        """Alias to keep the API aligned with the power-supply domain."""
        return self.set_state(new_state)

    def read(self) -> EnergyStatusMeasurement:
        """Returns the currently persisted energy state as a SensorReading-like payload."""
        measurement = EnergyStatusMeasurement(
            device_code=self.device.code,
            value=self.current_state.value,
            timestamp=self.last_state_change_timestamp,
        )
        self._last_measurement = measurement
        return measurement


EnergyStateSensor = EnergyStatusSensor
PowerStateSensor = EnergyStatusSensor
