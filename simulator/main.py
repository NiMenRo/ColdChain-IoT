from devices import ColdRoom, RefrigeratedShowcase, DeviceStatus


def main() -> None:
    """Creates sample devices and displays their information."""

    devices = [
        ColdRoom(
            id="DEV-001",
            code="CAVA-001",
            name="Cava Principal",
            location="Sótano - Sector A",
        ),
        ColdRoom(
            id="DEV-002",
            code="CAVA-002",
            name="Cava Secundaria",
            location="Sótano - Sector B",
            status=DeviceStatus.MAINTENANCE,
        ),
        RefrigeratedShowcase(
            id="DEV-003",
            code="VITRINA-001",
            name="Vitrina Mostrador 1",
            location="Salón Principal - Zona Clientes",
        ),
    ]

    print("=" * 60)
    print("  COLDCHAIN-IoT — Dispositivos registrados")
    print("=" * 60)

    for device in devices:
        print()
        print(f"  Código          : {device.code}")
        print(f"  Nombre          : {device.name}")
        print(f"  Tipo            : {device.device_type.value}")
        print(f"  Ubicación       : {device.location}")
        print(f"  Estado          : {device.status.value}")
        print(f"  Fecha registro  : {device.registration_date.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  ID interno      : {device.id}")
        print("-" * 60)

    print()
    print(f"  Total dispositivos: {len(devices)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
