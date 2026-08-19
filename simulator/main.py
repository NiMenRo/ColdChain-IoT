import logging
import os
import sys
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if __package__ in (None, ""):
    from config import SimulatorConfig
    from devices import ColdRoom, RefrigeratedShowcase, DeviceStatus
    from mqtt import MQTTClient, DevicePublisher
    from scenarios import CriticalScenario, CriticalScenarioManager
    from sensors import TemperatureSensor, HumiditySensor, EnergyStatusSensor, EnergyState
else:  # pragma: no cover - package-style execution from repo root
    from simulator.config import SimulatorConfig
    from simulator.devices import ColdRoom, RefrigeratedShowcase, DeviceStatus
    from simulator.mqtt import MQTTClient, DevicePublisher
    from simulator.scenarios import CriticalScenario, CriticalScenarioManager
    from simulator.sensors import TemperatureSensor, HumiditySensor, EnergyStatusSensor, EnergyState


def main() -> None:
    config = SimulatorConfig()

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    mqtt_client = MQTTClient(config.mqtt_host, config.mqtt_port)
    mqtt_client.start()

    device_publisher = DevicePublisher(mqtt_client, config.topic_prefix, config.mqtt_qos)

    # --- Devices ---
    cava_principal = ColdRoom(
        id="DEV-001",
        code="CAVA-001",
        name="Cava Principal",
        location="Sótano - Sector A",
    )

    cava_secundaria = ColdRoom(
        id="DEV-002",
        code="CAVA-002",
        name="Cava Secundaria",
        location="Sótano - Sector B",
        status=DeviceStatus.MAINTENANCE,
    )

    vitrina = RefrigeratedShowcase(
        id="DEV-003",
        code="VITRINA-001",
        name="Vitrina Mostrador 1",
        location="Salón Principal - Zona Clientes",
    )

    # --- Sensors ---
    temp_sensor_1 = TemperatureSensor(device=cava_principal, min_temperature=2.0, max_temperature=6.0)
    temp_sensor_2 = TemperatureSensor(device=cava_secundaria, min_temperature=0.0, max_temperature=4.0)
    temp_sensor_3 = TemperatureSensor(device=vitrina, min_temperature=3.0, max_temperature=8.0)

    hum_sensor_1 = HumiditySensor(device=cava_principal)
    hum_sensor_2 = HumiditySensor(device=cava_secundaria)
    hum_sensor_3 = HumiditySensor(device=vitrina)

    energy_sensor_1 = EnergyStatusSensor(device=cava_principal)
    energy_sensor_2 = EnergyStatusSensor(device=cava_secundaria, initial_state=EnergyState.POWERED)
    energy_sensor_3 = EnergyStatusSensor(device=vitrina)

    cava_principal.add_sensor(temp_sensor_1)
    cava_principal.add_sensor(hum_sensor_1)
    cava_principal.add_sensor(energy_sensor_1)
    cava_secundaria.add_sensor(temp_sensor_2)
    cava_secundaria.add_sensor(hum_sensor_2)
    cava_secundaria.add_sensor(energy_sensor_2)
    vitrina.add_sensor(temp_sensor_3)
    vitrina.add_sensor(hum_sensor_3)
    vitrina.add_sensor(energy_sensor_3)

    devices = [cava_principal, cava_secundaria, vitrina]

    critical_manager = CriticalScenarioManager()
    scenarios = [
        CriticalScenario(
            id="SCENARIO-LOW-001",
            name="Alerta baja - frío insuficiente para carne",
            devices=[vitrina],
            temperature_range=(4.5, 6.0),
            humidity_range=(78.0, 82.0),
            energy_state=EnergyState.ON,
            duration_seconds=2.0,
        ),
        CriticalScenario(
            id="SCENARIO-MEDIUM-001",
            name="Alerta media - pérdida parcial del frío",
            devices=[vitrina],
            temperature_range=(6.5, 8.0),
            humidity_range=(72.0, 78.0),
            energy_state=EnergyState.ON,
            duration_seconds=2.0,
        ),
        CriticalScenario(
            id="SCENARIO-HIGH-001",
            name="Alerta alta - fallo eléctrico / descongelación",
            devices=[vitrina],
            temperature_range=(9.0, 12.0),
            humidity_range=(95.0, 100.0),
            energy_state=EnergyState.OFF,
            duration_seconds=2.0,
        ),
    ]

    # --- Measurements ---
    print("=" * 60)
    print("Simulación de cuarto frío para almacenamiento de carne.")
    print("Se alternan escenarios de baja, media y alta criticidad.")
    print("La pérdida de energía o el aumento de temperatura afectan directamente el riesgo de la carne.")
    print("=" * 60)

    try:
        for cycle_index, scenario in enumerate(scenarios, start=1):
            critical_manager.deactivate_all()
            critical_manager.activate(scenario)
            print(f"\n  --- Ciclo {cycle_index}: {scenario.name} ---")

            critical_manager.update()

            for device in devices:
                print()
                print(f"  {device.code}")
                print(f"  {'-' * 30}")

                measurements = {}
                for sensor in device.get_sensors():
                    measurement = sensor.read()
                    measurements[sensor] = measurement

                    if hasattr(sensor, "min_temperature"):
                        label = "Temperatura"
                        state = sensor.current_temperature
                    elif hasattr(sensor, "min_humidity"):
                        label = "Humedad"
                        state = sensor.current_humidity
                    elif hasattr(sensor, "current_state"):
                        label = "Estado energético"
                        state = sensor.current_state.value
                    else:
                        continue

                    print(f"  {label}:")
                    print(f"  {measurement.value} {measurement.unit}")
                    print(f"  Hora:")
                    print(f"  {measurement.timestamp.strftime('%H:%M:%S')}")
                    print(f"  (estado interno: {state} {measurement.unit})")

                device_publisher.publish_telemetry(device, measurements)

                print(f"  {'-' * 30}")

            time.sleep(config.sampling_interval)

        print("=" * 60)
    finally:
        mqtt_client.stop()


if __name__ == "__main__":
    main()
