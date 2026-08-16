from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
import logging

from .application.classification_service import ClassificationService
from .application.criticality_calculator import CriticalityCalculator
from .application.priority_assigner import PriorityAssigner
from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/classification", tags=["classification"])


class NormalizedReadingModel(BaseModel):
    device_code: str
    device_type: str
    sensor_name: str
    value: float
    timestamp: str
    raw_value: Optional[float]

    @validator("timestamp")
    def valid_timestamp(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v)
        except Exception:
            raise ValueError("timestamp must be ISO-8601 string")
        return v


class ClassificationRequest(BaseModel):
    reading: NormalizedReadingModel
    impact: Optional[int] = Field(2, ge=1, le=3)
    urgency: Optional[int] = Field(2, ge=1, le=3)
    risk: Optional[int] = Field(2, ge=1, le=3)


class ClassificationResponse(BaseModel):
    id: str
    reading_id: str
    criticality: float
    priority: str
    queue: str
    classification_time: str
    timestamp: str


@router.post("/classify", response_model=ClassificationResponse)
def classify_reading(request: ClassificationRequest):
    # Build NormalizedReading dataclass expected by service
    reading_model = request.reading
    try:
        normalized = NormalizedReading(
            device_code=reading_model.device_code,
            device_type=reading_model.device_type,
            sensor_name=reading_model.sensor_name,
            value=reading_model.value,
            timestamp=reading_model.timestamp,
            raw_value=reading_model.raw_value if reading_model.raw_value is not None else reading_model.value,
        )
    except Exception as exc:
        logger.exception("Failed to construct NormalizedReading")
        raise HTTPException(status_code=400, detail=str(exc))

    # Instantiate service
    calculator = CriticalityCalculator()
    assigner = PriorityAssigner()
    service = ClassificationService(calculator=calculator, assigner=assigner)

    try:
        classification: TrafficClassification = service.classify(
            reading=normalized,
            impact=request.impact,
            urgency=request.urgency,
            risk=request.risk,
        )
    except Exception as exc:
        logger.exception("Classification failed")
        raise HTTPException(status_code=400, detail=str(exc))

    # Prepare response
    response = ClassificationResponse(
        id=str(classification.id),
        reading_id=str(classification.reading_id),
        criticality=classification.criticality,
        priority=classification.priority,
        queue=classification.queue,
        classification_time=classification.classification_time.isoformat(timespec="seconds"),
        timestamp=classification.timestamp.isoformat(timespec="seconds"),
    )

    return response
