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
    from devices.device_type import DeviceType
    from devices.factory import orm_to_device
    from mqtt import MQTTClient, DevicePublisher
    from scenarios import CriticalScenario, CriticalScenarioManager
    from sensors import TemperatureSensor, HumiditySensor, EnergyStatusSensor, EnergyState
else:  # pragma: no cover - package-style execution from repo root
    from simulator.config import SimulatorConfig
    from simulator.devices import ColdRoom, RefrigeratedShowcase, DeviceStatus
    from simulator.devices.device_type import DeviceType
    from simulator.devices.factory import orm_to_device
    from simulator.mqtt import MQTTClient, DevicePublisher
    from simulator.scenarios import CriticalScenario, CriticalScenarioManager
    from simulator.sensors import TemperatureSensor, HumiditySensor, EnergyStatusSensor, EnergyState


def main() -> None:
    config = SimulatorConfig()

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    mqtt_username, mqtt_password, mqtt_ca_cert = config.mqtt_credentials()
    mqtt_client = MQTTClient(
        config.mqtt_host,
        config.mqtt_port,
        username=mqtt_username,
        password=mqtt_password,
        tls_ca_cert=mqtt_ca_cert,
    )
    mqtt_client.start()

    device_publisher = DevicePublisher(mqtt_client, config.topic_prefix, config.mqtt_qos)

    # --- Devices (DB is the single source of truth) ---
    from simulator.database.session import SessionLocal

    orm_devices = None
    for attempt in range(15):
        try:
            with SessionLocal() as db:
                # Direct DB access via DeviceRepository pattern without importing backend
                from sqlalchemy import text as _sa_text

                # Use DeviceRepository logic via direct query to avoid backend import cycle
                # Ordered by code to keep deterministic display
                rows = db.execute(_sa_text("SELECT id, code, name, location, device_type, status, registration_date FROM devices ORDER BY code ASC")).fetchall()
                if rows:
                    # Map rows to ORM-like objects for factory
                    class _Row:
                        pass

                    orm_devices = []
                    for r in rows:
                        o = _Row()
                        o.id, o.code, o.name, o.location, o.device_type, o.status, o.registration_date = r
                        orm_devices.append(o)
                    break
                else:
                    logging.getLogger(__name__).warning("No devices in DB (attempt %d/15) — waiting for seed", attempt + 1)
        except Exception as e:
            logging.getLogger(__name__).warning("DB fetch failed (attempt %d/15): %s", attempt + 1, e)
        time.sleep(1)

    if not orm_devices:
        logging.getLogger(__name__).error("No devices available or DB unreachable — aborting simulator (DB is source of truth, no hardcoded fallback)")
        mqtt_client.stop()
        sys.exit(1)

    devices = [orm_to_device(o) for o in orm_devices]

    # --- Sensors (by device_type, no code-specific logic) ---
    for device in devices:
        if device.device_type == DeviceType.COLD_ROOM:
            temp_range = (0.0, 4.0)
        else:  # REFRIGERATED_SHOWCASE
            temp_range = (3.0, 8.0)
        device.add_sensor(TemperatureSensor(device=device, min_temperature=temp_range[0], max_temperature=temp_range[1]))
        device.add_sensor(HumiditySensor(device=device))
        initial = EnergyState.POWERED if device.status == DeviceStatus.MAINTENANCE else EnergyState.ON
        device.add_sensor(EnergyStatusSensor(device=device, initial_state=initial))

    # --- Critical scenarios (resolved by device_type, no hardcoded VITRINA-001) ---
    by_type: dict[DeviceType, list] = {}
    for d in devices:
        by_type.setdefault(d.device_type, []).append(d)
    target_devices = by_type.get(DeviceType.REFRIGERATED_SHOWCASE) or devices[:1]

    critical_manager = CriticalScenarioManager()
    scenarios = [
        CriticalScenario(
            id="SCENARIO-LOW-001",
            name="Alerta baja - frío insuficiente para carne",
            devices=list(target_devices),
            temperature_range=(4.5, 6.0),
            humidity_range=(78.0, 82.0),
            energy_state=EnergyState.ON,
            duration_seconds=2.0,
        ),
        CriticalScenario(
            id="SCENARIO-MEDIUM-001",
            name="Alerta media - pérdida parcial del frío",
            devices=list(target_devices),
            temperature_range=(6.5, 8.0),
            humidity_range=(72.0, 78.0),
            energy_state=EnergyState.ON,
            duration_seconds=2.0,
        ),
        CriticalScenario(
            id="SCENARIO-HIGH-001",
            name="Alerta alta - fallo eléctrico / descongelación",
            devices=list(target_devices),
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
