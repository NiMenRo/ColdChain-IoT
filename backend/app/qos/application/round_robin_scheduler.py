from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from app.classification import PriorityLevel, TrafficClassification
from app.qos.application.scheduler import ScheduledItem, Scheduler
from app.qos.domain.work_item import WorkItem

FlowId = Tuple[str, str]


class RoundRobinScheduler(Scheduler):
    """Quantum-one Round Robin for MEDIUM work, rotating active sensor flows."""

    priority = PriorityLevel.MEDIUM

    def __init__(self) -> None:
        self._slots: Dict[FlowId, Deque[ScheduledItem]] = {}
        self._flow_order: Deque[FlowId] = deque()
        self.rounds: int = 0

    @property
    def slot_names(self) -> List[FlowId]:
        """Active flows in their next-service rotation order."""
        return list(self._flow_order)

    def dequeue(self) -> Optional[ScheduledItem]:
        if not self._flow_order:
            return None

        flow = self._flow_order.popleft()
        queue = self._slots[flow]
        item = queue.popleft()
        if queue:
            # One quantum: an active flow returns at the tail only after its
            # head has been selected. New flows are also appended at the tail.
            self._flow_order.append(flow)
        else:
            del self._slots[flow]
        if not self._flow_order:
            self.rounds += 1
        return item

    def size(self) -> int:
        return sum(len(slot) for slot in self._slots.values())

    def _store(self, item: ScheduledItem) -> None:
        flow = self._flow_for(item)
        queue = self._slots.get(flow)
        if queue is None:
            queue = self._slots[flow] = deque()
            self._flow_order.append(flow)
        queue.append(item)

    @staticmethod
    def _flow_for(item: ScheduledItem) -> FlowId:
        if isinstance(item, WorkItem):
            return item.flow_id
        # Classification-only planning is a legacy API demonstration. It must
        # not create the old shared production "default" flow.
        if isinstance(item, TrafficClassification):
            return "__legacy__", str(item.reading_id)
        raise TypeError("'item' must be a WorkItem or TrafficClassification instance")
