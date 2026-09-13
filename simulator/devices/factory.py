from simulator.devices.cold_room import ColdRoom
from simulator.devices.device_type import DeviceStatus, DeviceType
from simulator.devices.refrigerated_showcase import RefrigeratedShowcase


def orm_to_device(orm) -> object:
    """Convert a DeviceORM row into a simulator Device instance."""
    status = DeviceStatus(orm.status)
    base_kwargs = dict(
        id=str(orm.id),
        code=orm.code,
        name=orm.name,
        location=orm.location,
        status=status,
        registration_date=orm.registration_date,
    )
    if orm.device_type == DeviceType.COLD_ROOM.value:
        return ColdRoom(**base_kwargs)
    if orm.device_type == DeviceType.REFRIGERATED_SHOWCASE.value:
        return RefrigeratedShowcase(**base_kwargs)
    raise ValueError(f"Unknown device_type: {orm.device_type}")
