from __future__ import annotations

import threading
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _worker_loop(message_queue, app_state, stop_event: threading.Event) -> None:
    """Background worker that consumes messages, normalizes them and sends to classifier.

    The worker keeps an in-memory list at app_state.classifications where each entry
    contains the generated TrafficClassification and a reference to the originating
    normalized reading. This is intentionally simple to keep the integration light
    and easy to extend later (persisting to DB, forwarding to QoS, etc.).
    """
    from app.acquisition.normalizer import TelemetryNormalizer

    from app.classification.application.classification_service import (
        ClassificationService,
    )
    from app.classification.application.criticality_calculator import CriticalityCalculator
    from app.classification.application.priority_assigner import PriorityAssigner
    from app.classification.application.risk_matrix_evaluator import RiskMatrixEvaluator
    from app.qos.application.qos_metrics_service import MessageDeliveryRecord

    normalizer = TelemetryNormalizer()
    calculator = CriticalityCalculator()
    assigner = PriorityAssigner()
    service = ClassificationService(calculator=calculator, assigner=assigner)
    risk_evaluator = RiskMatrixEvaluator()

    # ensure classifications list exists
    if not hasattr(app_state, "classifications"):
        app_state.classifications = []

    while not stop_event.is_set():
        try:
            message = message_queue.pop()
            if message is None:
                time.sleep(0.25)
                continue

            try:
                readings = normalizer.normalize(message)
            except Exception as exc:
                logger.exception("Failed to normalize message: %s", exc)
                continue

            # Derive I/U/R from each reading using the risk matrix. The
            # evaluator is the source of truth; payload impact/urgency/risk
            # fields are intentionally ignored to keep classifications
            # consistent with the real sensor conditions.
            for reading in readings:
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

                try:
                    qos_service = getattr(app_state, "qos_service", None)
                    if qos_service is not None:
                        qos_service.plan(classification)
                        qos_records = getattr(app_state, "qos_records", None)
                        if qos_records is not None:
                            qos_records.append(
                                MessageDeliveryRecord(
                                    message_id=str(classification.id),
                                    sent_at=classification.timestamp,
                                    received_at=classification.classification_time,
                                    size_bytes=128.0,
                                    delivered=True,
                                    criticality=classification.criticality,
                                    priority=classification.priority,
                                )
                            )
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

                logger.info(
                    "Classified reading from %s:%s as %s",
                    reading.device_code,
                    reading.sensor_name,
                    classification.priority,
                )
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
