from datetime import datetime
from typing import Optional

from .device import Device
from .device_type import DeviceType, DeviceStatus


class ColdRoom(Device):
    """A refrigerated cold room (cava) for storage."""

    def __init__(
        self,
        id: str,
        code: str,
        name: str,
        location: str,
        status: DeviceStatus = DeviceStatus.ACTIVE,
        registration_date: Optional[datetime] = None,
    ) -> None:
        super().__init__(
            id=id,
            code=code,
            name=name,
            location=location,
            device_type=DeviceType.COLD_ROOM,
            status=status,
            registration_date=registration_date or datetime.now(),
        )
