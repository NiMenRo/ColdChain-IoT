import time

from devices import ColdRoom, RefrigeratedShowcase, DeviceStatus
from sensors import TemperatureSensor


def main() -> None:
    """Creates sample devices with temperature sensors and takes measurements."""

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

    cava_principal.add_sensor(temp_sensor_1)
    cava_secundaria.add_sensor(temp_sensor_2)
    vitrina.add_sensor(temp_sensor_3)

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
                print(f"  Temperatura:")
                print(f"  {measurement.value} {measurement.unit}")
                print(f"  Hora:")
                print(f"  {measurement.timestamp.strftime('%H:%M:%S')}")
                if hasattr(sensor, "current_temperature"):
                    print(f"  (estado interno: {sensor.current_temperature} {measurement.unit})")

            print(f"  {'-' * 30}")

        time.sleep(1)

    print("=" * 60)


if __name__ == "__main__":
    main()
