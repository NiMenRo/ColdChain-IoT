from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, validator

from app.classification.domain import TrafficClassification
from app.qos.application.qos_metrics_service import MessageDeliveryRecord, QoSMetricsService
from app.qos.application.traffic_planning_service import TrafficPlanningService

router = APIRouter(prefix="/qos", tags=["qos"])

__all__ = ["router"]


class TrafficClassificationRequest(BaseModel):
    id: str
    reading_id: str
    criticality: float = Field(..., gt=0)
    priority: str
    queue: str
    classification_time: str
    timestamp: str

    @validator("id", "reading_id")
    def validate_uuid(cls, value: str) -> str:
        try:
            UUID(value)
        except ValueError as exc:
            raise ValueError("id and reading_id must be valid UUID strings") from exc
        return value

    @validator("priority")
    def validate_priority(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"low", "medium", "high"}:
            raise ValueError("priority must be low, medium, or high")
        return normalized

    @validator("classification_time", "timestamp")
    def validate_datetime(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("timestamps must be ISO-8601 strings") from exc
        return value


class DeliveryRecordRequest(BaseModel):
    message_id: str
    sent_at: datetime
    received_at: datetime
    size_bytes: float = Field(0.0, ge=0)
    delivered: bool = True
    criticality: Optional[float] = None
    priority: Optional[str] = None

    @validator("priority")
    def validate_priority(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.lower()
        if normalized not in {"low", "medium", "high"}:
            raise ValueError("priority must be low, medium, or high")
        return normalized


class PlanningResponse(BaseModel):
    id: str
    reading_id: str
    criticality: float
    priority: str
    queue: str
    classification_time: str
    timestamp: str
    planned_queue: str


@router.post("/plan", response_model=PlanningResponse, status_code=status.HTTP_202_ACCEPTED)
def plan_classification(request: TrafficClassificationRequest, request_obj: Request):
    try:
        classification = TrafficClassification(
            id=UUID(request.id),
            reading_id=UUID(request.reading_id),
            criticality=request.criticality,
            priority=request.priority,
            queue=request.queue,
            classification_time=datetime.fromisoformat(request.classification_time),
            timestamp=datetime.fromisoformat(request.timestamp),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid TrafficClassification payload: {exc}") from exc

    service: TrafficPlanningService = getattr(request_obj.app.state, "qos_service", TrafficPlanningService())
    try:
        planned = service.plan(classification)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    records = getattr(request_obj.app.state, "qos_records", [])
    records.append(
        MessageDeliveryRecord(
            message_id=str(planned.id),
            sent_at=planned.timestamp,
            received_at=planned.classification_time,
            size_bytes=128.0,
            delivered=True,
            criticality=planned.criticality,
            priority=planned.priority,
        )
    )

    return PlanningResponse(
        id=str(planned.id),
        reading_id=str(planned.reading_id),
        criticality=planned.criticality,
        priority=planned.priority,
        queue=planned.queue,
        classification_time=planned.classification_time.isoformat(timespec="seconds"),
        timestamp=planned.timestamp.isoformat(timespec="seconds"),
        planned_queue=planned.queue,
    )


@router.get("/queues")
def get_queues(request: Request):
    service: TrafficPlanningService = getattr(request.app.state, "qos_service", TrafficPlanningService())
    priorities = ["low", "medium", "high"]
    snapshot: dict[str, list[dict[str, Any]]] = {}
    for priority in priorities:
        items = service.get_queue(priority)
        snapshot[priority] = [
            {
                "id": str(item.id),
                "reading_id": str(item.reading_id),
                "criticality": item.criticality,
                "priority": item.priority,
                "queue": item.queue,
                "timestamp": item.timestamp.isoformat(timespec="seconds"),
            }
            for item in items
        ]
    return {"count": sum(len(items) for items in snapshot.values()), "queues": snapshot}


@router.get("/metrics")
def get_metrics(request: Request):
    metrics_service: QoSMetricsService = getattr(request.app.state, "qos_metrics_service", QoSMetricsService())
    records = getattr(request.app.state, "qos_records", [])
    if not records:
        return {"count": 0, "summary": {"latency": 0.0, "jitter": 0.0, "throughput": 0.0, "pdr": 0.0, "packet_loss": 0.0}, "by_priority": {}}

    summary = metrics_service.summarize(records, include_priority_summary=False)
    by_priority = metrics_service.summarize_by_priority(records)
    return {"count": len(records), "summary": summary, "by_priority": by_priority}


@router.post("/metrics/calculate")
def calculate_metrics(body: list[DeliveryRecordRequest], request: Request):
    if not body:
        raise HTTPException(status_code=400, detail="At least one delivery record is required")

    metrics_service: QoSMetricsService = getattr(request.app.state, "qos_metrics_service", QoSMetricsService())
    records = [
        MessageDeliveryRecord(
            message_id=item.message_id,
            sent_at=item.sent_at,
            received_at=item.received_at,
            size_bytes=item.size_bytes,
            delivered=item.delivered,
            criticality=item.criticality,
            priority=item.priority,
        )
        for item in body
    ]
    return {
        "count": len(records),
        "summary": metrics_service.summarize(records, include_priority_summary=False),
        "by_priority": metrics_service.summarize_by_priority(records),
    }
