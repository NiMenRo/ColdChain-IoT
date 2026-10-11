import time

from simulator.devices import ColdRoom
from simulator.scenarios import CriticalScenario, CriticalScenarioManager
from simulator.sensors import (
    TemperatureSensor,
    HumiditySensor,
    EnergyStatusSensor,
    EnergyState,
)


def test_critical_scenario_updates_and_restores_sensor_behavior():
    device = ColdRoom(
        id="DEV-TEST",
        code="CAVA-TEST",
        name="Cava Test",
        location="Lab",
    )

    temp_sensor = TemperatureSensor(device=device)
    hum_sensor = HumiditySensor(device=device)
    energy_sensor = EnergyStatusSensor(device=device)

    device.add_sensor(temp_sensor)
    device.add_sensor(hum_sensor)
    device.add_sensor(energy_sensor)

    original_temp_min = temp_sensor.min_temperature
    original_temp_max = temp_sensor.max_temperature
    original_humidity_min = hum_sensor.min_humidity
    original_humidity_max = hum_sensor.max_humidity

    manager = CriticalScenarioManager()
    scenario = CriticalScenario(
        id="SCN-001",
        name="Escenario crítico de prueba",
        devices=[device],
        temperature_range=(10.0, 12.0),
        humidity_range=(95.0, 100.0),
        energy_state=EnergyState.OFF,
        duration_seconds=0.1,
    )

    manager.activate(scenario)

    assert scenario.devices[0] is device
    assert scenario.active is True
    assert temp_sensor.min_temperature == 10.0
    assert temp_sensor.max_temperature == 12.0
    assert hum_sensor.min_humidity == 95.0
    assert hum_sensor.max_humidity == 100.0
    assert energy_sensor.current_state == EnergyState.OFF

    # Simulate reading generation with altered behavior
    temp_read = temp_sensor.read()
    hum_read = hum_sensor.read()
    energy_read = energy_sensor.read()

    assert temp_read.device_code == device.code
    assert hum_read.device_code == device.code
    assert energy_read.device_code == device.code

    time.sleep(0.2)
    manager.update()

    assert len(manager.get_active_scenarios()) == 0
    assert temp_sensor.min_temperature == original_temp_min
    assert temp_sensor.max_temperature == original_temp_max
    assert hum_sensor.min_humidity == original_humidity_min
    assert hum_sensor.max_humidity == original_humidity_max
    assert energy_sensor.current_state == EnergyState.ON


def test_activate_anchors_duration_at_activation_time():
    """Late scenarios (e.g. HIGH, third in a cycle) must not be born expired.

    Regression: started_at was frozen at build time, so with
    duration_seconds=2.0 the HIGH scenario expired in update() right after
    activate() and published normal drift instead of critical values.
    """
    from datetime import datetime, timedelta

    device = ColdRoom(
        id="DEV-LATE",
        code="CAVA-LATE",
        name="Cava Late",
        location="Lab",
    )
    temp_sensor = TemperatureSensor(device=device)
    device.add_sensor(temp_sensor)

    manager = CriticalScenarioManager()
    scenario = CriticalScenario(
        id="SCN-LATE",
        name="Escenario tardío",
        devices=[device],
        temperature_range=(9.0, 12.0),
        duration_seconds=2.0,
    )
    # Simulate a cycle that reaches this scenario seconds after build.
    scenario.started_at = datetime.now() - timedelta(seconds=10)
    scenario.finished_at = scenario.started_at + timedelta(seconds=2.0)

    manager.activate(scenario)
    manager.update()

    assert scenario.active is True
    assert scenario in manager.get_active_scenarios()
    assert temp_sensor.min_temperature == 9.0
    assert temp_sensor.max_temperature == 12.0
    reading = temp_sensor.read()
    assert 9.0 <= reading.value <= 12.0