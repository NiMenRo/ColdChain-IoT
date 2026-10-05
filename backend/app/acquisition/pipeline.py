from __future__ import annotations

import threading
import time
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


def _as_aware_utc(value: datetime | None) -> datetime | None:
    """Normalize to aware UTC; None stays None (never fabricated)."""
    if value is None or not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _ms_between(start: datetime | None, end: datetime | None) -> float | None:
    """Real millisecond delta or None when timestamps are unavailable.

    Never raises: unmeasurable stays unrecorded instead of artificial.
    """
    start = _as_aware_utc(start)
    end = _as_aware_utc(end)
    if start is None or end is None:
        return None
    try:
        return (end - start).total_seconds() * 1000.0
    except Exception:
        return None


def _parse_received_at(message: dict) -> datetime | None:
    """TSK-059.7 — real ingestion instant, or None when unavailable.

    Never fabricated: without received_at no ingest-based latency is recorded.
    """
    raw = message.get("received_at")
    if not raw or not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _worker_loop(message_queue, app_state, stop_event: threading.Event) -> None:
    """Background worker that consumes messages, normalizes them and sends to classifier.

    The worker keeps an in-memory list at app_state.classifications where each entry
    contains the generated TrafficClassification and a reference to the originating
    normalized reading. This is intentionally simple to keep the integration light
    and easy to extend later (persisting to DB, forwarding to QoS, etc.).
    
    The pipeline also processes events through the event processing service to generate
    alerts based on threshold breaches, then enriches those alerts with contextual
    information (device, classification, QoS metrics) for complete traceability.
    """
    from app.acquisition.normalizer import TelemetryNormalizer

    from app.classification.application.classification_service import (
        ClassificationService,
    )
    from app.classification.application.criticality_calculator import CriticalityCalculator
    from app.classification.application.priority_assigner import PriorityAssigner
    from app.classification.application.risk_matrix_evaluator import RiskMatrixEvaluator
    from app.events.application.event_enrichment_service import (
        DeviceInfo,
        EventEnrichmentService,
    )
    from app.qos.application.qos_metrics_service import MessageDeliveryRecord

    normalizer = TelemetryNormalizer()
    calculator = CriticalityCalculator()
    assigner = PriorityAssigner()
    service = ClassificationService(calculator=calculator, assigner=assigner)
    risk_evaluator = RiskMatrixEvaluator()
    enrichment_service = EventEnrichmentService()

    # ensure classifications list exists
    if not hasattr(app_state, "classifications"):
        app_state.classifications = []
    if not hasattr(app_state, "events"):
        app_state.events = []
    if not hasattr(app_state, "alerts"):
        app_state.alerts = []
    if not hasattr(app_state, "enriched_events"):
        app_state.enriched_events = []

    while not stop_event.is_set():
        try:
            message = message_queue.pop()
            if message is None:
                time.sleep(0.25)
                continue

            # TSK-059.7 — resolve scenario once per message, right after the
            # transport queue. No service re-resolves it downstream.
            from app.experiments.active import resolve_scenario
            from app.experiments.metrics import record_metrics

            run_id, scenario = resolve_scenario()
            without_qos = scenario == "WITHOUT_QOS"
            received_at = _parse_received_at(message)
            # Backlog = pending transport queue depth after pop (QoS queues excluded).
            # Defensive: test doubles may expose only pop().
            try:
                backlog = float(len(message_queue.get_all()))
            except Exception:
                backlog = 0.0
            if run_id is not None:
                record_metrics(
                    run_id,
                    [
                        ("messages_received", 1.0, received_at),
                        ("backlog", backlog, received_at),
                    ],
                )

            try:
                readings = normalizer.normalize(message)
            except Exception as exc:
                logger.exception("Failed to normalize message: %s", exc)
                if run_id is not None:
                    record_metrics(
                        run_id, [("messages_invalid", 1.0, received_at)]
                    )
                continue

            # Bundle persistence: SensorReading 1:1 TrafficClassification
            # Persisted as one transaction per MQTT message via PersistenceService.
            # Grouping by (device_code, timestamp) is a technical adaptation to map
            # NormalizedReading (per sensor) to SensorReadingORM (temp+hum+energy in one row).
            classifications_for_bundle: list = []
            qos_for_bundle = None
            alerts_for_bundle: list = []

            # Derive I/U/R from each reading using the risk matrix. The
            # evaluator is the source of truth; payload impact/urgency/risk
            # fields are intentionally ignored to keep classifications
            # consistent with the real sensor conditions.
            for reading in readings:
                # TSK-059.7 — WITHOUT_QOS skips risk/classify/plan/scheduler
                # entirely. No LOW/FIFO fallback: classification stays None.
                classification = None
                if not without_qos:
                    try:
                        criteria = risk_evaluator.evaluate(reading)
                        classification = service.classify(
                            reading=reading,
                            impact=criteria.impact,
                            urgency=criteria.urgency,
                            risk=criteria.risk,
                        )
                    except Exception as exc:
                        logger.exception("Classification failed for reading %s: %s", reading, exc)
                        continue

                    # store result with reference to the normalized reading and original message metadata
                    entry = {
                        "classification": classification,
                        "reading": reading,
                        "device_code": reading.device_code,
                        "received_at": message.get("received_at"),
                        "topic": message.get("topic"),
                    }
                    app_state.classifications.append(entry)

                    classifications_for_bundle.append(classification)

                    try:
                        qos_service = getattr(app_state, "qos_service", None)
                        if qos_service is not None:
                            qos_service.plan(classification)
                            qos_records = getattr(app_state, "qos_records", None)
                            if qos_records is not None:
                                record = MessageDeliveryRecord(
                                    message_id=str(classification.id),
                                    sent_at=classification.timestamp,
                                    received_at=classification.classification_time,
                                    size_bytes=128.0,
                                    delivered=True,
                                    criticality=classification.criticality,
                                    priority=classification.priority,
                                )
                                qos_records.append(record)
                                # Build QoSMetric for persistence (reemplaza, no duplica)
                                try:
                                    qos_metrics_service = getattr(app_state, "qos_metrics_service", None)
                                    if qos_metrics_service is not None:
                                        qos_for_bundle = qos_metrics_service.build_metric(record, classification_id=classification.id)
                                except Exception:
                                    logger.exception("Failed to build QoSMetric for %s", classification.id)
                            logger.info(
                                "Queued classified reading %s into %s queue for QoS processing",
                                classification.id,
                                classification.queue,
                            )
                    except Exception:
                        logger.exception(
                            "Failed to enqueue classified reading %s into the QoS pipeline",
                            classification.id,
                        )

                # Process events through the event processing service
                try:
                    event_service = getattr(app_state, "event_processing_service", None)
                    if event_service is not None:
                        # Process only the current reading, not the full batch
                        result = event_service.process([reading], classification)
                        alerts_for_bundle.extend(result["alerts"])
                        
                        # Store events and alerts
                        events_list = getattr(app_state, "events", None)
                        alerts_list = getattr(app_state, "alerts", None)
                        enriched_events_list = getattr(app_state, "enriched_events", None)
                        
                        if events_list is not None:
                            events_list.extend(result["events"])
                        
                        if alerts_list is not None:
                            alerts_list.extend(result["alerts"])
                        
                        # Enrich alerts with contextual information
                        # (WITH_QOS only: enrichment requires a classification)
                        if (
                            enriched_events_list is not None
                            and result["alert_count"] > 0
                            and classification is not None
                        ):
                            for alert in result["alerts"]:
                                try:
                                    # Extract device information from reading
                                    device_info = DeviceInfo(
                                        device_id=alert.device_id,
                                        device_code=reading.device_code,
                                        device_type=reading.device_type or "unknown",
                                        location=None,  # Location would come from device registry
                                    )
                                    
                                    # Get QoS metrics if available
                                    qos_context = None
                                    qos_service = getattr(app_state, "qos_service", None)
                                    if qos_service is not None:
                                        # For now, create a dummy QoS context
                                        # In production, this would be fetched from actual QoS records
                                        from app.events.application.event_enrichment_service import (
                                            QoSContext,
                                        )
                                        qos_context = QoSContext(
                                            latency=0.0,
                                            jitter=0.0,
                                            throughput=0.0,
                                            pdr=100.0,
                                            packet_loss=0.0,
                                        )
                                    
                                    # Enrich the alert
                                    enriched = enrichment_service.enrich(
                                        alert=alert,
                                        device_info=device_info,
                                        classification=classification,
                                        qos_context=qos_context,
                                    )
                                    enriched_events_list.append(enriched)
                                    
                                    logger.debug(
                                        "Enriched alert %s with device, classification, and QoS data",
                                        alert.id,
                                    )
                                except Exception:
                                    logger.exception(
                                        "Failed to enrich alert %s", alert.id
                                    )
                        
                        # Dispatch notifications for generated alerts
                        notification_service = getattr(app_state, "notification_service", None)
                        notifications_list = getattr(app_state, "notifications", None)
                        if notification_service is not None and result["alert_count"] > 0:
                            for alert in result["alerts"]:
                                try:
                                    notif_result = notification_service.process(alert)
                                    if notif_result.notification is not None and notifications_list is not None:
                                        notifications_list.append(notif_result.notification)
                                    logger.info(
                                        "Processed notification %s for alert %s",
                                        getattr(notif_result.notification, "id", None),
                                        alert.id,
                                    )
                                except Exception:
                                    logger.exception(
                                        "Failed to process notification for alert %s", alert.id
                                    )

                        if result["alert_count"] > 0:
                            logger.warning(
                                "Generated %d alerts for device %s (classification %s)",
                                result["alert_count"],
                                reading.device_code,
                                classification.id if classification is not None else None,
                            )
                except Exception:
                    logger.exception(
                        "Failed to process events for classification %s",
                        classification.id if classification is not None else None,
                    )

                if classification is not None:
                    logger.info(
                        "Classified reading from %s:%s as %s",
                        reading.device_code,
                        reading.sensor_name,
                        classification.priority,
                    )
                else:
                    logger.info(
                        "Processed reading from %s:%s without QoS (WITHOUT_QOS)",
                        reading.device_code,
                        reading.sensor_name,
                    )

            # Persist bundle – one transaction per message.
            # WITH_QOS: SensorReading 1:1 TrafficClassification (+QoSMetric/alerts).
            # WITHOUT_QOS: SensorReading + alerts only, no TC/QoS rows.
            # QoSMetric is produced by QoS module, not calculated here (TSK-042 only persists)
            # Resolution is DeviceRepository.get_by_code() -> real Device.id (no fake UUID)
            try:
                persistence_service = getattr(app_state, "persistence_service", None)
                should_persist = persistence_service is not None and (
                    classifications_for_bundle or without_qos
                )
                if should_persist:
                    from app.database.infrastructure.repositories import DeviceRepository
                    from app.database.infrastructure.session import SessionLocal
                    from app.experiments.metrics import record_metrics

                    # Resolve device FK via DeviceRepository (single source of truth)
                    device_code = readings[0].device_code if readings else None
                    if device_code:
                        with SessionLocal() as db:
                            with db.begin():
                                device_row = DeviceRepository().get_by_code(db, device_code)
                                if device_row is None:
                                    logger.warning("Skipping persistence: Device code %s not found in DB", device_code)
                                else:
                                    # Use first classification as representative for 1:1 bundle
                                    tc = classifications_for_bundle[0] if classifications_for_bundle else None
                                    persistence_service.persist_bundle(
                                        db,
                                        readings=readings,
                                        device_id=device_row.id,
                                        classification=tc,
                                        qos_metric=qos_for_bundle,
                                        alerts=alerts_for_bundle,
                                        predictions=None,
                                        run_id=run_id,
                                    )
                                    logger.info(
                                        "Persisted bundle for device %s: SensorReading + TC %s + %d alerts (run %s)",
                                        device_code,
                                        tc.id if tc is not None else None,
                                        len(alerts_for_bundle),
                                        run_id,
                                    )
                                    if run_id is not None:
                                        persist_ts = datetime.now(timezone.utc)
                                        metrics: list[tuple[str, float, datetime | None]] = [
                                            ("readings_persisted", 1.0, persist_ts),
                                        ]
                                        for alert in alerts_for_bundle:
                                            metrics.append(("alerts_generated", 1.0, alert.created_at))
                                            alert_ms = _ms_between(received_at, alert.created_at)
                                            if alert_ms is not None:
                                                metrics.append(
                                                    ("ingest_to_alert_ms", alert_ms, alert.created_at)
                                                )
                                        persist_ms = _ms_between(received_at, persist_ts)
                                        if persist_ms is not None:
                                            metrics.append(
                                                ("ingest_to_persist_ms", persist_ms, persist_ts)
                                            )
                                        record_metrics(run_id, metrics)
            except Exception:
                logger.exception("Failed to persist bundle for message %s", message.get("topic"))

        except Exception:
            logger.exception("Unhandled error in acquisition->classification worker loop")


class AcquisitionPipeline:
    """Helper to manage the worker thread lifecycle."""

    def __init__(self, message_queue, app_state) -> None:
        self._queue = message_queue
        self._app_state = app_state
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=_worker_loop, args=(self._queue, self._app_state, self._stop_event), daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=2.0)
