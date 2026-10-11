"""Schemas for experiment runs and common metrics (TSK-059.6)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ExperimentRunResponse(BaseModel):
    id: str
    scenario: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    config_snapshot: Optional[str] = None


class ExperimentRunListResponse(BaseModel):
    total: int
    page: int
    per_page: int
    count: int
    results: list[ExperimentRunResponse]


class ExperimentMetricResponse(BaseModel):
    id: str
    run_id: str
    metric_type: str
    value: float
    timestamp: datetime


class ExperimentMetricListResponse(BaseModel):
    total: int
    page: int
    per_page: int
    count: int
    results: list[ExperimentMetricResponse]
