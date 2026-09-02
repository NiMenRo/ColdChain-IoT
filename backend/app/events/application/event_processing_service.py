"""Main orchestrator for event processing pipeline.

Coordinates receiving SensorReading + TrafficClassification + QoS metrics,
evaluating them against configured rules, and generating Alert objects
when conditions are met.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.events.application.event_detector import EventDetector
from app.events.application.rule_engine import RuleEngine
from app.events.domain import Alert, DetectedEvent, ThresholdConfig
from app.qos.application.qos_metrics_service import MessageDeliveryRecord


class EventProcessingService:
    """Orchestrates event detection from readings, classifications, and QoS metrics.

    Flow:
        NormalizedReading + TrafficClassification + QoS Metrics
            ↓
        RuleEngine.evaluate()  →  RuleEvaluation list
            ↓
        EventDetector.detect()  →  DetectedEvent list
            ↓
        Alert generation (if needed)

    The service intentionally does not re-classify messages or re-plan traffic.
    It only receives outputs from previous stages and processes them.

    Parameters
    ----------
    threshold_config : ThresholdConfig
        Thresholds for temperature, humidity, and allowed energy states.
        This configuration is injected and never hard-coded.
    device_mapping : dict[str, UUID], optional
        Mapping from device_code to device_id. If not provided, device_id
        is generated for each reading.
    user_id : UUID, optional
        Default user_id to attach to generated alerts. If not provided,
        alerts are generated with a placeholder user_id.
    """

    def __init__(
        self,
        threshold_config: ThresholdConfig,
        device_mapping: Optional[dict[str, UUID]] = None,
        user_id: Optional[UUID] = None,
    ) -> None:
        if not isinstance(threshold_config, ThresholdConfig):
            raise TypeError("'threshold_config' must be a ThresholdConfig instance")

        self._threshold_config = threshold_config
        self._rule_engine = RuleEngine(threshold_config)
        self._event_detector = EventDetector()
        self._device_mapping = device_mapping or {}
        self._user_id = user_id or UUID("00000000-0000-0000-0000-000000000000")

    def process(
        self,
        readings: list[NormalizedReading],
        classification: TrafficClassification,
        metrics: Optional[MessageDeliveryRecord] = None,
    ) -> dict:
        """Process a batch of readings with classification and optional metrics.

        Parameters
        ----------
        readings : list[NormalizedReading]
            Normalized sensor readings to process.
        classification : TrafficClassification
            Traffic classification result from the classification module.
        metrics : MessageDeliveryRecord, optional
            QoS metrics associated with this batch (not used in alert generation,
            but kept for future correlation and tracing).

        Returns
        -------
        dict
            Result containing:
            - 'evaluations': list of RuleEvaluation objects
            - 'events': list of DetectedEvent objects
            - 'alerts': list of Alert objects (only if rules were breached)
            - 'event_count': total number of events detected
            - 'alert_count': total number of alerts generated
        """
        if not isinstance(readings, list):
            raise TypeError("'readings' must be a list of NormalizedReading")
        if not isinstance(classification, TrafficClassification):
            raise TypeError("'classification' must be a TrafficClassification instance")

        # Evaluate readings against configured thresholds
        evaluations = self._rule_engine.evaluate(readings)

        # Detect events from breached evaluations
        events = self._event_detector.detect(evaluations)

        # Generate alerts for detected events
        alerts = self._generate_alerts(events, readings, classification, metrics)

        return {
            "evaluations": evaluations,
            "events": events,
            "alerts": alerts,
            "event_count": len(events),
            "alert_count": len(alerts),
            "classification_id": str(classification.id),
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _generate_alerts(
        self,
        events: list[DetectedEvent],
        readings: list[NormalizedReading],
        classification: TrafficClassification,
        metrics: Optional[MessageDeliveryRecord] = None,
    ) -> list[Alert]:
        """Convert detected events into Alert objects.

        An Alert is generated for each DetectedEvent, enriched with:
        - device_id (from device_mapping or generated)
        - user_id (from config or placeholder)
        - criticality (from classification)
        - type (from event)
        - message (from event)
        - created_at (now)
        """
        alerts: list[Alert] = []

        for event in events:
            device_id = self._resolve_device_id(event.device_code)
            alert = Alert(
                id=uuid4(),
                device_id=device_id,
                user_id=self._user_id,
                type=event.event_type,
                message=event.message,
                criticality=classification.criticality,
                acknowledged=False,
                created_at=datetime.now(timezone.utc),
            )
            alerts.append(alert)

        return alerts

    def _resolve_device_id(self, device_code: str) -> UUID:
        """Resolve device_code to device_id using configured mapping.

        If device_code is not in mapping, a new UUID is generated and cached.
        """
        if device_code not in self._device_mapping:
            self._device_mapping[device_code] = uuid4()
        return self._device_mapping[device_code]

    def set_device_mapping(self, mapping: dict[str, UUID]) -> None:
        """Update or replace the device_code → device_id mapping."""
        if not isinstance(mapping, dict):
            raise TypeError("'mapping' must be a dict")
        self._device_mapping.update(mapping)

    def set_user_id(self, user_id: UUID) -> None:
        """Update the default user_id for generated alerts."""
        if not isinstance(user_id, UUID):
            raise TypeError("'user_id' must be a UUID instance")
        self._user_id = user_id
