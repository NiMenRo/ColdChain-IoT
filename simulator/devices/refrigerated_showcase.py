from datetime import datetime
from typing import Optional

from .device import Device
from .device_type import DeviceType, DeviceStatus


class RefrigeratedShowcase(Device):
    """A refrigerated display cabinet (vitrina) for product exhibition."""

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
            device_type=DeviceType.REFRIGERATED_SHOWCASE,
            status=status,
            registration_date=registration_date or datetime.now(),
        )
