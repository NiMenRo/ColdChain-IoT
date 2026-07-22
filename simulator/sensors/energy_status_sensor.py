from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Union

from .base_sensor import BaseSensor
from .sensor_status import SensorStatus


class EnergyState(str, Enum):
    """Represents the electrical feed state of a refrigerated device."""

    POWERED = "powered"
    ON = "powered"
    POWER_LOSS = "power_loss"
    POWER_FAILURE = "power_loss"
    OFF = "power_loss"


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
    simulation scenario calls one of the state update methods.
    """

    def __init__(
        self,
        device: Any,
        initial_state: Union[EnergyState, str] = EnergyState.POWERED,
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

    @property
    def current_power_state(self) -> EnergyState:
        return self.current_state

    @current_power_state.setter
    def current_power_state(self, new_state: Union[EnergyState, str]) -> None:
        self.state = new_state

    @property
    def is_powered(self) -> bool:
        return self.current_state == EnergyState.POWERED

    def set_state(self, new_state: Union[EnergyState, str]) -> EnergyState:
        """Updates the persisted energy state.

        The state remains stable between scenario changes.
        """
        self.state = new_state
        return self.current_state

    def set_power_state(self, new_state: Union[EnergyState, str]) -> EnergyState:
        """Alias to keep the API aligned with the power-supply domain."""
        return self.set_state(new_state)

    def read(self) -> EnergyStatusMeasurement:
        """Returns the last persisted energy state as a reading."""
        measurement = EnergyStatusMeasurement(
            device_code=self.device.code,
            value=self.current_state.value,
            timestamp=datetime.now(),
        )
        self._last_measurement = measurement
        return measurement


EnergyStateSensor = EnergyStatusSensor
PowerStateSensor = EnergyStatusSensor
