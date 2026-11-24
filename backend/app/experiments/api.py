"""REST API for experiment runs and common metrics (TSK-059.6/059.7).

Reads are authenticated; starting/finishing a run is admin-only.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.authorization import authenticated
from app.database.infrastructure.repositories import (
    ExperimentMetricRepository,
    ExperimentRunRepository,
    SystemConfigRepository,
)
from app.database.infrastructure.session import get_db
from app.experiments.active import clear_active_run, set_active_run
from app.experiments.worker import start_worker, stop_worker
from app.experiments.schemas import (
    ExperimentMetricListResponse,
    ExperimentMetricResponse,
    ExperimentRunListResponse,
    ExperimentRunResponse,
    ExperimentEvidenceResponse,
    ExperimentAnalysisResponse,
)
from app.security.dependencies import require_admin

router = APIRouter(
    prefix="/experiment-runs", tags=["experiments"], dependencies=[Depends(authenticated)]
)
logger = logging.getLogger(__name__)
_runs = ExperimentRunRepository()
_metrics = ExperimentMetricRepository()
_finish_lock = threading.Lock()
_background_finishes: set[UUID] = set()
_background_lock = threading.Lock()


def _continue_finish_in_background(run_id: UUID, request: Request) -> None:
    """Retry a timed-out drain without discarding admitted telemetry."""
    from app.database.infrastructure.session import SessionLocal

    with _background_lock:
        if run_id in _background_finishes:
            return
        _background_finishes.add(run_id)

    def finish_when_drained():
        try:
            while True:
                try:
                    with _finish_lock, SessionLocal() as db:
                        _finish_run_locked(run_id, request, db)
                    return
                except HTTPException as exc:
                    if exc.status_code != 409 or exc.detail != "Experiment is still draining; retry finish":
                        logger.warning("Background finish for %s stopped: %s", run_id, exc.detail)
                        return
                    threading.Event().wait(1)
                except Exception:
                    logger.exception("Background finish for %s failed", run_id)
                    return
        finally:
            with _background_lock:
                _background_finishes.discard(run_id)

    threading.Thread(target=finish_when_drained, name=f"finish-{run_id}", daemon=True).start()


def _validate_page(per_page: int, page: int):
    if page < 1:
        raise HTTPException(400, "page must be >=1")
    if not 1 <= per_page <= 100:
        raise HTTPException(400, "per_page must be 1..100")


def _serialize_run(run) -> ExperimentRunResponse:
    with _background_lock:
        closing = run.finished_at is None and run.id in _background_finishes
    return ExperimentRunResponse(
        id=str(run.id),
        scenario=run.scenario,
        started_at=run.started_at,
        finished_at=run.finished_at,
        config_snapshot=run.config_snapshot,
        closing=closing,
    )


def _serialize_metric(metric) -> ExperimentMetricResponse:
    return ExperimentMetricResponse(
        id=str(metric.id),
        run_id=str(metric.run_id),
        metric_type=metric.metric_type,
        value=metric.value,
        timestamp=metric.timestamp,
    )


@router.get("", response_model=ExperimentRunListResponse)
def list_runs(
    scenario: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _validate_page(per_page, page)
    try:
        total, items = _runs.list(db, scenario=scenario, page=page, per_page=per_page)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ExperimentRunListResponse(
        total=total,
        page=page,
        per_page=per_page,
        count=len(items),
        results=[_serialize_run(i) for i in items],
    )


@router.get("/{run_id}", response_model=ExperimentRunResponse)
def get_run(run_id: UUID, db: Session = Depends(get_db)):
    run = _runs.get_by_id(db, run_id)
    if run is None:
        raise HTTPException(404, "Experiment run not found")
    return _serialize_run(run)


class ExperimentRunStartRequest(BaseModel):
    scenario: str
    config_snapshot: Optional[dict] = None


@router.post("", response_model=ExperimentRunResponse, status_code=status.HTTP_201_CREATED)
def start_run(
    body: ExperimentRunStartRequest,
    request: Request,
    db: Session = Depends(get_db),
    _current=Depends(require_admin),
):
    """Start an experiment run and mark it active for the pipeline worker.

    409 when another run is already active or the previous one is still
    draining its admitted work. config_snapshot defaults to the
    current system thresholds plus scenario (reproducibility, no secrets).
    """
    from app.experiments.active import get_active_run

    if get_active_run() is not None:
        raise HTTPException(409, "An experiment run is already active")
    coordinator = getattr(request.app.state, "dispatch_coordinator", None)
    if coordinator is not None and coordinator.is_draining:
        raise HTTPException(409, "The previous experiment run is still draining")
    snapshot = body.config_snapshot
    if snapshot is None:
        config = SystemConfigRepository().get_current(db)
        snapshot = {
            "scenario": body.scenario,
            "min_temperature": config.min_temperature if config else None,
            "max_temperature": config.max_temperature if config else None,
            "min_humidity": config.min_humidity if config else None,
            "max_humidity": config.max_humidity if config else None,
        }
    else:
        snapshot = dict(snapshot)
    # Policy comes from server configuration, never from client-provided
    # metadata. Absence is explicit for lightweight apps without BackendConfig.
    backend_config = getattr(request.app.state, "backend_config", None)
    effective = getattr(backend_config, "effective_qos_config", None)
    snapshot["dispatch"] = {
        "processing_version": 2,
        "work_unit": "sensor_reading",
        "wfq_cost": 1,
        "effective_config": effective() if callable(effective) else None,
    }
    snapshot["telemetry_evidence"] = {
        "version": 1,
        "enabled": bool(getattr(backend_config, "telemetry_evidence_enabled", False)),
        "grace_seconds": getattr(backend_config, "telemetry_evidence_grace_s", None),
    }
    snapshot["simulator_sampling_interval_seconds"] = os.getenv("SIMULATOR_SAMPLING_INTERVAL", "10.0")
    snapshot["simulator_random_seed"] = os.getenv("SIMULATOR_RANDOM_SEED")
    snapshot["smtp_enabled"] = os.getenv("SMTP_ENABLED", "").strip().lower() == "true"
    current_thresholds = SystemConfigRepository().get_current(db)
    snapshot["system_thresholds"] = {
        key: getattr(current_thresholds, key) for key in
        ("min_temperature", "max_temperature", "min_humidity", "max_humidity")
    } if current_thresholds is not None else None
    try:
        run = _runs.create(db, scenario=body.scenario, config_snapshot=snapshot)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    from app.experiments.evidence import start_capture
    start_capture(run, backend_config)
    try:
        set_active_run(run.id, run.scenario)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    # Telemetry for the run: launch the run-scoped simulator worker.
    # Warn-only by design (COLDCHAIN_SIM_WORKER_ENABLED controls it):
    # a worker problem never breaks the 201 semantics of the run itself.
    if not start_worker(run.id):
        logger.warning("run %s started without simulator telemetry worker", run.id)
    return _serialize_run(run)


@router.post("/{run_id}/finish", response_model=ExperimentRunResponse)
def finish_run(
    run_id: UUID,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _current=Depends(require_admin),
):
    """Stop admission and the producer, then drain previously accepted work.

    A slow drain returns 202 and continues in the background.
    """
    if not _finish_lock.acquire(blocking=False):
        raise HTTPException(409, "An experiment finish request is already in progress")
    try:
        try:
            return _finish_run_locked(run_id, request, db)
        except HTTPException as exc:
            if exc.status_code == 409 and exc.detail == "Experiment is still draining; retry finish":
                _continue_finish_in_background(run_id, request)
                response.status_code = status.HTTP_202_ACCEPTED
                result = _serialize_run(_runs.get_by_id(db, run_id))
                result.closing = True
                return result
            raise
    finally:
        _finish_lock.release()


def _finish_run_locked(run_id: UUID, request: Request, db: Session):
    from app.experiments.active import get_active_run

    run = _runs.get_by_id(db, run_id)
    if run is None:
        raise HTTPException(404, "Experiment run not found")
    coordinator = getattr(request.app.state, "dispatch_coordinator", None)
    message_queue = getattr(request.app.state, "message_queue", None)
    if run.finished_at is not None:
        return _serialize_run(run)
    active = get_active_run()
    if active is not None and active[0] != run.id:
        raise HTTPException(409, "A different experiment run is active")
    if message_queue is not None and coordinator is None:
        raise HTTPException(409, "Cannot drain transport without a dispatch coordinator")
    # Close the transport boundary first. Messages already claimed by the
    # ingestion worker retain their acceptance and may still be admitted to
    # dispatch, but later arrivals cannot enter this run while the producer is
    # stopping or the reception deadline is being observed.
    from app.experiments import evidence
    if coordinator is not None:
        config = getattr(request.app.state, "backend_config", None)
        timeout = getattr(config, "qos_drain_timeout_s", 30.0)
        try:
            if message_queue is not None:
                message_queue.begin_drain(run.id)
            coordinator.begin_drain(run.id)
        except RuntimeError as exc:
            if message_queue is not None:
                message_queue.end_drain(run.id)
            raise HTTPException(409, str(exc)) from exc
    try:
        managed = evidence.manifest(run.id)
        if managed is not None:
            stop_worker(run.id)
            reception_deadline = evidence.request_close(run.id)
            remaining = (reception_deadline - datetime.now(timezone.utc)).total_seconds()
            if remaining > 0:
                time.sleep(remaining)
    except (OSError, ValueError, TypeError):
        logger.exception("Capture closure failed for run %s; rates remain unavailable", run.id)
    # Keep the run active and its drain guard in place on timeout or DB error.
    stop_worker(run.id)
    deadline = time.monotonic() + timeout if coordinator is not None else None
    ingress_drained = (
        message_queue is None or coordinator is None
        or message_queue.wait_run_ingested(run.id, max(0.0, deadline - time.monotonic()))
    )
    if coordinator is not None and (
        not ingress_drained or not coordinator.wait_until_idle(max(0.0, deadline - time.monotonic()))
    ):
        logger.warning("run %s drain timed out after %ss", run.id, timeout)
        raise HTTPException(409, "Experiment is still draining; retry finish")
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    try:
        evidence.seal_capture(run.id)
    except (OSError, ValueError, TypeError):
        logger.exception("Capture seal failed for run %s", run.id)
    active = get_active_run()
    if active is not None and active[0] == run.id:
        clear_active_run()
    if coordinator is not None:
        coordinator.end_drain()
    if message_queue is not None:
        message_queue.end_drain(run.id)
    return _serialize_run(run)


@router.get("/{run_id}/evidence", response_model=ExperimentEvidenceResponse)
def get_run_evidence(run_id: UUID, db: Session = Depends(get_db)):
    """Measured evidence only; no client paths, imported campaign data or writes."""
    from app.experiments.evidence import report_for_run
    from app.database.infrastructure.models import SensorReadingORM, TrafficClassificationORM
    from app.acquisition.normalizer import NormalizedReading
    from app.classification.application.risk_matrix_evaluator import RiskMatrixEvaluator
    from app.classification.application.priority_assigner import PriorityAssigner

    run = _runs.get_by_id(db, run_id)
    if run is None:
        raise HTTPException(404, "Experiment run not found")
    readings = db.query(SensorReadingORM, TrafficClassificationORM.priority).outerjoin(
        TrafficClassificationORM, TrafficClassificationORM.reading_id == SensorReadingORM.id,
    ).filter(SensorReadingORM.run_id == run_id).all()
    priority_labels = {}
    for reading, priority in readings:
        if priority is not None:
            priority_labels[str(reading.id)] = priority
        elif run.scenario == "WITHOUT_QOS" and reading.sensor_name:
            # Analysis only, on the saved values. Never classify/plan/persist
            # FIFO work or trust a device-provided priority.
            raw = getattr(reading, reading.sensor_name, None)
            if raw is None:
                continue
            try:
                normalized = NormalizedReading(
                    "", "", reading.sensor_name,
                    float(raw == "on") if reading.sensor_name == "energy" else float(raw),
                    reading.timestamp.isoformat(), raw,
                )
                criteria = RiskMatrixEvaluator().evaluate(normalized)
                priority_labels[str(reading.id)] = PriorityAssigner().assign(
                    criteria.impact + criteria.urgency + criteria.risk,
                ).value
            except (TypeError, ValueError):
                continue
    report = report_for_run(run, priority_labels)
    report["counts"]["database_readings_persisted"] = len(readings)
    return report


@router.get("/{run_id}/metrics", response_model=ExperimentMetricListResponse)
def list_run_metrics(
    run_id: UUID,
    metric_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _validate_page(per_page, page)
    if _runs.get_by_id(db, run_id) is None:
        raise HTTPException(404, "Experiment run not found")
    try:
        total, items = _metrics.list(
            db, run_id=run_id, metric_type=metric_type, page=page, per_page=per_page
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ExperimentMetricListResponse(
        total=total,
        page=page,
        per_page=per_page,
        count=len(items),
        results=[_serialize_metric(i) for i in items],
    )


@router.get("/{run_id}/analysis", response_model=ExperimentAnalysisResponse)
def get_run_analysis(
    run_id: UUID,
    max_points: int = Query(300, ge=1, le=500),
    bucket_seconds: float | None = Query(None, ge=0.001, le=1e9, allow_inf_nan=False),
    db: Session = Depends(get_db),
):
    from app.experiments.analysis import analyze_run
    run = _runs.get_by_id(db, run_id)
    if run is None:
        raise HTTPException(404, "Experiment run not found")
    try:
        return analyze_run(db, run, max_points, bucket_seconds)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
