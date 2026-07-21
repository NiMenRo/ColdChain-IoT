from enum import Enum


class SensorStatus(Enum):
    """Operational status of a sensor."""

    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"
