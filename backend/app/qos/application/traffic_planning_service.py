from __future__ import annotations

from typing import Iterable, List, Optional, Union

from app.classification import PriorityLevel, TrafficClassification
from app.qos.application.fifo_scheduler import FIFOScheduler
from app.qos.application.round_robin_scheduler import RoundRobinScheduler
from app.qos.application.wfq_scheduler import WFQScheduler
from app.qos.application.scheduler import ScheduledItem
from app.qos.domain.work_item import WorkItem


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

    def plan(self, item: ScheduledItem) -> ScheduledItem:
        """Queue one work item using its already assigned priority.

        The classification-only branch is retained solely for the explicit
        demonstration API until T20 separates that API's backing storage.
        """
        self._require_scheduled_item(item)
        priority = self._normalize_priority(item.priority)

        if priority is PriorityLevel.LOW:
            self._fifo_scheduler.enqueue(item)
        elif priority is PriorityLevel.MEDIUM:
            self._round_robin_scheduler.enqueue(item)
        elif priority is PriorityLevel.HIGH:
            self._wfq_scheduler.enqueue(item)
        else:
            raise ValueError(f"Unsupported priority for planning: {item.priority!r}")

        return item

    def plan_many(self, items: Iterable[ScheduledItem]) -> List[ScheduledItem]:
        planned: List[ScheduledItem] = []
        for item in items:
            planned.append(self.plan(item))
        return planned

    def dequeue(self, priority: Union[str, PriorityLevel]) -> Optional[ScheduledItem]:
        scheduler = self._scheduler_for(priority)
        return scheduler.dequeue()

    def get_queue(self, priority: Union[str, PriorityLevel]) -> List[ScheduledItem]:
        scheduler = self._scheduler_for(priority)
        if isinstance(scheduler, FIFOScheduler):
            return list(scheduler._items)
        if isinstance(scheduler, RoundRobinScheduler):
            items: List[ScheduledItem] = []
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
    def _require_scheduled_item(item: object) -> None:
        if not isinstance(item, (WorkItem, TrafficClassification)):
            raise TypeError("'item' must be a WorkItem or TrafficClassification instance")

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
