"""Schemas for experiment runs and common metrics (TSK-059.6)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

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


class EvidenceLatency(BaseModel):
    count: int
    mean: float | None
    p95: float | None


class EvidencePriorityLatency(BaseModel):
    persist: EvidenceLatency
    alert: EvidenceLatency


class ExperimentEvidenceResponse(BaseModel):
    run_id: str
    status: Literal["in_progress", "provisional", "final", "incomplete", "unavailable"]
    reasons: list[str]
    scope: Literal["managed_local_producer"]
    counts: dict[str, int | None]
    pending_messages: int | None
    pdr_percent: float | None
    loss_percent: float | None
    received_payload_bytes: int | None
    payload_goodput_bytes_per_second: float | None
    window: dict | None
    configuration: dict | None
    device_to_persist_ms: EvidenceLatency
    device_to_alert_persist_ms: EvidenceLatency
    by_priority: dict[str, EvidencePriorityLatency]
    clock_unmeasurable: int | None


class AnalysisMetric(BaseModel):
    count: int
    sum: float
    mean: float
    max: float
    latest: float


class AnalysisPoint(BaseModel):
    elapsedMin: float
    value: float
    count: int
    max: float
    start_seconds: float
    end_seconds: float


class ExperimentAnalysisResponse(BaseModel):
    run_id: str
    total_samples: int
    provisional: bool
    max_points: int
    bucket_seconds: float
    metrics: dict[str, AnalysisMetric]
    series: dict[str, list[AnalysisPoint]]
