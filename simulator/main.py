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


def load_devices():
    """Load devices + enabled sensors from DB (single source of truth).

    Returns the device list (possibly empty). Retries briefly on DB
    errors. Devices created while running join on the next cycle.
    """
    from simulator.database.session import SessionLocal

    orm_devices = []
    sensor_by_device = []
    for attempt in range(15):
        try:
            with SessionLocal() as db:
                # Direct DB access via DeviceRepository pattern without importing backend
                from sqlalchemy import text as _sa_text

                # Use DeviceRepository logic via direct query to avoid backend import cycle
                # Ordered by code to keep deterministic display
                rows = db.execute(_sa_text("SELECT id, code, name, location, device_type, status, registration_date FROM devices ORDER BY code ASC")).fetchall()
                # TSK-059.3 — DeviceSensor is the single source of truth for
                # enabled sensors; no parallel sensor configuration exists.
                sensor_rows = db.execute(_sa_text("SELECT device_id, sensor_type FROM device_sensors")).fetchall()
                if rows:
                    sensor_by_device = sensor_rows
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
        return []

    devices = [orm_to_device(o) for o in orm_devices]

    # --- Sensors (DeviceSensor is the single source of truth, TSK-059.3) ---
    enabled_by_device: dict[str, set[str]] = {}
    for device_id, sensor_type in sensor_by_device:
        enabled_by_device.setdefault(str(device_id), set()).add(str(sensor_type).strip().lower())
    ready = []
    for device in devices:
        enabled = enabled_by_device.get(str(device.id), set())
        if not enabled:
            logging.getLogger(__name__).warning(
                "Device %s has no configured sensors in device_sensors — skipped (no hardcoded fallback)",
                device.code,
            )
            continue
        if _device_type_value(device) == DeviceType.COLD_ROOM.value:
            temp_range = (0.0, 4.0)
        else:  # REFRIGERATED_SHOWCASE
            temp_range = (3.0, 8.0)
        if "temperature" in enabled:
            device.add_sensor(TemperatureSensor(device=device, min_temperature=temp_range[0], max_temperature=temp_range[1]))
        if "humidity" in enabled:
            device.add_sensor(HumiditySensor(device=device))
        if "energy" in enabled:
            initial = EnergyState.POWERED if device.status == DeviceStatus.MAINTENANCE else EnergyState.ON
            device.add_sensor(EnergyStatusSensor(device=device, initial_state=initial))
        ready.append(device)
    return ready


def _device_type_value(device) -> str:
    """Device-type string without relying on enum identity.

    Devices may carry a DeviceType from a duplicated module copy
    (script-style vs package-style imports), where `==` across copies is
    always False. Comparing `.value` strings is immune to that.
    """
    device_type = getattr(device, "device_type", None)
    return str(getattr(device_type, "value", device_type) or "")


def build_scenarios(devices):
    """Critical scenarios resolved by device_type (no hardcoded codes)."""
    by_type: dict[str, list] = {}
    for d in devices:
        by_type.setdefault(_device_type_value(d), []).append(d)
    target_devices = (
        by_type.get(DeviceType.REFRIGERATED_SHOWCASE.value) or devices[:1]
    )
    return [
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


def select_scenarios(devices, condition=None):
    """Scenarios for one cycle, honoring the run sensor condition.

    - ``"critica"`` (or None/unknown): current behavior — LOW, MEDIUM and
      HIGH critical scenarios over the target devices.
    - ``"normal"``: no overrides — plain drift within each device's
      configured ranges (readings stay inside safe bands absent drift).
    """
    if condition == "normal":
        return []
    return build_scenarios(devices)


def _publish_all_devices(devices, device_publisher):
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


def publish_cycle(devices, scenarios, critical_manager, device_publisher, sampling_interval):
    """Publish every scenario once for every device.

    An empty scenario list means plain operation (``normal`` condition):
    a single drift pass with no overrides applied.
    """
    if not scenarios:
        _publish_all_devices(devices, device_publisher)
        time.sleep(sampling_interval)
        return
    for cycle_index, scenario in enumerate(scenarios, start=1):
        critical_manager.deactivate_all()
        critical_manager.activate(scenario)
        print(f"\n  --- Ciclo {cycle_index}: {scenario.name} ---")

        critical_manager.update()

        _publish_all_devices(devices, device_publisher)

        time.sleep(sampling_interval)


def main(cycles: int = 1, condition: str | None = None) -> None:
    """Run the scenario loop.

    ``cycles >= 1`` publishes every scenario once per device and exits.
    ``cycles == 0`` runs continuously until interrupted (run-scoped worker
    mode): devices reload from DB every cycle, so UI-created devices join
    without restarting.
    """
    if cycles < 0:
        raise ValueError("'cycles' must be >= 0 (0 = continuous)")
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
    critical_manager = CriticalScenarioManager()

    # --- Measurements ---
    print("=" * 60)
    print("Simulación de cuarto frío para almacenamiento de carne.")
    print("Se alternan escenarios de baja, media y alta criticidad.")
    print("La pérdida de energía o el aumento de temperatura afectan directamente el riesgo de la carne.")
    print("=" * 60)

    try:
        run_cycle = 0
        while True:
            run_cycle += 1
            if cycles > 0 and run_cycle > cycles:
                break
            if cycles == 0 or cycles > 1:
                print(f"\n=== Vuelta {run_cycle}" + (f"/{cycles} ===" if cycles > 0 else " (continuo) ==="))

            devices = load_devices()
            if not devices:
                if cycles > 0:
                    logging.getLogger(__name__).error("No devices available or DB unreachable — aborting simulator (DB is source of truth, no hardcoded fallback)")
                    sys.exit(1)
                logging.getLogger(__name__).warning("No devices with sensors yet — waiting for devices")
                time.sleep(config.sampling_interval)
                continue

            publish_cycle(devices, select_scenarios(devices, condition), critical_manager, device_publisher, config.sampling_interval)

        print("=" * 60)
    finally:
        mqtt_client.stop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ColdChain-IoT device simulator")
    parser.add_argument("--cycles", type=int, default=1, help="scenario loop repetitions (0 = continuous until interrupted)")
    parser.add_argument("--condition", choices=["critica", "normal"], default=None,
                        help="sensor condition for the run (default: critical scenarios, current behavior)")
    args = parser.parse_args()
    main(cycles=args.cycles, condition=args.condition)
