from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

try:
    from devices import Device
    from sensors import EnergyState, EnergyStatusSensor, HumiditySensor, TemperatureSensor
except ModuleNotFoundError:  # pragma: no cover - fallback for package-style imports
    from simulator.devices import Device
    from simulator.sensors import EnergyState, EnergyStatusSensor, HumiditySensor, TemperatureSensor


@dataclass
class CriticalScenario:
    """Definition of a temporary critical condition over one or more devices."""

    id: str
    name: str
    devices: list[Device]
    temperature_range: Optional[tuple[float, float]] = None
    humidity_range: Optional[tuple[float, float]] = None
    energy_state: Optional[EnergyState | str] = None
    duration_seconds: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    active: bool = False
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        self.started_at = self.started_at or datetime.now()
        if self.duration_seconds is not None:
            self.finished_at = self.started_at + timedelta(seconds=self.duration_seconds)

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        if self.finished_at is None:
            return False
        current_time = now or datetime.now()
        return current_time >= self.finished_at


class CriticalScenarioManager:
    """Applies and removes temporary critical conditions over simulator devices."""

    def __init__(self) -> None:
        self._active_scenarios: list[CriticalScenario] = []

    def activate(self, scenario: CriticalScenario) -> CriticalScenario:
        """Configures the associated sensors to follow the scenario behavior."""
        scenario.active = True
        scenario.started_at = scenario.started_at or datetime.now()
        if scenario.duration_seconds is not None:
            scenario.finished_at = scenario.started_at + timedelta(seconds=scenario.duration_seconds)

        for device in scenario.devices:
            self._apply_scenario_to_device(device=device, scenario=scenario)

        self._active_scenarios.append(scenario)
        return scenario

    def deactivate(self, scenario: CriticalScenario) -> None:
        """Restores the attached sensors back to their normal operating behavior."""
        if scenario not in self._active_scenarios:
            return

        for device in scenario.devices:
            self._restore_device_sensors(device=device)

        scenario.active = False
        scenario.finished_at = datetime.now()
        self._active_scenarios.remove(scenario)

    def deactivate_all(self) -> None:
        """Removes every currently active scenario and restores normal behavior."""
        for scenario in list(self._active_scenarios):
            self.deactivate(scenario)

    def update(self) -> None:
        """Automatically expires scenarios whose configured duration has elapsed."""
        for scenario in list(self._active_scenarios):
            if scenario.is_expired():
                self.deactivate(scenario)

    def get_active_scenarios(self) -> list[CriticalScenario]:
        return list(self._active_scenarios)

    @staticmethod
    def _apply_scenario_to_device(device: Device, scenario: CriticalScenario) -> None:
        for sensor in device.get_sensors():
            if isinstance(sensor, TemperatureSensor) and scenario.temperature_range is not None:
                sensor.apply_behavior_override(
                    {
                        "temperature_range": scenario.temperature_range,
                    }
                )

            if isinstance(sensor, HumiditySensor) and scenario.humidity_range is not None:
                sensor.apply_behavior_override(
                    {
                        "humidity_range": scenario.humidity_range,
                    }
                )

            if isinstance(sensor, EnergyStatusSensor) and scenario.energy_state is not None:
                sensor.set_state(scenario.energy_state)

    @staticmethod
    def _restore_device_sensors(device: Device) -> None:
        for sensor in device.get_sensors():
            if hasattr(sensor, "restore_behavior"):
                sensor.restore_behavior()

            if isinstance(sensor, EnergyStatusSensor):
                sensor.set_state(EnergyState.ON)
