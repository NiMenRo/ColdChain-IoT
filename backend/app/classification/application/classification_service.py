from __future__ import annotations

from datetime import datetime
from typing import Dict
from uuid import uuid4

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification

from .criticality_calculator import CriticalityCalculator, CriticalityLevel
from .priority_assigner import PriorityAssigner, PriorityLevel


class ClassificationService:
    """Orchestrates the classification of an IoT telemetry reading.

    Flow::

        NormalizedReading + Impact + Urgency + Risk
            │
            ▼
        CriticalityCalculator.calculate(I, U, R)  →  criticality score
            │
            ▼
        PriorityAssigner.assign(criticality)       →  PriorityLevel
            │
            ▼
        Queue mapping (HIGH→WFQ, MEDIUM→Round Robin, LOW→FIFO)
            │
            ▼
        TrafficClassification
    """

    # Priority → Queue mapping as defined by the project's prioritization model.
    QUEUE_MAP: Dict[PriorityLevel, str] = {
        PriorityLevel.HIGH: "WFQ",
        PriorityLevel.MEDIUM: "Round Robin",
        PriorityLevel.LOW: "FIFO",
    }

    def __init__(
        self,
        calculator: CriticalityCalculator,
        assigner: PriorityAssigner,
    ) -> None:
        self._calculator = calculator
        self._assigner = assigner

    def classify(
        self,
        reading: NormalizedReading,
        impact: int,
        urgency: int,
        risk: int,
    ) -> TrafficClassification:
        """Classify a telemetry reading and return a ``TrafficClassification``.

        Parameters
        ----------
        reading:
            The normalized sensor reading to classify.
        impact, urgency, risk:
            Integer criteria (1–3) used to compute the criticality score.

        Notes
        -----
        ``reading_id`` is generated with ``uuid4()`` because ``NormalizedReading``
        does not currently expose a unique identifier.  When ``SensorReading`` is
        implemented with a real UUID, this must be replaced with the actual
        reading ID.
        """
        if reading is None:
            raise TypeError("'reading' must be a NormalizedReading instance")

        criticality = self._calculator.calculate(impact, urgency, risk)
        priority = self._assigner.assign(criticality)
        queue = self.QUEUE_MAP[priority]

        # Parse the reading timestamp string into a datetime object.
        reading_timestamp = datetime.fromisoformat(reading.timestamp)

        return TrafficClassification(
            id=uuid4(),
            reading_id=uuid4(),  # TODO: replace with real SensorReading ID
            criticality=criticality,
            priority=priority.value,
            queue=queue,
            classification_time=datetime.now(),
            timestamp=reading_timestamp,
        )
