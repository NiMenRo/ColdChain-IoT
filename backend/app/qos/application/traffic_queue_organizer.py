from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional

from app.classification import PriorityLevel, TrafficClassification


class TrafficQueueOrganizer:
    """Organizes ``TrafficClassification`` objects into per-priority queues.

    Each classification is routed to one of three independent queues based
    exclusively on ``TrafficClassification.priority`` (``high``, ``medium``,
    ``low``).  The queues use ``collections.deque`` and preserve arrival order
    (FIFO base), mirroring the ``MessageQueue`` convention.

    The queue disciplines (FIFO, Round Robin, WFQ) are not implemented here;
    this component only organizes and temporarily holds the classifications so
    that the QoS planning algorithms can consume them later through ``pop``.
    """

    def __init__(self) -> None:
        self._queues: Dict[str, Deque[TrafficClassification]] = {
            PriorityLevel.HIGH.value: deque(),
            PriorityLevel.MEDIUM.value: deque(),
            PriorityLevel.LOW.value: deque(),
        }

    def enqueue(self, classification: TrafficClassification) -> None:
        """Add a classification to the queue matching its priority."""
        self._require_classification(classification)
        queue = self._queue_for(classification.priority)
        queue.append(classification)

    def get_queue(self, priority: str) -> List[TrafficClassification]:
        """Return a snapshot of a queue without modifying it."""
        return list(self._queue_for(priority))

    def queue_length(self, priority: str) -> int:
        """Return the number of classifications stored in one queue."""
        return len(self._queue_for(priority))

    def is_empty(self, priority: str) -> bool:
        """Return ``True`` if the given queue has no elements."""
        return not self._queue_for(priority)

    def total_count(self) -> int:
        """Return the total number of classifications across all queues."""
        return sum(len(queue) for queue in self._queues.values())

    def pop(self, priority: str) -> Optional[TrafficClassification]:
        """Remove and return the oldest classification of a queue (FIFO).

        Returns ``None`` when the queue is empty.
        """
        queue = self._queue_for(priority)
        return queue.popleft() if queue else None

    def peek(self, priority: str) -> Optional[TrafficClassification]:
        """Return the oldest classification of a queue without removing it.

        Returns ``None`` when the queue is empty.
        """
        queue = self._queue_for(priority)
        return queue[0] if queue else None

    # -- helpers / validation -------------------------------------------------

    @staticmethod
    def _require_classification(classification: object) -> None:
        if not isinstance(classification, TrafficClassification):
            raise TypeError("'classification' must be a TrafficClassification instance")

    def _queue_for(self, priority: str) -> Deque[TrafficClassification]:
        key = self._priority_key(priority)
        return self._queues[key]

    @staticmethod
    def _priority_key(priority: object) -> str:
        try:
            return PriorityLevel(priority).value
        except ValueError:
            raise ValueError(f"Unsupported priority: {priority!r}")