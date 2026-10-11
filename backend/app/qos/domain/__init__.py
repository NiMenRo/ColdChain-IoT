from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class QoSMetric:
    """Quality of Service metric associated with a traffic classification.

    This entity stores the QoS metrics produced during the processing of IoT
    traffic.  At this stage it is a plain data container — the planning and
    queueing logic that populates ``latency``, ``packet_loss``, ``throughput``,
    ``pdr`` and ``jitter`` will be implemented in a future task.  The
    ``classification_id`` references the ``TrafficClassification`` this metric
    belongs to, as defined in the UML model.
    """

    id: UUID
    classification_id: UUID
    latency: float
    packet_loss: float
    throughput: float
    pdr: float
    jitter: float
    timestamp: datetime

    def __post_init__(self) -> None:
        self._validate_id()
        self._validate_classification_id()
        self._validate_latency()
        self._validate_packet_loss()
        self._validate_throughput()
        self._validate_pdr()
        self._validate_jitter()
        self._validate_timestamp()

    # -- validators ----------------------------------------------------------

    def _validate_id(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("'id' must be a UUID instance")

    def _validate_classification_id(self) -> None:
        if not isinstance(self.classification_id, UUID):
            raise TypeError("'classification_id' must be a UUID instance")

    def _validate_latency(self) -> None:
        if isinstance(self.latency, bool) or not isinstance(self.latency, (int, float)):
            raise TypeError("'latency' must be numeric")
        if self.latency < 0:
            raise ValueError("'latency' must be >= 0 (seconds)")

    def _validate_packet_loss(self) -> None:
        if isinstance(self.packet_loss, bool) or not isinstance(self.packet_loss, (int, float)):
            raise TypeError("'packet_loss' must be numeric")
        if not 0 <= self.packet_loss <= 100:
            raise ValueError("'packet_loss' must be between 0 and 100 (percent)")

    def _validate_throughput(self) -> None:
        if isinstance(self.throughput, bool) or not isinstance(self.throughput, (int, float)):
            raise TypeError("'throughput' must be numeric")
        if self.throughput < 0:
            raise ValueError("'throughput' must be >= 0 (bytes/second)")

    def _validate_pdr(self) -> None:
        if isinstance(self.pdr, bool) or not isinstance(self.pdr, (int, float)):
            raise TypeError("'pdr' must be numeric")
        if not 0 <= self.pdr <= 100:
            raise ValueError("'pdr' must be between 0 and 100 (percent)")

    def _validate_jitter(self) -> None:
        if isinstance(self.jitter, bool) or not isinstance(self.jitter, (int, float)):
            raise TypeError("'jitter' must be numeric")
        if self.jitter < 0:
            raise ValueError("'jitter' must be >= 0 (seconds)")

    def _validate_timestamp(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise TypeError("'timestamp' must be a datetime instance")
