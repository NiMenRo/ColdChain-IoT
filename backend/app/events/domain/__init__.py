from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Alert:
    """A domain event raised when a monitored device requires operator attention.

    An alert is always associated with exactly one device and one user, and
    records the event ``type``, a human-readable ``message`` and a numeric
    ``criticality`` score (the same C = I + U + R value used by the
    classification subsystem) so that downstream priority logic can reuse it.
    """

    id: UUID
    device_id: UUID
    user_id: UUID
    type: str
    message: str
    criticality: float
    acknowledged: bool
    created_at: datetime

    def __post_init__(self) -> None:
        self._validate_id()
        self._validate_device_id()
        self._validate_user_id()
        self._validate_type()
        self._validate_message()
        self._validate_criticality()
        self._validate_acknowledged()
        self._validate_created_at()

    def _validate_id(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("'id' must be a UUID instance")

    def _validate_device_id(self) -> None:
        if not isinstance(self.device_id, UUID):
            raise TypeError("'device_id' must be a UUID instance")

    def _validate_user_id(self) -> None:
        if not isinstance(self.user_id, UUID):
            raise TypeError("'user_id' must be a UUID instance")

    def _validate_type(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("'type' must be a str instance")
        if not self.type.strip():
            raise ValueError("'type' must be a non-empty string")

    def _validate_message(self) -> None:
        if not isinstance(self.message, str):
            raise TypeError("'message' must be a str instance")
        if not self.message.strip():
            raise ValueError("'message' must be a non-empty string")

    def _validate_criticality(self) -> None:
        if isinstance(self.criticality, bool) or not isinstance(self.criticality, (int, float)):
            raise TypeError("'criticality' must be a numeric value")

    def _validate_acknowledged(self) -> None:
        if not isinstance(self.acknowledged, bool):
            raise TypeError("'acknowledged' must be a bool instance")

    def _validate_created_at(self) -> None:
        if not isinstance(self.created_at, datetime):
            raise TypeError("'created_at' must be a datetime instance")
