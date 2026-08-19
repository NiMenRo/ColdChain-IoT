from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID, uuid4

from app.classification import PriorityAssigner, PriorityLevel
from app.qos.domain import QoSMetric


@dataclass(frozen=True)
class MessageDeliveryRecord:
    """Simple record describing a sent/received payload and its QoS metadata."""

    message_id: str | UUID
    sent_at: datetime
    received_at: datetime
    size_bytes: float = 0.0
    delivered: bool = True
    criticality: float | None = None
    priority: str | None = None


class QoSMetricsService:
    """Calculates QoS metrics from sent/received traffic records.

    The service intentionally does not alter queueing logic. It focuses only on
    measuring traffic behavior so the planning strategies in the QoS module can be
    compared with and without prioritization.
    """

    def calculate_latency(self, sent_at: datetime, received_at: datetime) -> float:
        sent_at = self._require_datetime(sent_at, "sent_at")
        received_at = self._require_datetime(received_at, "received_at")
        if received_at < sent_at:
            raise ValueError("'received_at' cannot be earlier than 'sent_at'")
        return (received_at - sent_at).total_seconds()

    compute_latency = calculate_latency

    def calculate_jitter(self, latencies: Sequence[float] | Iterable[float]) -> float:
        values = [float(value) for value in latencies]
        if not values:
            return 0.0
        if len(values) == 1:
            return 0.0
        deltas = [abs(curr - prev) for prev, curr in zip(values, values[1:])]
        return sum(deltas) / len(deltas) if deltas else 0.0

    compute_jitter = calculate_jitter

    def calculate_throughput(
        self,
        records: Sequence[object] | Iterable[object],
        interval_seconds: float | None = None,
    ) -> float:
        normalized = [self._normalize_record(record) for record in records]
        delivered = [record for record in normalized if record.delivered]
        if not delivered:
            return 0.0

        data_volume = sum(float(record.size_bytes) for record in delivered)
        if interval_seconds is None:
            times = [record.sent_at for record in delivered] + [record.received_at for record in delivered]
            if not times:
                return 0.0
            start = min(times)
            end = max(times)
            interval_seconds = max((end - start).total_seconds(), 1e-9)
        interval_seconds = float(interval_seconds)
        if interval_seconds <= 0:
            raise ValueError("'interval_seconds' must be greater than zero")
        return data_volume / interval_seconds

    compute_throughput = calculate_throughput

    def calculate_pdr(self, sent_count: int, received_count: int) -> float:
        sent_total = self._require_non_negative_int(sent_count, "sent_count")
        received_total = self._require_non_negative_int(received_count, "received_count")
        if sent_total == 0:
            return 0.0
        return (received_total / sent_total) * 100.0

    compute_pdr = calculate_pdr

    def calculate_packet_loss(self, sent_count: int, received_count: int) -> float:
        sent_total = self._require_non_negative_int(sent_count, "sent_count")
        received_total = self._require_non_negative_int(received_count, "received_count")
        if sent_total == 0:
            return 0.0
        lost = sent_total - received_total
        return (lost / sent_total) * 100.0

    compute_packet_loss = calculate_packet_loss

    def summarize(
        self,
        records: Sequence[object] | Iterable[object],
        interval_seconds: float | None = None,
        include_priority_summary: bool = True,
    ) -> dict[str, Any]:
        normalized = [self._normalize_record(record) for record in records]
        if not normalized:
            return {
                "latency": 0.0,
                "jitter": 0.0,
                "throughput": 0.0,
                "pdr": 0.0,
                "packet_loss": 0.0,
                "sent_count": 0,
                "received_count": 0,
                "priority_summary": {},
            }

        latencies = [
            self.calculate_latency(record.sent_at, record.received_at)
            for record in normalized
            if record.delivered and record.received_at is not None
        ]

        sent_count = len(normalized)
        received_count = sum(1 for record in normalized if record.delivered)

        summary = {
            "latency": sum(latencies) / len(latencies) if latencies else 0.0,
            "jitter": self.calculate_jitter(latencies),
            "throughput": self.calculate_throughput(normalized, interval_seconds),
            "pdr": self.calculate_pdr(sent_count, received_count),
            "packet_loss": self.calculate_packet_loss(sent_count, received_count),
            "sent_count": sent_count,
            "received_count": received_count,
            "priority_summary": {},
        }
        if include_priority_summary:
            summary["priority_summary"] = self._summarize_by_priority(normalized, interval_seconds)
        return summary

    calculate_metrics = summarize

    def build_metric(
        self,
        record: object,
        *,
        classification_id: UUID | None = None,
        timestamp: datetime | None = None,
        sent_count: int = 1,
        received_count: int = 1,
    ) -> QoSMetric:
        normalized = self._normalize_record(record)
        if classification_id is None:
            classification_id = self._extract_classification_id(normalized)
        if classification_id is None:
            classification_id = uuid4()

        metric_time = timestamp or normalized.received_at
        return QoSMetric(
            id=uuid4(),
            classification_id=classification_id,
            latency=self.calculate_latency(normalized.sent_at, normalized.received_at),
            packet_loss=self.calculate_packet_loss(sent_count, received_count),
            throughput=self._throughput_for_record(normalized),
            pdr=self.calculate_pdr(sent_count, received_count),
            jitter=self.calculate_jitter([
                self.calculate_latency(normalized.sent_at, normalized.received_at)
            ]),
            timestamp=metric_time,
        )

    def summarize_by_priority(
        self,
        records: Sequence[object] | Iterable[object],
        interval_seconds: float | None = None,
    ) -> dict[str, dict[str, float | int]]:
        normalized = [self._normalize_record(record) for record in records]
        buckets: dict[str, list[MessageDeliveryRecord]] = defaultdict(list)
        for record in normalized:
            priority = self._priority_for_record(record)
            buckets[priority].append(record)
        return {
            priority: self.summarize(bucket, interval_seconds)
            for priority, bucket in buckets.items()
        }

    def _summarize_by_priority(
        self,
        records: Sequence[MessageDeliveryRecord],
        interval_seconds: float | None = None,
    ) -> dict[str, dict[str, float | int]]:
        buckets: dict[str, list[MessageDeliveryRecord]] = defaultdict(list)
        for record in records:
            priority = self._priority_for_record(record)
            buckets[priority].append(record)

        metrics_by_priority: dict[str, dict[str, float | int]] = {}
        for priority, bucket in buckets.items():
            bucket_summary = self.summarize(bucket, interval_seconds, include_priority_summary=False)
            metrics_by_priority[priority] = {
                "latency": bucket_summary["latency"],
                "jitter": bucket_summary["jitter"],
                "throughput": bucket_summary["throughput"],
                "pdr": bucket_summary["pdr"],
                "packet_loss": bucket_summary["packet_loss"],
                "sent_count": bucket_summary["sent_count"],
                "received_count": bucket_summary["received_count"],
            }
        return metrics_by_priority

    @staticmethod
    def _normalize_record(record: object) -> MessageDeliveryRecord:
        if isinstance(record, MessageDeliveryRecord):
            return record
        if isinstance(record, Mapping):
            return MessageDeliveryRecord(
                message_id=record.get("message_id"),
                sent_at=QoSMetricsService._require_datetime(record.get("sent_at"), "sent_at"),
                received_at=QoSMetricsService._require_datetime(record.get("received_at"), "received_at"),
                size_bytes=float(record.get("size_bytes", 0.0) or 0.0),
                delivered=bool(record.get("delivered", True)),
                criticality=record.get("criticality"),
                priority=record.get("priority"),
            )
        if hasattr(record, "sent_at") and hasattr(record, "received_at"):
            priority = getattr(record, "priority", None)
            criticality = getattr(record, "criticality", None)
            size_bytes = getattr(record, "size_bytes", getattr(record, "size", 0.0))
            delivered = getattr(record, "delivered", True)
            return MessageDeliveryRecord(
                message_id=getattr(record, "message_id", getattr(record, "id", "unknown")),
                sent_at=QoSMetricsService._require_datetime(getattr(record, "sent_at"), "sent_at"),
                received_at=QoSMetricsService._require_datetime(getattr(record, "received_at"), "received_at"),
                size_bytes=float(size_bytes or 0.0),
                delivered=bool(delivered),
                criticality=criticality,
                priority=priority,
            )
        raise TypeError("Record must be a MessageDeliveryRecord, dict, or object with sent_at/received_at")

    @staticmethod
    def _require_datetime(value: Any, name: str) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError(f"'{name}' must be a datetime instance")
        return value

    @staticmethod
    def _require_non_negative_int(value: Any, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"'{name}' must be an integer")
        if value < 0:
            raise ValueError(f"'{name}' must be greater than or equal to zero")
        return value

    @staticmethod
    def _priority_for_record(record: MessageDeliveryRecord) -> str:
        if record.priority:
            return str(record.priority).lower()
        if record.criticality is not None:
            try:
                priority = PriorityAssigner().assign(float(record.criticality))
            except (TypeError, ValueError):
                return "unknown"
            return priority.value
        return "unknown"

    @staticmethod
    def _extract_classification_id(record: MessageDeliveryRecord) -> UUID | None:
        message_id = record.message_id
        if isinstance(message_id, UUID):
            return message_id
        return None

    @staticmethod
    def _throughput_for_record(record: MessageDeliveryRecord) -> float:
        latency_seconds = max(
            (record.received_at - record.sent_at).total_seconds(),
            1e-9,
        )
        return float(record.size_bytes) / latency_seconds


QoSMetricService = QoSMetricsService
