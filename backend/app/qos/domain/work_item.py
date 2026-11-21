"""Immutable admission data for one sensor reading; no scheduling or I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from uuid import UUID, uuid4

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification


def _aware_utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"'{name}' must be a datetime")
    if value.utcoffset() is None:
        raise ValueError(f"'{name}' must be timezone-aware")
    return value.astimezone(timezone.utc)


def _finite_number(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"'{name}' must be numeric")
    if not isfinite(value):
        raise ValueError(f"'{name}' must be finite")


@dataclass(frozen=True, kw_only=True)
class ClassificationSnapshot:
    """Detached classification whose reading_id is the stable work UUID."""

    id: UUID
    reading_id: UUID
    criticality: float
    priority: str
    queue: str
    classification_time: datetime
    timestamp: datetime

    def __post_init__(self) -> None:
        # Reuse domain validation, including priority/queue normalization,
        # without keeping a mutable TrafficClassification in the work item.
        classification = self.to_classification()
        expected_queue = {"low": "FIFO", "medium": "Round Robin", "high": "WFQ"}
        if classification.queue != expected_queue[classification.priority]:
            raise ValueError("'queue' must match the classification priority")
        object.__setattr__(self, "priority", classification.priority)
        object.__setattr__(self, "queue", classification.queue)
        object.__setattr__(
            self, "classification_time",
            _aware_utc(self.classification_time, "classification_time"),
        )

    def to_classification(self) -> TrafficClassification:
        """Return a fresh adapter for existing services, never a shared object."""
        return TrafficClassification(
            id=self.id, reading_id=self.reading_id, criticality=self.criticality,
            priority=self.priority, queue=self.queue,
            classification_time=self.classification_time, timestamp=self.timestamp,
        )


@dataclass(frozen=True, kw_only=True)
class WorkItem:
    """One admitted reading and the context captured for it.

    Capture clocks explicitly at their real events; missing reception times
    stay None. Selection, persistence and completion belong to later stages,
    not construction. No active experiment, clock, queue or DB is consulted.
    """

    id: UUID
    source_message_id: UUID
    sequence: int
    device_code: str
    device_type: str
    sensor_name: str
    value: float
    timestamp: str
    raw_value: str | int | float
    classification: ClassificationSnapshot | None
    scenario: str
    run_id: UUID | None
    received_at: datetime | None
    received_monotonic: float | None
    admitted_at: datetime
    admitted_monotonic: float

    def __post_init__(self) -> None:
        for name in ("id", "source_message_id"):
            if not isinstance(getattr(self, name), UUID):
                raise TypeError(f"'{name}' must be a UUID")
        if self.run_id is not None and not isinstance(self.run_id, UUID):
            raise TypeError("'run_id' must be a UUID or None")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise TypeError("'sequence' must be an integer")
        if self.sequence < 0:
            raise ValueError("'sequence' must be non-negative")
        for name in ("device_code", "device_type", "timestamp"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"'{name}' must be a non-empty string")
        datetime.fromisoformat(self.timestamp)
        if self.sensor_name not in ("temperature", "humidity", "energy"):
            raise ValueError("'sensor_name' must be temperature, humidity or energy")
        _finite_number(self.value, "value")
        # Valid normalized telemetry has scalar raw values. Mutable payloads
        # must not leak into a frozen item shared by worker threads.
        if not isinstance(self.raw_value, str):
            _finite_number(self.raw_value, "raw_value")
        if self.scenario not in ("WITH_QOS", "WITHOUT_QOS"):
            raise ValueError("'scenario' must be WITH_QOS or WITHOUT_QOS")
        if self.scenario == "WITH_QOS":
            if not isinstance(self.classification, ClassificationSnapshot):
                raise TypeError("WITH_QOS requires a ClassificationSnapshot")
            if self.classification.reading_id != self.id:
                raise ValueError("'classification.reading_id' must match the work id")
            if self.classification.timestamp != datetime.fromisoformat(self.timestamp):
                raise ValueError("'classification.timestamp' must match the reading timestamp")
        elif self.classification is not None:
            raise ValueError("WITHOUT_QOS must not have a classification")
        object.__setattr__(self, "admitted_at", _aware_utc(self.admitted_at, "admitted_at"))
        if self.received_at is not None:
            object.__setattr__(self, "received_at", _aware_utc(self.received_at, "received_at"))
        _finite_number(self.admitted_monotonic, "admitted_monotonic")
        if self.received_monotonic is not None:
            _finite_number(self.received_monotonic, "received_monotonic")
            if self.received_monotonic > self.admitted_monotonic:
                raise ValueError("reception must not follow admission on the monotonic clock")

    @property
    def flow_id(self) -> tuple[str, str]:
        return self.device_code, self.sensor_name

    @property
    def priority(self) -> str | None:
        return self.classification.priority if self.classification is not None else None

    def to_reading(self) -> NormalizedReading:
        """Return a fresh normalized reading for existing application services."""
        return NormalizedReading(
            device_code=self.device_code, device_type=self.device_type,
            sensor_name=self.sensor_name, value=self.value,
            timestamp=self.timestamp, raw_value=self.raw_value,
        )

    @classmethod
    def from_reading(
        cls,
        reading: NormalizedReading,
        *,
        source_message_id: UUID,
        sequence: int,
        scenario: str,
        run_id: UUID | None,
        admitted_at: datetime,
        admitted_monotonic: float,
        classification: TrafficClassification | None = None,
        received_at: datetime | None = None,
        received_monotonic: float | None = None,
        id: UUID | None = None,
    ) -> WorkItem:
        """Snapshot the inputs without mutating or reclassifying them."""
        if not isinstance(reading, NormalizedReading):
            raise TypeError("'reading' must be a NormalizedReading")
        work_id = uuid4() if id is None else id
        snapshot = None
        if classification is not None:
            if not isinstance(classification, TrafficClassification):
                raise TypeError("'classification' must be a TrafficClassification or None")
            snapshot = ClassificationSnapshot(
                id=classification.id, reading_id=work_id,
                criticality=classification.criticality, priority=classification.priority,
                queue=classification.queue, classification_time=classification.classification_time,
                timestamp=classification.timestamp,
            )
        return cls(
            id=work_id, source_message_id=source_message_id, sequence=sequence,
            device_code=reading.device_code, device_type=reading.device_type,
            sensor_name=reading.sensor_name, value=reading.value,
            timestamp=reading.timestamp, raw_value=reading.raw_value,
            classification=snapshot, scenario=scenario, run_id=run_id,
            received_at=received_at, received_monotonic=received_monotonic,
            admitted_at=admitted_at, admitted_monotonic=admitted_monotonic,
        )
