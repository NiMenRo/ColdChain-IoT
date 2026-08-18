from __future__ import annotations

from typing import List, Optional, Tuple

from app.classification import PriorityLevel, TrafficClassification
from app.qos.application.scheduler import Scheduler

Entry = Tuple[float, float, TrafficClassification]


class WFQScheduler(Scheduler):
    """Weighted Fair Queueing discipline for ``HIGH`` priority traffic.

    Processes the ``HIGH`` flow using virtual-time based WFQ accounting:

    * on arrival, an entry receives ``start = max(virtual_time, last_finish)``
      and ``finish = start + weight``;
    * on ``dequeue``, the pending entry with the smallest ``finish`` is served
      and the virtual clock advances to that finish time.

    The ``weight`` is a single per-scheduler coefficient applied to the whole
    ``HIGH`` flow, defaulting to ``1.0`` (neutral).  No per-reading weighting
    is applied: the priority was already determined by the classification
    module, so readings are not re-weighted individually here.
    """

    priority = PriorityLevel.HIGH

    def __init__(self, weight: float = 1.0) -> None:
        self._validate_weight(weight)
        self._weight = weight
        self._virtual_time: float = 0.0
        self._last_finish: float = 0.0
        self._items: List[Entry] = []

    @property
    def weight(self) -> float:
        """Return the weight coefficient applied to the ``HIGH`` flow."""
        return self._weight

    @property
    def virtual_time(self) -> float:
        """Return the current virtual clock value."""
        return self._virtual_time

    def dequeue(self) -> Optional[TrafficClassification]:
        if not self._items:
            return None
        index, (_, finish, classification) = min(
            enumerate(self._items), key=lambda entry: entry[1][1]
        )
        del self._items[index]
        self._virtual_time = finish
        return classification

    def size(self) -> int:
        return len(self._items)

    def _store(self, classification: TrafficClassification) -> None:
        start = max(self._virtual_time, self._last_finish)
        finish = start + self._weight
        self._last_finish = finish
        self._items.append((start, finish, classification))

    @staticmethod
    def _validate_weight(weight: object) -> None:
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise TypeError("'weight' must be numeric")
        if weight <= 0:
            raise ValueError("'weight' must be greater than zero")