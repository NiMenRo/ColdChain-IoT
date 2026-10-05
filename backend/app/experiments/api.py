"""Read-only REST query API for experiment runs and common metrics (TSK-059.6)."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.authorization import authenticated
from app.database.infrastructure.repositories import (
    ExperimentMetricRepository,
    ExperimentRunRepository,
)
from app.database.infrastructure.session import get_db
from app.experiments.schemas import (
    ExperimentMetricListResponse,
    ExperimentMetricResponse,
    ExperimentRunListResponse,
    ExperimentRunResponse,
)

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
