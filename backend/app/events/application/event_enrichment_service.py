"""Service for enriching events with contextual information.

The event enrichment service receives Alert objects and supplements them with
contextual data like device information, traffic classification, and QoS metrics.
The enriched event maintains full traceability from sensor reading through alert
generation, enabling comprehensive event recording and auditing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.classification.domain import TrafficClassification
from app.events.domain import Alert
from app.qos.application.qos_metrics_service import MessageDeliveryRecord


@dataclass(frozen=True)
class DeviceInfo:
    """Contextual information about the device that generated the event."""

    device_id: UUID
    device_code: str
    device_type: str
    location: Optional[str] = None


@dataclass(frozen=True)
class QoSContext:
    """QoS metrics associated with the event."""

    latency: float
    jitter: float
    throughput: float
    pdr: float
    packet_loss: float


@dataclass(frozen=True)
class EnrichedEvent:
    """Complete event record with full contextual information for persistence.

    An enriched event combines:
    - The alert (type, message, criticality)
    - Device context (device_id, device_code, device_type)
    - Traffic classification (priority, queue, classification_time)
    - QoS metrics (latency, jitter, throughput, pdr, packet_loss)
    - Timestamps (alert time, classification time, enrichment time)
    - Full traceability (all IDs needed to trace back through the pipeline)
    """

    # Alert information
    alert_id: UUID
    alert_type: str
    alert_message: str
    alert_criticality: float
    alert_acknowledged: bool
    alert_created_at: datetime

    # Device context
    device_id: UUID
    device_code: str
    device_type: str
    device_location: Optional[str]

    # Traffic classification
    classification_id: UUID
    reading_id: UUID
    traffic_priority: str
    traffic_queue: str
    classification_time: datetime

    # QoS metrics
    qos_latency: float
    qos_jitter: float
    qos_throughput: float
    qos_pdr: float
    qos_packet_loss: float

    # Timestamps
    sensor_timestamp: datetime
    enrichment_timestamp: datetime

    # User context
    user_id: UUID


class EventEnrichmentService:
    """Enriches Alert objects with contextual information for storage.

    The service orchestrates the gathering of all relevant data from different
    stages of the pipeline (device info, classification, QoS metrics) and creates
    a single, complete `EnrichedEvent` record.

    The enriched event preserves all traceability information needed to:
    - Trace back from alert to original sensor reading
    - Understand the classification and QoS decisions that led to the alert
    - Correlate with other events from the same device
    - Generate reports and analytics
    - Audit the entire event processing flow
    """

    def enrich(
        self,
        alert: Alert,
        device_info: DeviceInfo,
        classification: TrafficClassification,
        qos_context: QoSContext,
    ) -> EnrichedEvent:
        """Enrich an alert with contextual information.

        Parameters
        ----------
        alert : Alert
            The alert object to enrich.
        device_info : DeviceInfo
            Information about the device that generated the alert.
        classification : TrafficClassification
            Traffic classification associated with the alert.
        qos_context : QoSContext
            QoS metrics associated with the alert.

        Returns
        -------
        EnrichedEvent
            Enriched event with full contextual information, ready for storage.

        Raises
        ------
        TypeError
            If any parameter is of incorrect type.
        ValueError
            If alert and device_info device IDs don't match.
        """
        self._validate_inputs(alert, device_info, classification, qos_context)
        self._validate_consistency(alert, device_info)

        return EnrichedEvent(
            # Alert information
            alert_id=alert.id,
            alert_type=alert.type,
            alert_message=alert.message,
            alert_criticality=alert.criticality,
            alert_acknowledged=alert.acknowledged,
            alert_created_at=alert.created_at,
            # Device context
            device_id=device_info.device_id,
            device_code=device_info.device_code,
            device_type=device_info.device_type,
            device_location=device_info.location,
            # Traffic classification
            classification_id=classification.id,
            reading_id=classification.reading_id,
            traffic_priority=classification.priority,
            traffic_queue=classification.queue,
            classification_time=classification.classification_time,
            # QoS metrics
            qos_latency=qos_context.latency,
            qos_jitter=qos_context.jitter,
            qos_throughput=qos_context.throughput,
            qos_pdr=qos_context.pdr,
            qos_packet_loss=qos_context.packet_loss,
            # Timestamps
            sensor_timestamp=classification.timestamp,
            enrichment_timestamp=datetime.now(timezone.utc),
            # User context
            user_id=alert.user_id,
        )

    def enrich_from_delivery_record(
        self,
        alert: Alert,
        device_info: DeviceInfo,
        classification: TrafficClassification,
        delivery_record: MessageDeliveryRecord,
    ) -> EnrichedEvent:
        """Enrich an alert using a MessageDeliveryRecord for QoS data.

        This is a convenience method that extracts QoS context from a
        MessageDeliveryRecord before calling the main enrich method.

        Parameters
        ----------
        alert : Alert
            The alert object to enrich.
        device_info : DeviceInfo
            Information about the device that generated the alert.
        classification : TrafficClassification
            Traffic classification associated with the alert.
        delivery_record : MessageDeliveryRecord
            QoS delivery record containing latency, throughput, PDR, etc.

        Returns
        -------
        EnrichedEvent
            Enriched event with full contextual information.
        """
        if not isinstance(delivery_record, MessageDeliveryRecord):
            raise TypeError("'delivery_record' must be a MessageDeliveryRecord instance")

        qos_context = QoSContext(
            latency=delivery_record.sent_at
            if isinstance(delivery_record.sent_at, (int, float))
            else 0.0,
            jitter=0.0,  # Jitter would be calculated from multiple records
            throughput=delivery_record.size_bytes / 1000.0,  # Simple estimate
            pdr=100.0 if delivery_record.delivered else 0.0,
            packet_loss=0.0 if delivery_record.delivered else 100.0,
        )

        return self.enrich(alert, device_info, classification, qos_context)

    @staticmethod
    def _validate_inputs(
        alert: object,
        device_info: object,
        classification: object,
        qos_context: object,
    ) -> None:
        """Validate all input parameters."""
        if not isinstance(alert, Alert):
            raise TypeError("'alert' must be an Alert instance")
        if not isinstance(device_info, DeviceInfo):
            raise TypeError("'device_info' must be a DeviceInfo instance")
        if not isinstance(classification, TrafficClassification):
            raise TypeError("'classification' must be a TrafficClassification instance")
        if not isinstance(qos_context, QoSContext):
            raise TypeError("'qos_context' must be a QoSContext instance")

    @staticmethod
    def _validate_consistency(alert: Alert, device_info: DeviceInfo) -> None:
        """Validate that alert and device_info reference the same device."""
        if alert.device_id != device_info.device_id:
            raise ValueError(
                f"Alert device_id ({alert.device_id}) does not match "
                f"device_info device_id ({device_info.device_id})"
            )
