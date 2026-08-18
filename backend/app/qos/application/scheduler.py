from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.classification import PriorityLevel, TrafficClassification


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

    def enqueue(self, classification: TrafficClassification) -> None:
        """Store a classification matching this scheduler's priority."""
        self._require_classification(classification)
        self._require_matching_priority(classification)
        self._store(classification)

    @abstractmethod
    def dequeue(self) -> Optional[TrafficClassification]:
        """Remove and return the next classification per this discipline.

        Returns ``None`` when there is nothing left to process.
        """

    def size(self) -> int:
        """Return the number of stored classifications."""
        raise NotImplementedError

    def is_empty(self) -> bool:
        """Return ``True`` when no classifications are stored."""
        return self.size() == 0

    @abstractmethod
    def _store(self, classification: TrafficClassification) -> None:
        """Append a validated classification to the internal buffer."""

    # -- validation ----------------------------------------------------------

    @staticmethod
    def _require_classification(classification: object) -> None:
        if not isinstance(classification, TrafficClassification):
            raise TypeError("'classification' must be a TrafficClassification instance")

    def _require_matching_priority(self, classification: TrafficClassification) -> None:
        if classification.priority != self.priority.value:
            raise ValueError(
                f"priority {classification.priority!r} does not match "
                f"scheduler priority {self.priority.value!r}"
            )