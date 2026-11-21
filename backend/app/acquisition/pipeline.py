from __future__ import annotations

import itertools
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional
from uuid import UUID, uuid4, uuid5

from app.acquisition.telemetry_trace import emission_trace, record_trace

logger = logging.getLogger(__name__)

_SCENARIOS = ("WITH_QOS", "WITHOUT_QOS")
COLOMBIA_TIMEZONE = timezone(timedelta(hours=-5), "COT")


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


def _critical_email_message(alert, device_code: str) -> str:
    """Render the local critical-email template from a persisted alert."""
    type_labels = {
        "TEMPERATURE_EXCEEDED": "Temperatura fuera del rango permitido",
        "TEMPERATURE_BELOW_MIN": "Temperatura por debajo del rango permitido",
        "HUMIDITY_ABOVE_MAX": "Humedad fuera del rango permitido",
        "HUMIDITY_BELOW_MIN": "Humedad por debajo del rango permitido",
        "ENERGY_STATE_ANOMALY": "Estado de energía anómalo",
    }
    values = re.findall(r"\(([^)]+)\)", alert.message)
    observed = values[0] if values else "No disponible"
    configured_range = values[1] if len(values) > 1 else "Ver detalle técnico"
    created_at = _as_aware_utc(alert.created_at) or datetime.now(timezone.utc)
    colombia_created_at = created_at.astimezone(COLOMBIA_TIMEZONE)
    return f"""Se ha detectado una alerta crítica en el sistema de refrigeración.

Estimado usuario:

El sistema ColdChain-IoT ha identificado una condición crítica que requiere atención inmediata, debido a que podría comprometer las condiciones de conservación de los productos almacenados.

DETALLES DE LA ALERTA

- Dispositivo: {device_code}
- Tipo de alerta: {type_labels.get(alert.type, alert.type)}
- Valor registrado: {observed}
- Rango establecido: {configured_range}
- Nivel de criticidad: CRÍTICO ({alert.criticality:g}/9)
- Fecha y hora: {colombia_created_at.strftime('%d/%m/%Y – %H:%M')} (hora Colombia)
- Estado: Pendiente de atención
- Detalle técnico: {alert.message}

ACCIÓN RECOMENDADA

Se recomienda verificar inmediatamente el estado del sistema de refrigeración, comprobar las condiciones del dispositivo y realizar las acciones correctivas necesarias para evitar posibles afectaciones a los productos almacenados.

Por favor, ingrese a la plataforma ColdChain-IoT para consultar los detalles de la alerta y realizar el seguimiento correspondiente.

IMPORTANTE: Esta notificación ha sido generada automáticamente por el sistema de monitoreo. La alerta permanecerá sujeta a seguimiento hasta que se verifique y atienda la condición detectada.

Atentamente,
Sistema de monitoreo ColdChain-IoT
Monitoreo y gestión de alertas para la conservación de la cadena de frío.
"""


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
    band_weights = getattr(config, "qos_wfq_band_weights", None)
    planner = TrafficPlanningService(
        wfq_scheduler=WFQScheduler(band_weights=band_weights)
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
    record_trace(
        "dispatch_config",
        config={
            "wfq_policy": "criticality_bands_v1", "cost_per_reading": 1,
            "band_weights": planner.wfq.band_weights,
            "class_quotas": {
                priority: sum(value.value == priority for value in coordinator.class_cycle)
                for priority in ("high", "medium", "low")
            },
            "pending_capacity": coordinator.capacity,
        },
    )
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
    """Deliver confirmed alerts to logged-in humans, never before selection/commit.

    Keep main's recipient-specific dashboard/email policy, but execute it from
    the v2 attention worker, not the ingestion/transport loop. Notification
    failures cannot roll back the already committed reading or alert.
    """
    notification_service = getattr(app_state, "notification_service", None)
    records: list = []
    if notification_service is None or not alerts:
        return records

    try:
        from app.auth.sessions import active_sessions
        from app.database.infrastructure.models import (
            HUMAN_USER_ROLES,
            DeviceORM,
            UserORM,
        )
        from app.database.infrastructure.session import SessionLocal

        active_ids = active_sessions.active_user_ids()
        if not active_ids:
            return records
        with SessionLocal() as db:
            with db.begin():
                humans = (
                    db.query(UserORM)
                    .filter(UserORM.is_active.is_(True))
                    .filter(UserORM.role.in_(sorted(HUMAN_USER_ROLES)))
                    .filter(UserORM.id.in_(active_ids))
                    .all()
                )
                device_codes = {
                    device.id: device.code
                    for device in db.query(DeviceORM)
                    .filter(DeviceORM.id.in_({alert.device_id for alert in alerts}))
                    .all()
                }
                for alert in alerts:
                    message = notification_service.resolve_message(alert)
                    if not isinstance(message, str) or not message.strip():
                        continue
                    channels = (
                        ("dashboard", "email")
                        if alert.criticality is not None and alert.criticality >= 8
                        else ("dashboard",)
                    )
                    for channel in channels:
                        for user in humans:
                            recipient = (user.email or "").strip() if channel == "email" else str(user.id)
                            if not recipient:
                                continue
                            delivery_message = (
                                _critical_email_message(alert, device_codes.get(alert.device_id, str(alert.device_id)))
                                if channel == "email" else message
                            )
                            # Check idempotency BEFORE sending to each real
                            # recipient; never copy one delivery's outcome to others.
                            result, _row = notification_service.process_and_persist(
                                alert, db, recipient=recipient,
                                message=delivery_message, user_id=user.id,
                                channel_override=channel,
                            )
                            if result.notification is not None:
                                records.append(result.notification)
        # Do not expose notification rows that were rolled back.
        notifications_list = getattr(app_state, "notifications", None)
        if notifications_list is not None:
            notifications_list.extend(records)
        return records
    except Exception:
        logger.exception(
            "Failed to deliver or persist notification records "
            "(alerts and readings are unaffected)"
        )
        return []


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
        record_trace("replay_skipped", source_message_id=str(work_item.source_message_id),
                     work_id=str(work_item.id), sensor_name=work_item.sensor_name,
                     run_id=str(work_item.run_id) if work_item.run_id else None)
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
    record_trace(
        "persisted", source_message_id=str(work_item.source_message_id),
        work_id=str(work_item.id), sensor_name=work_item.sensor_name,
        device_code=work_item.device_code, run_id=str(work_item.run_id) if work_item.run_id else None,
        committed_at=committed_at.isoformat(),
        alerts=[{"alert_id": str(alert.id), "created_at": alert.created_at.isoformat()}
                for alert in alerts],
        generated_at=work_item.timestamp,
        priority=work_item.priority,
    )
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

    _notify_alerts(alerts, app_state)
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
                record_trace("reading_failed", source_message_id=str(work_item.source_message_id),
                             work_id=str(work_item.id), sensor_name=work_item.sensor_name,
                             run_id=str(work_item.run_id) if work_item.run_id else None)
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

    trace = emission_trace(message.get("payload")) if isinstance(message, dict) else None
    source_message_id = UUID(trace["message_id"]) if trace else uuid4()
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
                id=uuid5(source_message_id, reading.sensor_name) if trace else None,
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
        record_trace(
            "reading_admitted" if admitted else "reading_rejected",
            source_message_id=str(source_message_id), work_id=str(work_item.id),
            device_code=work_item.device_code, sensor_name=work_item.sensor_name,
            priority=work_item.priority, generated_at=work_item.timestamp,
            run_id=str(work_item.run_id) if work_item.run_id else None,
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
                        record_trace("reading_cancelled", source_message_id=str(item.source_message_id),
                                     work_id=str(item.id), sensor_name=item.sensor_name,
                                     run_id=str(item.run_id) if item.run_id else None)
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
