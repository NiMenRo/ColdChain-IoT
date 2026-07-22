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

    # Simulamos la generación de lectura con el comportamiento alterado
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