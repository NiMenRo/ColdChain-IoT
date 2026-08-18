from __future__ import annotations

from typing import Iterable, List, Optional, Union

from app.classification import PriorityLevel, TrafficClassification
from app.qos.application.fifo_scheduler import FIFOScheduler
from app.qos.application.round_robin_scheduler import RoundRobinScheduler
from app.qos.application.wfq_scheduler import WFQScheduler


class TrafficPlanningService:
    """Routes classified traffic to the correct QoS queue.

    The service does not reclassify messages. It uses the priority already assigned
    by the classification module and sends each ``TrafficClassification`` to the
    matching scheduler: low -> FIFO, medium -> Round Robin, high -> WFQ.
    """

    def __init__(
        self,
        fifo_scheduler: Optional[FIFOScheduler] = None,
        round_robin_scheduler: Optional[RoundRobinScheduler] = None,
        wfq_scheduler: Optional[WFQScheduler] = None,
    ) -> None:
        self._fifo_scheduler = fifo_scheduler or FIFOScheduler()
        self._round_robin_scheduler = round_robin_scheduler or RoundRobinScheduler()
        self._wfq_scheduler = wfq_scheduler or WFQScheduler()

    @property
    def fifo(self) -> FIFOScheduler:
        return self._fifo_scheduler

    @property
    def round_robin(self) -> RoundRobinScheduler:
        return self._round_robin_scheduler

    @property
    def wfq(self) -> WFQScheduler:
        return self._wfq_scheduler

    def plan(self, classification: TrafficClassification) -> TrafficClassification:
        """Queue a classification using the strategy corresponding to its priority."""
        self._require_classification(classification)
        priority = self._normalize_priority(classification.priority)

        if priority is PriorityLevel.LOW:
            self._fifo_scheduler.enqueue(classification)
        elif priority is PriorityLevel.MEDIUM:
            self._round_robin_scheduler.enqueue(classification)
        elif priority is PriorityLevel.HIGH:
            self._wfq_scheduler.enqueue(classification)
        else:
            raise ValueError(f"Unsupported priority for planning: {classification.priority!r}")

        return classification

    def plan_many(self, classifications: Iterable[TrafficClassification]) -> List[TrafficClassification]:
        planned: List[TrafficClassification] = []
        for classification in classifications:
            planned.append(self.plan(classification))
        return planned

    def dequeue(self, priority: Union[str, PriorityLevel]) -> Optional[TrafficClassification]:
        scheduler = self._scheduler_for(priority)
        return scheduler.dequeue()

    def get_queue(self, priority: Union[str, PriorityLevel]) -> List[TrafficClassification]:
        scheduler = self._scheduler_for(priority)
        if isinstance(scheduler, FIFOScheduler):
            return list(scheduler._items)
        if isinstance(scheduler, RoundRobinScheduler):
            items: List[TrafficClassification] = []
            for slot in scheduler._slots.values():
                items.extend(slot)
            return items
        if isinstance(scheduler, WFQScheduler):
            return [entry[2] for entry in scheduler._items]
        raise TypeError(f"Unsupported scheduler type: {type(scheduler).__name__}")

    def is_empty(self, priority: Union[str, PriorityLevel]) -> bool:
        scheduler = self._scheduler_for(priority)
        return scheduler.is_empty()

    def size(self, priority: Union[str, PriorityLevel]) -> int:
        scheduler = self._scheduler_for(priority)
        return scheduler.size()

    def _scheduler_for(self, priority: Union[str, PriorityLevel]):
        normalized = self._normalize_priority(priority)
        if normalized is PriorityLevel.LOW:
            return self._fifo_scheduler
        if normalized is PriorityLevel.MEDIUM:
            return self._round_robin_scheduler
        if normalized is PriorityLevel.HIGH:
            return self._wfq_scheduler
        raise ValueError(f"Unsupported priority: {priority!r}")

    @staticmethod
    def _require_classification(classification: object) -> None:
        if not isinstance(classification, TrafficClassification):
            raise TypeError("'classification' must be a TrafficClassification instance")

    @staticmethod
    def _normalize_priority(priority: Union[str, PriorityLevel]) -> PriorityLevel:
        if isinstance(priority, PriorityLevel):
            return priority
        if isinstance(priority, str):
            try:
                return PriorityLevel(priority.lower())
            except ValueError as exc:
                raise ValueError(f"Unsupported priority: {priority!r}") from exc
        raise TypeError("'priority' must be a PriorityLevel or string")
