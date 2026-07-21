import time

from devices import ColdRoom, RefrigeratedShowcase, DeviceStatus
from sensors import TemperatureSensor, HumiditySensor


def main() -> None:
    """Creates sample devices with temperature and humidity sensors."""

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

    cava_principal.add_sensor(temp_sensor_1)
    cava_principal.add_sensor(hum_sensor_1)
    cava_secundaria.add_sensor(temp_sensor_2)
    cava_secundaria.add_sensor(hum_sensor_2)
    vitrina.add_sensor(temp_sensor_3)
    vitrina.add_sensor(hum_sensor_3)

    devices = [cava_principal, cava_secundaria, vitrina]

    # --- Measurements ---
    print("=" * 60)

    for cycle in range(1, 4):
        print(f"\n  --- Ciclo {cycle} ---")

        for device in devices:
            print()
            print(f"  {device.code}")
            print(f"  {'-' * 30}")

            for sensor in device.get_sensors():
                measurement = sensor.read()

                if hasattr(sensor, "min_temperature"):
                    label = "Temperatura"
                    unit_label = measurement.unit
                    state = sensor.current_temperature
                elif hasattr(sensor, "min_humidity"):
                    label = "Humedad"
                    unit_label = measurement.unit
                    state = sensor.current_humidity
                else:
                    continue

                print(f"  {label}:")
                print(f"  {measurement.value} {unit_label}")
                print(f"  Hora:")
                print(f"  {measurement.timestamp.strftime('%H:%M:%S')}")
                print(f"  (estado interno: {state} {unit_label})")

            print(f"  {'-' * 30}")

        time.sleep(1)

    print("=" * 60)


if __name__ == "__main__":
    main()
