"""Sensor condition wiring: frontend `condicion` reaches the simulator.

- `select_scenarios(devices, "normal")` -> [] (plain drift, no overrides).
- `select_scenarios(devices, "critica"|None)` -> LOW/MEDIUM/HIGH (current behavior).
- `publish_cycle` with [] publishes once per device without touching ranges.
"""

from simulator.devices import ColdRoom, RefrigeratedShowcase
from simulator.main import build_scenarios, publish_cycle, select_scenarios
from simulator.scenarios import CriticalScenarioManager
from simulator.sensors import EnergyStatusSensor, HumiditySensor, TemperatureSensor


def _device(cls, code):
    device = cls(id=f"DEV-{code}", code=code, name=code, location="Lab")
    device.add_sensor(TemperatureSensor(device=device, min_temperature=0.0, max_temperature=4.0))
    device.add_sensor(HumiditySensor(device=device))
    device.add_sensor(EnergyStatusSensor(device=device))
    return device


def _recorder():
    calls = []

    class _Publisher:
        def publish_telemetry(self, device, measurements=None):
            calls.append((device.code, dict(measurements or {})))
            return True

    return calls, _Publisher()


def test_select_scenarios_filters_by_condition():
    devices = [_device(ColdRoom, "CAVA-1"), _device(RefrigeratedShowcase, "VIT-1")]
    assert select_scenarios(devices, "normal") == []
    critical = select_scenarios(devices, "critica")
    assert [s.id for s in critical] == ["SCENARIO-LOW-001", "SCENARIO-MEDIUM-001", "SCENARIO-HIGH-001"]
    legacy = select_scenarios(devices, None)
    assert [s.id for s in legacy] == [s.id for s in critical]
    assert [s.id for s in build_scenarios(devices)] == [s.id for s in critical]


def test_publish_cycle_without_scenarios_is_plain_drift():
    devices = [_device(ColdRoom, "CAVA-1"), _device(RefrigeratedShowcase, "VIT-1")]
    calls, publisher = _recorder()
    manager = CriticalScenarioManager()
    publish_cycle(devices, [], manager, publisher, sampling_interval=0)
    assert sorted(code for code, _ in calls) == ["CAVA-1", "VIT-1"]
    assert manager.get_active_scenarios() == []
    for device in devices:
        temp = next(s for s in device.get_sensors() if isinstance(s, TemperatureSensor))
        assert (temp.min_temperature, temp.max_temperature) == (0.0, 4.0)
        assert 0.0 <= temp.current_temperature <= 4.0


def test_publish_cycle_with_critical_scenarios_applies_high():
    devices = [_device(RefrigeratedShowcase, "VIT-1")]
    calls, publisher = _recorder()
    manager = CriticalScenarioManager()
    publish_cycle(devices, select_scenarios(devices, "critica"), manager, publisher, sampling_interval=0)
    # One publish per device per scenario (LOW/MEDIUM/HIGH).
    assert len(calls) == 3
    temp = next(s for s in devices[0].get_sensors() if isinstance(s, TemperatureSensor))
    # HIGH ran last: override window applied.
    assert (temp.min_temperature, temp.max_temperature) == (9.0, 12.0)
