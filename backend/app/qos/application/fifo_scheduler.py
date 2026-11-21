from __future__ import annotations

from collections import deque
from typing import Deque, Optional

from app.classification import PriorityLevel
from app.qos.application.scheduler import ScheduledItem, Scheduler


class FIFOScheduler(Scheduler):
    """First-In First-Out queue discipline for ``LOW`` priority traffic.

    Processes classified readings in arrival order: the oldest element in the
    queue is the next one dequeued.
    """

    priority = PriorityLevel.LOW

    def __init__(self) -> None:
        self._items: Deque[ScheduledItem] = deque()

    def dequeue(self) -> Optional[ScheduledItem]:
        return self._items.popleft() if self._items else None

    def size(self) -> int:
        return len(self._items)

    def _store(self, item: ScheduledItem) -> None:
        self._items.append(item)
