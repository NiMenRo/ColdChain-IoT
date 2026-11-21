from __future__ import annotations

from fractions import Fraction
from math import isfinite
from typing import List, Mapping, Optional, Tuple

from app.classification import PriorityLevel, TrafficClassification
from app.qos.application.scheduler import ScheduledItem, Scheduler
from app.qos.domain.work_item import WorkItem

DEFAULT_BAND_WEIGHTS = {"H7": 1.0, "H8": 2.0, "H9": 3.0}
Entry = Tuple[Fraction, int, ScheduledItem, str]


class WFQScheduler(Scheduler):
    """Unit-cost WFQ between HIGH criticality bands, FIFO within each band.

    Virtual time follows a fluid GPS server, including flow exhaustion within
    a service opportunity. GPS activity must not be inferred from packet queues.
    """

    priority = PriorityLevel.HIGH

    def __init__(
        self, *, band_weights: Mapping[str, float] | None = None
    ) -> None:
        weights = dict(DEFAULT_BAND_WEIGHTS if band_weights is None else band_weights)
        if set(weights) != set(DEFAULT_BAND_WEIGHTS):
            raise ValueError("band_weights must define exactly H7, H8 and H9")
        self._weights: dict[str, Fraction] = {}
        for band, configured_weight in weights.items():
            self._validate_weight(configured_weight)
            self._weights[band] = Fraction(str(configured_weight))
        self._virtual_time = Fraction()
        self._last_finish: dict[str, Fraction] = {}
        self._items: List[Entry] = []
        self._arrival_counter = 0

    @property
    def virtual_time(self) -> float:
        return float(self._virtual_time)

    @property
    def band_weights(self) -> dict[str, float]:
        return {band: float(weight) for band, weight in self._weights.items()}

    def dequeue(self) -> Optional[ScheduledItem]:
        if not self._items:
            return None
        index, (_, _, item, _band) = min(
            enumerate(self._items), key=lambda candidate: candidate[1][:2]
        )
        del self._items[index]
        self._advance_gps()
        return item

    def size(self) -> int:
        return len(self._items)

    def _store(self, item: ScheduledItem) -> None:
        band = self.band_for(item)
        start = max(self._last_finish.get(band, Fraction()), self._virtual_time)
        finish = start + 1 / self._weights[band]
        self._last_finish[band] = finish
        self._items.append((finish, self._arrival_counter, item, band))
        self._arrival_counter += 1

    def _advance_gps(self) -> None:
        remaining = Fraction(1)
        while remaining:
            active = {
                band: finish for band, finish in self._last_finish.items()
                if finish > self._virtual_time
            }
            if not active:
                return
            total_weight = sum(self._weights[band] for band in active)
            next_finish = min(active.values())
            cost = (next_finish - self._virtual_time) * total_weight
            if cost <= remaining:
                self._virtual_time = next_finish
                remaining -= cost
            else:
                self._virtual_time += remaining / total_weight
                return

    @staticmethod
    def band_for(item: ScheduledItem) -> str:
        if isinstance(item, WorkItem):
            criticality = item.classification.criticality if item.classification else None
        elif isinstance(item, TrafficClassification):
            criticality = item.criticality
        else:
            raise TypeError("'item' must be a WorkItem or TrafficClassification instance")
        if (
            isinstance(criticality, bool) or not isinstance(criticality, (int, float))
            or not isfinite(criticality) or not 7 <= criticality <= 9
        ):
            raise ValueError("HIGH WFQ requires criticality in [7, 9]")
        return "H7" if criticality < 8 else "H8" if criticality < 9 else "H9"

    @staticmethod
    def _validate_weight(weight: object) -> None:
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise TypeError("'weight' must be numeric")
        if not isfinite(weight) or weight <= 0:
            raise ValueError("'weight' must be finite and greater than zero")
