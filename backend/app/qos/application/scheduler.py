from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Union

from app.classification import PriorityLevel, TrafficClassification
from app.qos.domain.work_item import WorkItem

ScheduledItem = Union[WorkItem, TrafficClassification]


class Scheduler(ABC):
    """Abstract base class for QoS queue disciplines.

    Each concrete scheduler serves exactly one priority level and only ever
    processes classifications whose ``TrafficClassification.priority`` matches
    its assigned priority.  This preserves the traffic separation established
    by the classification module:

    * ``LOW``    -> FIFO
    * ``MEDIUM`` -> Round Robin
    * ``HIGH``   -> WFQ
    """

    priority: PriorityLevel

    def enqueue(self, item: ScheduledItem) -> None:
        """Store an item matching this scheduler's priority.

        ``TrafficClassification`` remains accepted temporarily for the
        `/qos/plan` demonstration endpoint. Runtime scheduling must provide a
        ``WorkItem``; T13 will remove the legacy admission path from pipeline
        processing without changing that isolated demonstration operation.
        """
        self._require_scheduled_item(item)
        self._require_matching_priority(item)
        self._store(item)

    @abstractmethod
    def dequeue(self) -> Optional[ScheduledItem]:
        """Remove and return the next item per this discipline.

        Returns ``None`` when there is nothing left to process.
        """

    def size(self) -> int:
        """Return the number of stored classifications."""
        raise NotImplementedError

    def is_empty(self) -> bool:
        """Return ``True`` when no classifications are stored."""
        return self.size() == 0

    @abstractmethod
    def _store(self, item: ScheduledItem) -> None:
        """Append a validated item to the internal buffer."""

    # -- validation ----------------------------------------------------------

    @staticmethod
    def _require_scheduled_item(item: object) -> None:
        if not isinstance(item, (WorkItem, TrafficClassification)):
            raise TypeError("'item' must be a WorkItem or TrafficClassification instance")

    def _require_matching_priority(self, item: ScheduledItem) -> None:
        priority = item.priority
        if priority != self.priority.value:
            raise ValueError(
                f"priority {priority!r} does not match "
                f"scheduler priority {self.priority.value!r}"
            )
