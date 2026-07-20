from enum import Enum


class DeviceType(Enum):
    COLD_ROOM = "cold_room"
    REFRIGERATED_SHOWCASE = "refrigerated_showcase"


class DeviceStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"
    ERROR = "error"
