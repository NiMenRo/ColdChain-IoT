"""Dual module identity: script-style vs package-style imports.

Production runs `main.py` as a script (top-level `devices`/`sensors`/
`scenarios` modules) while some modules resolve to the `simulator.*`
package copies. The same class then exists twice and `isinstance()` / `==`
across copies fail. Scenario application, device-type grouping and default
ranges must work across copies (duck-typing / `.value` comparison).

On 2026-10-10 this silently disabled every critical scenario in production:
HIGH never applied (no temp>8, no energy off), vitrinas were never targeted,
and cavas got the wrong default range — while all package-style unit tests
stayed green.
"""

import sys
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

SIM_DIR = str(Path(__file__).resolve().parents[1])


def _push_sim_dir():
    if SIM_DIR not in sys.path:
        sys.path.insert(0, SIM_DIR)


def _pop_sim_dir():
    while SIM_DIR in sys.path:
        sys.path.remove(SIM_DIR)
    for mod in [m for m in list(sys.modules)
                if m in ("sensors", "scenarios", "devices")
                or m.startswith(("sensors.", "scenarios.", "devices."))]:
        sys.modules.pop(mod, None)


def test_same_sensor_class_loaded_twice_is_not_identical():
    _push_sim_dir()
    try:
        import sensors.temperature_sensor as ts_top
        from simulator.sensors import temperature_sensor as ts_pkg
        assert ts_top.TemperatureSensor is not ts_pkg.TemperatureSensor
    finally:
        _pop_sim_dir()


def test_scenario_applies_across_duplicate_copies():
    _push_sim_dir()
    try:
        import sensors.temperature_sensor as ts_top
        import sensors.humidity_sensor as hs_top
        import sensors.energy_status_sensor as es_top
        from scenarios import CriticalScenario as TopScenario
        from simulator.devices import ColdRoom
        from simulator.scenarios import CriticalScenarioManager

        device = ColdRoom(id="D", code="C", name="n", location="l")
        temp = ts_top.TemperatureSensor(device=device)
        hum = hs_top.HumiditySensor(device=device)
        energy = es_top.EnergyStatusSensor(device=device)
        device.add_sensor(temp)
        device.add_sensor(hum)
        device.add_sensor(energy)

        manager = CriticalScenarioManager()
        scenario = TopScenario(
            id="SCN-X", name="X", devices=[device],
            temperature_range=(9.0, 12.0),
            humidity_range=(95.0, 100.0),
            energy_state="off",
            duration_seconds=30,
        )
        manager.activate(scenario)
        manager.update()

        assert scenario.active is True
        assert (temp.min_temperature, temp.max_temperature) == (9.0, 12.0)
        assert (hum.min_humidity, hum.max_humidity) == (95.0, 100.0)
        assert 9.0 <= temp.read().value <= 12.0
        assert energy.current_state.value == "off"

        manager.deactivate_all()
        assert energy.current_state.value == "on"
    finally:
        _pop_sim_dir()


def test_device_type_grouping_ignores_enum_identity():
    from simulator.main import _device_type_value, build_scenarios

    class OtherDeviceType(Enum):
        COLD_ROOM = "cold_room"
        REFRIGERATED_SHOWCASE = "refrigerated_showcase"

    assert OtherDeviceType.COLD_ROOM is not __import__(
        "simulator.devices.device_type", fromlist=["DeviceType"]
    ).DeviceType.COLD_ROOM

    vitrina = SimpleNamespace(code="VIT-1", device_type=OtherDeviceType.REFRIGERATED_SHOWCASE)
    cava = SimpleNamespace(code="CAVA-1", device_type=OtherDeviceType.COLD_ROOM)
    assert _device_type_value(vitrina) == "refrigerated_showcase"
    assert _device_type_value(cava) == "cold_room"

    scenarios = build_scenarios([cava, vitrina])
    high = next(s for s in scenarios if s.id == "SCENARIO-HIGH-001")
    assert [d.code for d in high.devices] == ["VIT-1"]
