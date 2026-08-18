from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional

from app.classification import PriorityLevel, TrafficClassification
from app.qos.application.scheduler import Scheduler

DEFAULT_SLOT = "default"


class RoundRobinScheduler(Scheduler):
    """Round Robin queue discipline for ``MEDIUM`` priority traffic.

    Services its sub-queues (slots) in cyclic order, taking one element per
    slot per rotation round.  Classification-based traffic currently arrives
    into a single slot, so the observable behavior matches arrival order;
    the cyclic rotation mechanism is kept prepared for a future scheduling
    policy that defines additional slots.  Empty slots are skipped.
    """

    priority = PriorityLevel.MEDIUM

    def __init__(self) -> None:
        self._slots: Dict[str, Deque[TrafficClassification]] = {
            DEFAULT_SLOT: deque()
        }
        self._slot_names: List[str] = [DEFAULT_SLOT]
        self._cursor: int = 0
        self.rounds: int = 0

    @property
    def slot_names(self) -> List[str]:
        """Return the names of the sub-queues the scheduler rotates over."""
        return list(self._slot_names)

    def dequeue(self) -> Optional[TrafficClassification]:
        for _ in range(len(self._slot_names)):
            slot = self._slots[self._slot_names[self._cursor]]
            if slot:
                popped = slot.popleft()
                self._advance_cursor()
                return popped
        return None

    def size(self) -> int:
        return sum(len(slot) for slot in self._slots.values())

    def _store(self, classification: TrafficClassification) -> None:
        self._slots[DEFAULT_SLOT].append(classification)

    def _advance_cursor(self) -> None:
        self._cursor = (self._cursor + 1) % len(self._slot_names)
        if self._cursor == 0:
            self.rounds += 1