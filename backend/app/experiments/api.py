"""REST API for experiment runs and common metrics (TSK-059.6/059.7).

Reads are authenticated; starting/finishing a run is admin-only.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
)
from app.security.dependencies import require_admin

router = APIRouter(
    prefix="/experiment-runs", tags=["experiments"], dependencies=[Depends(authenticated)]
)
logger = logging.getLogger(__name__)
_runs = ExperimentRunRepository()
_metrics = ExperimentMetricRepository()
_finish_lock = threading.Lock()


def _validate_page(per_page: int, page: int):
    if page < 1:
        raise HTTPException(400, "page must be >=1")
    if not 1 <= per_page <= 100:
        raise HTTPException(400, "per_page must be 1..100")


def _serialize_run(run) -> ExperimentRunResponse:
    return ExperimentRunResponse(
        id=str(run.id),
        scenario=run.scenario,
        started_at=run.started_at,
        finished_at=run.finished_at,
        config_snapshot=run.config_snapshot,
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
    try:
        run = _runs.create(db, scenario=body.scenario, config_snapshot=snapshot)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
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
    db: Session = Depends(get_db),
    _current=Depends(require_admin),
):
    """Close a run (sets finished_at), stop its producer and drain its work.

    A timeout returns 409 without closing the run or releasing its drain guard;
    a later request can retry after admitted work has finished.
    """
    if not _finish_lock.acquire(blocking=False):
        raise HTTPException(409, "An experiment finish request is already in progress")
    try:
        return _finish_run_locked(run_id, request, db)
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
    active = get_active_run()
    if active is not None and active[0] == run.id:
        clear_active_run()
    if coordinator is not None:
        coordinator.end_drain()
    if message_queue is not None:
        message_queue.end_drain(run.id)
    return _serialize_run(run)


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
