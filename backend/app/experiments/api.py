"""REST API for experiment runs and common metrics (TSK-059.6/059.7).

Reads are authenticated; starting/finishing a run is admin-only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
_runs = ExperimentRunRepository()
_metrics = ExperimentMetricRepository()


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
    db: Session = Depends(get_db),
    _current=Depends(require_admin),
):
    """Start an experiment run and mark it active for the pipeline worker.

    409 when another run is already active. config_snapshot defaults to the
    current system thresholds plus scenario (reproducibility, no secrets).
    """
    from app.experiments.active import get_active_run

    if get_active_run() is not None:
        raise HTTPException(409, "An experiment run is already active")
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
    try:
        run = _runs.create(db, scenario=body.scenario, config_snapshot=snapshot)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    try:
        set_active_run(run.id, run.scenario)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _serialize_run(run)


@router.post("/{run_id}/finish", response_model=ExperimentRunResponse)
def finish_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    _current=Depends(require_admin),
):
    """Close a run (sets finished_at) and release it when active."""
    from app.experiments.active import get_active_run

    run = _runs.get_by_id(db, run_id)
    if run is None:
        raise HTTPException(404, "Experiment run not found")
    run.finished_at = datetime.now(timezone.utc)
    db.flush()
    db.commit()
    active = get_active_run()
    if active is not None and active[0] == run.id:
        clear_active_run()
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
