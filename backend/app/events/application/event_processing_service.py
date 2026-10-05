"""Main orchestrator for event processing pipeline.

Coordinates receiving SensorReading + TrafficClassification + QoS metrics,
evaluating them against configured rules, and generating Alert objects
when conditions are met.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.events.application.event_detector import EventDetector
from app.events.application.rule_engine import RuleEngine
from app.events.domain import Alert, DetectedEvent, ThresholdConfig
from app.qos.application.qos_metrics_service import MessageDeliveryRecord

logger = logging.getLogger(__name__)


def criticality_for_breaches(evaluations: list) -> float:
    """Rule-derived severity for WITHOUT_QOS alerts (TSK-059.7).

    Counts breached evaluations: 3.0 base + 2.0 per breach, capped at 9.0.
    This is NOT QoS criticality (C = I + U + R); it carries no priority,
    queue or scheduler meaning and must never feed TrafficClassification.
    """
    breached = sum(1 for e in evaluations if getattr(e, "breached", False))
    return min(9.0, 3.0 + 2.0 * breached)


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
        classification: Optional[TrafficClassification] = None,
        metrics: Optional[MessageDeliveryRecord] = None,
    ) -> dict:
        """Process a batch of readings with optional classification and metrics.

        Parameters
        ----------
        readings : list[NormalizedReading]
            Normalized sensor readings to process.
        classification : TrafficClassification, optional
            Traffic classification result (WITH_QOS). None in WITHOUT_QOS,
            where alert criticality is derived from rule evaluations instead.
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
        if classification is not None and not isinstance(classification, TrafficClassification):
            raise TypeError("'classification' must be a TrafficClassification instance or None")

        # Evaluate readings against configured thresholds
        evaluations = self._rule_engine.evaluate(readings)

        # Detect events from breached evaluations
        events = self._event_detector.detect(evaluations)

        # Generate alerts for detected events
        alerts = self._generate_alerts(events, readings, classification, metrics, evaluations)

        return {
            "evaluations": evaluations,
            "events": events,
            "alerts": alerts,
            "event_count": len(events),
            "alert_count": len(alerts),
            "classification_id": str(classification.id) if classification is not None else None,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _generate_alerts(
        self,
        events: list[DetectedEvent],
        readings: list[NormalizedReading],
        classification: Optional[TrafficClassification],
        metrics: Optional[MessageDeliveryRecord] = None,
        evaluations: list | None = None,
    ) -> list[Alert]:
        """Convert detected events into Alert objects.

        An Alert is generated for each DetectedEvent, enriched with:
        - device_id (from device_mapping, must be a real Device.id)
        - user_id (from config or placeholder)
        - criticality (from classification in WITH_QOS; from rule
          evaluations via criticality_for_breaches in WITHOUT_QOS)
        - type (from event)
        - message (from event)
        - created_at (now)

        Unknown device_code values are skipped with a warning and do not
        generate a fake UUID.
        """
        alerts: list[Alert] = []

        for event in events:
            device_id = self._resolve_device_id(event.device_code)
            if device_id is None:
                continue
            if classification is not None:
                criticality = classification.criticality
            else:
                criticality = criticality_for_breaches(evaluations or [])
            alert = Alert(
                id=uuid4(),
                device_id=device_id,
                user_id=self._user_id,
                type=event.event_type,
                message=event.message,
                criticality=criticality,
                acknowledged=False,
                created_at=datetime.now(timezone.utc),
            )
            alerts.append(alert)

        return alerts

    def _resolve_device_id(self, device_code: str) -> UUID | None:
        """Resolve device_code to the real Device.id from the mapping.

        Returns None for unknown device_code values and logs a warning.
        No fake UUID is generated.
        """
        if device_code in self._device_mapping:
            return self._device_mapping[device_code]
        logger.warning("Unknown device_code %s — skipping alert (no fake UUID)", device_code)
        return None

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
