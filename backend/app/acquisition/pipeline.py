from __future__ import annotations

import itertools
import logging
import threading
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

_SCENARIOS = ("WITH_QOS", "WITHOUT_QOS")


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
        elapsed = (end - start).total_seconds() * 1000.0
        return elapsed if elapsed >= 0 else None
    except Exception:
        return None


def _ms_between_monotonic(start: float | None, end: float | None) -> float | None:
    """Real interval in milliseconds from monotonic clocks, or None."""
    if start is None or end is None:
        return None
    try:
        elapsed = (float(end) - float(start)) * 1000.0
        return elapsed if elapsed >= 0 else None
    except (TypeError, ValueError):
        return None


def _parse_received_at(message: dict) -> datetime | None:
    """TSK-059.7 — real ingestion instant, or None when unavailable.

    Never fabricated: without received_at no ingest-based latency is recorded.
    Non-dict queue items yield None instead of raising (they are still
    counted as invalid downstream, never crash the loop).
    """
    if not isinstance(message, dict):
        return None
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


def _sealed_context(message: dict) -> tuple[UUID | None, str]:
    """Read the experimental context sealed at reception.

    Messages received by ``MQTTSubscriber`` already carry ``scenario`` and
    ``run_id``.  Direct callers (tests, maintenance scripts) may not, so the
    fallback resolves once at ingestion; it is never re-resolved at attention.
    """
    if isinstance(message, dict):
        scenario = message.get("scenario")
        if scenario in _SCENARIOS:
            raw_run_id = message.get("run_id")
            run_id: UUID | None = None
            if raw_run_id:
                try:
                    run_id = UUID(str(raw_run_id))
                except (TypeError, ValueError):
                    logger.warning("Invalid sealed run_id %r; using None", raw_run_id)
            return run_id, scenario

    from app.experiments.active import resolve_scenario

    return resolve_scenario()


def _ensure_state_lists(app_state) -> None:
    for name in (
        "classifications",
        "events",
        "alerts",
        "enriched_events",
        "notifications",
    ):
        if not hasattr(app_state, name):
            setattr(app_state, name, [])


def _build_coordinator(app_state):
    """Create or reuse the production coordinator from the effective config.

    Building it eagerly (e.g. at startup) makes runtime observability
    available before the first message arrives; the worker reuses the same
    instance instead of creating a second, disconnected one.
    """
    from app.qos.application.dispatcher import DispatchCoordinator
    from app.qos.application.traffic_planning_service import TrafficPlanningService
    from app.qos.application.wfq_scheduler import WFQScheduler

    existing = getattr(app_state, "dispatch_coordinator", None)
    if existing is not None:
        return existing

    config = getattr(app_state, "backend_config", None)
    flow_weights = getattr(config, "qos_wfq_flow_weights", None) or {}
    planner = TrafficPlanningService(
        wfq_scheduler=WFQScheduler(flow_weights=flow_weights)
    )
    coordinator = DispatchCoordinator(
        planner,
        capacity=getattr(config, "qos_pending_capacity", 3000),
        high_quota=getattr(config, "qos_high_quota", 4),
        medium_quota=getattr(config, "qos_medium_quota", 2),
        low_quota=getattr(config, "qos_low_quota", 1),
        failure_capacity=getattr(config, "qos_recent_failure_capacity", 100),
    )
    # Expose runtime state for observability without sharing the demonstration
    # planner stored in ``app_state.qos_service``.
    app_state.dispatch_planner = planner
    app_state.dispatch_coordinator = coordinator
    return coordinator


def build_dispatch_coordinator(app_state):
    """Public entry point for eager construction during application startup."""
    return _build_coordinator(app_state)


def _record_run_metrics(
    run_id: UUID | None,
    entries: list[tuple[str, float, datetime | None]],
) -> None:
    if run_id is None or not entries:
        return
    from app.experiments.metrics import record_metrics

    record_metrics(run_id, entries)


def _persist_qos_attention(work_item, *, selected_at, committed_at, finished_at,
                           queue_wait_ms, service_time_ms):
    """Write a v2 observation in a separate transaction after reading commit."""
    if work_item.classification is None or committed_at is None:
        return
    from app.database.infrastructure.models import QoSMetricORM
    from app.database.infrastructure.session import SessionLocal

    elapsed = _ms_between(work_item.received_at, committed_at)
    latency = elapsed / 1000 if elapsed is not None and elapsed >= 0 else None
    try:
        with SessionLocal() as db:
            with db.begin():
                db.add(QoSMetricORM(
                    id=uuid4(), classification_id=work_item.classification.id,
                    processing_version=2, timestamp=finished_at,
                    latency=latency, packet_loss=None, throughput=None,
                    pdr=None, jitter=None, selected_at=selected_at,
                    persisted_at=committed_at, finished_at=finished_at,
                    queue_wait_ms=queue_wait_ms, service_time_ms=service_time_ms,
                ))
    except Exception:
        logger.exception("Failed to persist QoS observation for work %s; reading remains committed", work_item.id)


def _notify_alerts(alerts: list, app_state) -> list:
    """Dispatch notifications for confirmed alerts and return trace records."""
    notification_service = getattr(app_state, "notification_service", None)
    notifications_list = getattr(app_state, "notifications", None)
    records: list = []
    if notification_service is None or not alerts:
        return records

    for alert in alerts:
        try:
            notif_result = notification_service.process(alert)
            if notif_result.notification is not None and notifications_list is not None:
                notifications_list.append(notif_result.notification)
            try:
                notif_recipient = notification_service.resolve_recipient(alert)
                notif_message = notification_service.resolve_message(alert)
            except Exception:
                notif_recipient, notif_message = None, None
            records.append((alert, notif_result, notif_recipient, notif_message))
            logger.info(
                "Processed notification %s for alert %s",
                getattr(notif_result.notification, "id", None),
                alert.id,
            )
        except Exception:
            logger.exception("Failed to process notification for alert %s", alert.id)
    return records


def _persist_notification_records(notification_records: list) -> None:
    """Persist delivery trace rows in an isolated transaction.

    A failure here only loses traceability rows (logged), never alerts or
    readings.  Idempotency via UNIQUE(alert_id, channel, recipient): replays
    and retries skip already-recorded rows without re-sending.
    """
    if not notification_records:
        return
    try:
        from uuid import UUID as _UUID

        from app.database.infrastructure.models import (
            HUMAN_USER_ROLES as _HUMAN_ROLES,
        )
        from app.database.infrastructure.models import (
            UserORM as _UserORM,
        )
        from app.database.infrastructure.repositories import (
            NotificationRepository as _NotificationRepository,
        )
        from app.database.infrastructure.session import (
            SessionLocal as _SessionLocal,
        )

        def _recipient_for(_user, _channel: str) -> str | None:
            """Per-user delivery address for the resolved channel.

            Keeps UNIQUE(alert_id, channel, recipient) distinct per
            recipient. SMS without phone falls back to a user-scoped
            placeholder (still SIMULATED, logged, never sent).
            """
            if _channel == "email":
                return (_user.email or "").strip() or None
            if _channel == "sms":
                phone = (_user.phone or "").strip()
                return phone or f"user:{_user.id}"
            return str(_user.id)

        _repo = _NotificationRepository()
        with _SessionLocal() as _notif_db:
            with _notif_db.begin():
                # Recipient policy (RBAC-coherent): active humans
                # with a supervising role (admin, supervisor,
                # operador, auditor read-only). System/inactive
                # users never own notifications.
                _humans = (
                    _notif_db.query(_UserORM)
                    .filter(_UserORM.is_active.is_(True))
                    .filter(_UserORM.role.in_(sorted(_HUMAN_ROLES)))
                    .all()
                )
                for _alert, _result, _recipient, _message in notification_records:
                    _notif = getattr(_result, "notification", None)
                    if _notif is None:
                        continue
                    if not isinstance(_message, str) or not _message.strip():
                        continue
                    _channel = _notif.channel.value
                    # Fan-out targets: one row per active human
                    # recipient. Legacy fallback (no humans in DB):
                    # single row owned by the alert author.
                    _targets: list[tuple] = []
                    for _user in _humans:
                        _addr = _recipient_for(_user, _channel)
                        if _addr:
                            _targets.append((_user.id, _addr))
                    if not _targets and isinstance(_alert.user_id, _UUID):
                        if isinstance(_recipient, str) and _recipient.strip():
                            _targets.append((_alert.user_id, _recipient.strip()))
                    for _owner_id, _addr in _targets:
                        if _repo.find_duplicate(
                            _notif_db,
                            _alert.id,
                            _channel,
                            _addr,
                        ):
                            continue
                        _send = getattr(_result, "send_result", None)
                        # NOTE: no notification_id reuse here: each
                        # fan-out row gets its own PK (the domain
                        # id identifies the delivery attempt, not
                        # the per-recipient record).
                        _repo.create(
                            _notif_db,
                            alert_id=_alert.id,
                            user_id=_owner_id,
                            channel=_channel,
                            status=_notif.status.value,
                            recipient=_addr,
                            message=_message,
                            detail=(
                                _send.detail if _send is not None
                                else _result.error
                            ),
                            notification_date=_notif.notification_date,
                        )
    except Exception:
        logger.exception(
            "Failed to persist notification records "
            "(alerts and readings are unaffected)"
        )


def _record_attention_metrics(work_item, alerts: list, committed_at: datetime) -> None:
    """Record per-reading timings only after the commit is confirmed."""
    if work_item.run_id is None:
        return
    metrics: list[tuple[str, float, datetime | None]] = [
        ("readings_persisted", 1.0, committed_at),
    ]
    for alert in alerts:
        metrics.append(("alerts_generated", 1.0, alert.created_at))
        alert_ms = _ms_between(work_item.received_at, alert.created_at)
        if alert_ms is not None:
            metrics.append(("ingest_to_alert_ms", alert_ms, alert.created_at))
    persist_ms = _ms_between(work_item.received_at, committed_at)
    if persist_ms is not None:
        metrics.append(("ingest_to_persist_ms", persist_ms, committed_at))
    _record_run_metrics(work_item.run_id, metrics)


def _record_attention_timing(
    work_item,
    *,
    queue_wait_ms: float | None,
    service_time_ms: float | None,
    success: bool,
) -> None:
    """Record per-attention timings only for measurable, real intervals.

    Called after the attention finished (and, on success, after the commit),
    so a failure is counted as ``readings_failed`` instead of a success.  A
    missing measurement is skipped, never stored as zero.
    """
    if work_item.run_id is None:
        return
    recorded_at = datetime.now(timezone.utc)
    entries: list[tuple[str, float, datetime | None]] = []
    if not success:
        entries.append(("readings_failed", 1.0, recorded_at))
    if queue_wait_ms is not None:
        entries.append(("queue_wait_ms", queue_wait_ms, recorded_at))
    if service_time_ms is not None:
        entries.append(("service_time_ms", service_time_ms, recorded_at))
    _record_run_metrics(work_item.run_id, entries)


def _already_persisted(work_item) -> bool:
    """True when this work UUID already has a committed reading row."""
    try:
        from app.database.infrastructure.models import SensorReadingORM
        from app.database.infrastructure.session import SessionLocal

        with SessionLocal() as db:
            return db.get(SensorReadingORM, work_item.id) is not None
    except Exception:
        logger.exception("Failed to check replay state for work %s", work_item.id)
        return False


def _process_work_item(work_item, app_state) -> datetime | None:
    """Attention for exactly one selected reading.

    Order is fixed: rules/events/alerts -> reading transaction -> confirmed
    commit -> notifications.  A persistence failure ends this reading as
    failed and never sends its notifications.
    """
    reading = work_item.to_reading()
    classification = (
        work_item.classification.to_classification()
        if work_item.classification is not None
        else None
    )

    persistence_service = getattr(app_state, "persistence_service", None)
    if persistence_service is not None and _already_persisted(work_item):
        logger.info(
            "Work %s (%s:%s) was already persisted; replay skipped",
            work_item.id,
            work_item.device_code,
            work_item.sensor_name,
        )
        return

    alerts: list = []
    events: list = []
    event_service = getattr(app_state, "event_processing_service", None)
    if event_service is not None:
        result = event_service.process([reading], classification)
        events = result["events"]
        alerts = result["alerts"]
        if alerts:
            logger.warning(
                "Generated %d alerts for device %s sensor %s (work %s)",
                len(alerts),
                work_item.device_code,
                work_item.sensor_name,
                work_item.id,
            )

    if persistence_service is None:
        # Without a persistence service there is no confirmed commit, so no
        # notifications are emitted from this attention.
        return

    from app.database.infrastructure.repositories import DeviceRepository
    from app.database.infrastructure.session import SessionLocal

    with SessionLocal() as db:
        with db.begin():
            device_row = DeviceRepository().get_by_code(db, work_item.device_code)
            if device_row is None:
                raise LookupError(
                    f"Device code {work_item.device_code!r} not found in DB"
                )
            persistence_service.persist_work_item(
                db,
                work_item=work_item,
                device_id=device_row.id,
                qos_metric=None,
                alerts=alerts,
            )

    # The transaction has committed: only now is persistence confirmed.
    committed_at = datetime.now(timezone.utc)
    # Session APIs expose confirmed effects only. A rollback must not leave
    # alerts/events in memory that have no corresponding committed reading.
    events_list = getattr(app_state, "events", None)
    alerts_list = getattr(app_state, "alerts", None)
    if events_list is not None:
        events_list.extend(events)
    if alerts_list is not None:
        alerts_list.extend(alerts)
    logger.info(
        "Persisted reading %s for %s:%s (run %s)",
        work_item.id,
        work_item.device_code,
        work_item.sensor_name,
        work_item.run_id,
    )
    _record_attention_metrics(work_item, alerts, committed_at)

    notification_records = _notify_alerts(alerts, app_state)
    _persist_notification_records(notification_records)
    return committed_at


def _attention_loop(coordinator, app_state, stop_event: threading.Event) -> None:
    """Single consumer: select first, then produce every durable effect.

    The loop only exits once admission is closed and every admitted reading
    has been attended, so a shutdown never drops work that ingestion already
    accepted.  ``stop_event`` merely keeps the loop responsive while open.
    """
    while True:
        if coordinator.is_closed and coordinator.is_empty():
            return
        try:
            if not coordinator.wait_for_work(timeout=0.25):
                continue
            work_item = coordinator.select_next()
            if work_item is None:
                continue
            selected_monotonic = time.monotonic()
            selected_at = datetime.now(timezone.utc)
            success = False
            committed_at = None
            try:
                committed_at = _process_work_item(work_item, app_state)
                success = True
            except Exception:
                logger.exception(
                    "Attention failed for work %s (%s:%s)",
                    work_item.id,
                    work_item.device_code,
                    work_item.sensor_name,
                )
            finally:
                finished_at = datetime.now(timezone.utc)
                queue_wait_ms = _ms_between_monotonic(
                    work_item.admitted_monotonic, selected_monotonic
                )
                service_time_ms = _ms_between_monotonic(
                    selected_monotonic, time.monotonic()
                )
                if success and committed_at is not None:
                    _persist_qos_attention(
                        work_item, selected_at=selected_at,
                        committed_at=committed_at, finished_at=finished_at,
                        queue_wait_ms=queue_wait_ms, service_time_ms=service_time_ms,
                    )
                _record_attention_timing(
                    work_item,
                    queue_wait_ms=queue_wait_ms,
                    service_time_ms=service_time_ms,
                    success=success,
                )
                coordinator.finish(success=success)
        except Exception:
            logger.exception("Unhandled error in QoS attention loop")


@lru_cache(maxsize=1)
def _ingestion_services():
    """Stateless normalization/classification collaborators, created once."""
    from app.acquisition.normalizer import TelemetryNormalizer
    from app.classification.application.classification_service import (
        ClassificationService,
    )
    from app.classification.application.criticality_calculator import (
        CriticalityCalculator,
    )
    from app.classification.application.priority_assigner import PriorityAssigner
    from app.classification.application.risk_matrix_evaluator import RiskMatrixEvaluator

    return (
        TelemetryNormalizer(),
        ClassificationService(
            calculator=CriticalityCalculator(), assigner=PriorityAssigner()
        ),
        RiskMatrixEvaluator(),
    )


def _ingest_message(
    message,
    app_state,
    coordinator,
    sequence_counter,
    received_at: datetime | None,
    *,
    accepted_before_drain: bool = False,
) -> None:
    """Normalize and classify one received message into per-sensor work items."""
    from app.qos.domain.work_item import WorkItem

    normalizer, service, risk_evaluator = _ingestion_services()
    run_id, scenario = _sealed_context(message)
    without_qos = scenario == "WITHOUT_QOS"

    try:
        readings = normalizer.normalize(message)
    except Exception as exc:
        logger.exception("Failed to normalize message: %s", exc)
        _record_run_metrics(run_id, [("messages_invalid", 1.0, received_at)])
        return

    source_message_id = uuid4()
    msg_received_at = (
        message.get("received_at") if isinstance(message, dict) else None
    )
    msg_topic = message.get("topic") if isinstance(message, dict) else None
    received_monotonic = (
        message.get("received_monotonic") if isinstance(message, dict) else None
    )
    if isinstance(received_monotonic, bool) or not isinstance(
        received_monotonic, (int, float)
    ):
        received_monotonic = None

    for reading in readings:
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
                # A sensor that cannot be classified does not affect its
                # siblings; only this reading is skipped.
                logger.exception(
                    "Classification failed for reading %s:%s: %s",
                    reading.device_code,
                    reading.sensor_name,
                    exc,
                )
                continue

        admitted_at = datetime.now(timezone.utc)
        admitted_monotonic = time.monotonic()
        try:
            work_item = WorkItem.from_reading(
                reading,
                source_message_id=source_message_id,
                sequence=next(sequence_counter),
                scenario=scenario,
                run_id=run_id,
                admitted_at=admitted_at,
                admitted_monotonic=admitted_monotonic,
                classification=classification,
                received_at=received_at,
                received_monotonic=received_monotonic,
            )
        except Exception as exc:
            logger.exception(
                "Failed to create work item for reading %s:%s: %s",
                reading.device_code,
                reading.sensor_name,
                exc,
            )
            continue

        # In-memory trace of ingestion (never an attention effect).  WITHOUT_QOS
        # has no classification, so it is not presented as a classified result.
        if classification is not None:
            entry = {
                "classification": classification,
                "reading": reading,
                "device_code": reading.device_code,
                "received_at": msg_received_at,
                "topic": msg_topic,
                "work_id": work_item.id,
                "scenario": scenario,
                "run_id": run_id,
            }
            app_state.classifications.append(entry)

        admitted = (
            coordinator.admit(work_item, accepted_before_drain=True)
            if accepted_before_drain else coordinator.admit(work_item)
        )
        _record_run_metrics(
            run_id,
            [
                (
                    "readings_admitted" if admitted else "readings_rejected",
                    1.0,
                    admitted_at,
                )
            ],
        )
        if not admitted:
            logger.warning(
                "Reading %s:%s rejected by planner admission (capacity %s)",
                reading.device_code,
                reading.sensor_name,
                coordinator.capacity,
            )
            continue

        if classification is not None:
            logger.info(
                "Classified reading from %s:%s as %s (work %s)",
                reading.device_code,
                reading.sensor_name,
                classification.priority,
                work_item.id,
            )
        else:
            logger.info(
                "Admitted reading from %s:%s without QoS (WITHOUT_QOS, work %s)",
                reading.device_code,
                reading.sensor_name,
                work_item.id,
            )


def _worker_loop(message_queue, app_state, stop_event: threading.Event) -> None:
    """Ingestion plus one attention consumer.

    The ingestion loop only normalizes, classifies and admits work.  The
    attention thread selects one admitted reading at a time and is the sole
    producer of events, persistence and notifications.  A pending reading can
    therefore never have durable effects before it is selected.
    """
    _ensure_state_lists(app_state)
    coordinator = _build_coordinator(app_state)
    sequence_counter = itertools.count()

    attention = threading.Thread(
        target=_attention_loop,
        args=(coordinator, app_state, stop_event),
        name="coldchain-qos-attention",
        daemon=True,
    )
    attention.start()

    try:
        while True:
            try:
                tracked = hasattr(message_queue, "pop_for_processing")
                message = message_queue.pop_for_processing() if tracked else message_queue.pop()
            except Exception:
                logger.exception("Failed to pop a transport message")
                message = None

            if message is None:
                if stop_event.is_set():
                    break
                time.sleep(0.25)
                continue

            try:
                # The transport claim remains outstanding through normalization
                # and admission, so a drain cannot observe a false empty gap.
                try:
                    backlog = float(len(message_queue.get_all()))
                except Exception:
                    backlog = 0.0
                run_id, _scenario = _sealed_context(message)
                received_at = _parse_received_at(message)
                _record_run_metrics(run_id, [
                    ("messages_received", 1.0, received_at),
                    ("backlog", backlog, received_at),
                ])
                _ingest_message(
                    message,
                    app_state,
                    coordinator,
                    sequence_counter,
                    received_at,
                    accepted_before_drain=tracked,
                )
            except Exception:
                logger.exception("Unhandled error while ingesting a message")
            finally:
                if tracked:
                    message_queue.finish_processing(message)
    finally:
        coordinator.close_admission()
        coordinator.wake()
        # The owner enforces the deadline and cancels pending work. An already
        # selected transaction cannot safely be interrupted: wait for it.
        attention.join()
        # Explicit shutdown outcome: leftover work is reported, never silent.
        snapshot = coordinator.snapshot()
        if snapshot["pending"] or snapshot["in_flight"]:
            logger.warning(
                "Dispatch shutdown left %s pending and %s in flight; "
                "they were not persisted",
                snapshot["pending"],
                snapshot["in_flight"],
            )
        else:
            logger.info(
                "Dispatch drained on shutdown: %s attended, %s failed",
                snapshot["completed"],
                snapshot["failed"],
            )


class AcquisitionPipeline:
    """Helper to manage the worker thread lifecycle."""

    def __init__(self, message_queue, app_state, *, shutdown_timeout: float = 30.0) -> None:
        self._queue = message_queue
        self._app_state = app_state
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        if shutdown_timeout < 0:
            raise ValueError("shutdown_timeout must be non-negative")
        self._shutdown_timeout = shutdown_timeout

    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=_worker_loop,
                args=(self._queue, self._app_state, self._stop_event),
                name="coldchain-acquisition",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=self._shutdown_timeout)
            if self._thread.is_alive():
                logger.warning("Shutdown deadline exceeded; cancelling pending work")
                coordinator = getattr(self._app_state, "dispatch_coordinator", None)
                if coordinator is not None:
                    for item in coordinator.cancel_pending():
                        logger.warning(
                            "Cancelled pending work %s run=%s device=%s sensor=%s",
                            item.id, item.run_id, item.device_code, item.sensor_name,
                        )
                messages = self._queue.cancel_pending()
                logger.warning("Cancelled %d pending transport messages", len(messages))
                for message in messages:
                    logger.warning("Cancelled transport message topic=%s run=%s",
                                   message.get("topic") if isinstance(message, dict) else None,
                                   message.get("run_id") if isinstance(message, dict) else None)
                self._thread.join()
