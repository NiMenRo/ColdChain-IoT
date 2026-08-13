from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class TrafficClassification:
    """Classification result associated with an incoming IoT telemetry reading.

    This entity stores the output of the classification process applied to a
    ``SensorReading``.  At this stage it is a plain data container — the
    business rules that populate ``criticality``, ``priority`` and ``queue``
    will be implemented in a future task.
    """

    id: UUID
    reading_id: UUID
    criticality: float
    priority: str
    queue: str
    classification_time: datetime
    timestamp: datetime

    def __post_init__(self) -> None:
        self._validate_id()
        self._validate_reading_id()
        self._validate_criticality()
        self._validate_priority()
        self._validate_queue()
        self._validate_classification_time()
        self._validate_timestamp()

    # -- validators ----------------------------------------------------------

    def _validate_id(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("'id' must be a UUID instance")

    def _validate_reading_id(self) -> None:
        if not isinstance(self.reading_id, UUID):
            raise TypeError("'reading_id' must be a UUID instance")

    def _validate_criticality(self) -> None:
        if isinstance(self.criticality, bool) or not isinstance(self.criticality, (int, float)):
            raise TypeError("'criticality' must be numeric")

    def _validate_priority(self) -> None:
        if not isinstance(self.priority, str) or not self.priority.strip():
            raise ValueError("'priority' must be a non-empty string")

    def _validate_queue(self) -> None:
        if not isinstance(self.queue, str) or not self.queue.strip():
            raise ValueError("'queue' must be a non-empty string")

    def _validate_classification_time(self) -> None:
        if not isinstance(self.classification_time, datetime):
            raise TypeError("'classification_time' must be a datetime instance")

    def _validate_timestamp(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise TypeError("'timestamp' must be a datetime instance")
