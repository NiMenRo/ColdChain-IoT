from __future__ import annotations

from math import isfinite
from typing import Dict, List, Mapping, Optional, Tuple

from app.classification import PriorityLevel, TrafficClassification
from app.qos.application.scheduler import ScheduledItem, Scheduler
from app.qos.domain.work_item import WorkItem

FlowId = Tuple[str, str]
Entry = Tuple[float, int, ScheduledItem, FlowId]


class WFQScheduler(Scheduler):
    """Multiflow unit-cost WFQ for HIGH work with stable admission tie breaks."""

    priority = PriorityLevel.HIGH

    def __init__(
        self, weight: float = 1.0, *, flow_weights: Mapping[FlowId, float] | None = None
    ) -> None:
        self._validate_weight(weight)
        self._weight = float(weight)
        self._flow_weights: Dict[FlowId, float] = {}
        for flow, configured_weight in (flow_weights or {}).items():
            self._validate_flow(flow)
            self._validate_weight(configured_weight)
            self._flow_weights[flow] = float(configured_weight)
        self._virtual_time = 0.0
        self._last_finish: Dict[FlowId, float] = {}
        self._items: List[Entry] = []
        self._arrival_counter = 0

    @property
    def weight(self) -> float:
        """Default weight for a flow without an explicit configured weight."""
        return self._weight

    @property
    def virtual_time(self) -> float:
        return self._virtual_time

    @property
    def flow_weights(self) -> Dict[FlowId, float]:
        return dict(self._flow_weights)

    def dequeue(self) -> Optional[ScheduledItem]:
        if not self._items:
            return None
        index, (_, _, item, flow) = min(
            enumerate(self._items), key=lambda candidate: candidate[1][:2]
        )
        active_weights = sum(
            self._weight_for(active_flow) for active_flow in {entry[3] for entry in self._items}
        )
        del self._items[index]
        # A unit service opportunity advances the local GPS reference by its
        # fair share among flows that were active before this selection.
        self._virtual_time += 1.0 / active_weights
        if not any(entry[3] == flow for entry in self._items):
            self._last_finish.pop(flow, None)
        return item

    def size(self) -> int:
        return len(self._items)

    def _store(self, item: ScheduledItem) -> None:
        flow = self._flow_for(item)
        start = max(self._last_finish.get(flow, 0.0), self._virtual_time)
        finish = start + 1.0 / self._weight_for(flow)
        self._last_finish[flow] = finish
        self._items.append((finish, self._arrival_counter, item, flow))
        self._arrival_counter += 1

    def _weight_for(self, flow: FlowId) -> float:
        return self._flow_weights.get(flow, self._weight)

    @staticmethod
    def _flow_for(item: ScheduledItem) -> FlowId:
        if isinstance(item, WorkItem):
            return item.flow_id
        if isinstance(item, TrafficClassification):
            return "__legacy__", str(item.reading_id)
        raise TypeError("'item' must be a WorkItem or TrafficClassification instance")

    @staticmethod
    def _validate_flow(flow: object) -> None:
        if (
            not isinstance(flow, tuple) or len(flow) != 2
            or not all(isinstance(part, str) and part for part in flow)
        ):
            raise ValueError("flow weight keys must be (device_code, sensor_name)")

    @staticmethod
    def _validate_weight(weight: object) -> None:
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise TypeError("'weight' must be numeric")
        if not isfinite(weight) or weight <= 0:
            raise ValueError("'weight' must be finite and greater than zero")
