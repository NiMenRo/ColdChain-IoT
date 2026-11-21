"""Deterministic inter-class arbitration; it selects but never processes I/O."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Iterable, Optional
from uuid import UUID

from app.classification import PriorityLevel
from app.qos.application.scheduler import ScheduledItem
from app.qos.application.traffic_planning_service import TrafficPlanningService
from app.qos.application.wfq_scheduler import WFQScheduler
from app.qos.domain.work_item import WorkItem


class QoSDispatcher:
    """Persistent weighted cycle, skipping empty classes without idling."""

    def __init__(
        self, planner: TrafficPlanningService, *, high_quota: int = 4,
        medium_quota: int = 2, low_quota: int = 1,
    ) -> None:
        if not isinstance(planner, TrafficPlanningService):
            raise TypeError("'planner' must be a TrafficPlanningService")
        quotas = (high_quota, medium_quota, low_quota)
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in quotas):
            raise ValueError("dispatcher quotas must be positive integers")
        self._planner = planner
        self._cycle = (
            [PriorityLevel.HIGH] * high_quota
            + [PriorityLevel.MEDIUM] * medium_quota
            + [PriorityLevel.LOW] * low_quota
        )
        self._cursor = 0

    @property
    def cycle(self) -> tuple[PriorityLevel, ...]:
        return tuple(self._cycle)

    def select_next(self) -> Optional[ScheduledItem]:
        """Return a selected item, skipping empty opportunities atomically."""
        for _ in self._cycle:
            priority = self._cycle[self._cursor]
            self._cursor = (self._cursor + 1) % len(self._cycle)
            item = self._planner.dequeue(priority)
            if item is not None:
                return item
        # No pending work: restart from HIGH when the system becomes nonempty.
        self._cursor = 0
        return None


class DispatchCoordinator:
    """Thread-safe admission and selection boundary for the attention worker.

    The coordinator owns the only lock that touches pending work, scheduler
    state and counters.  It never performs SQL, notifications or other I/O
    while holding that lock, so an attention that is already running cannot
    block new admissions for the duration of a database commit.

    ``WITH_QOS`` work goes through the weighted 4:2:1 dispatcher.  Work received
    under ``WITHOUT_QOS`` has no priority and is kept in a plain FIFO reference
    queue instead of inventing one.
    """

    def __init__(
        self,
        planner: TrafficPlanningService,
        *,
        dispatcher: QoSDispatcher | None = None,
        capacity: int = 3000,
        high_quota: int = 4,
        medium_quota: int = 2,
        low_quota: int = 1,
        failure_capacity: int = 100,
    ) -> None:
        if not isinstance(planner, TrafficPlanningService):
            raise TypeError("'planner' must be a TrafficPlanningService")
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
            raise ValueError("'capacity' must be a positive integer")
        if isinstance(failure_capacity, bool) or not isinstance(failure_capacity, int) or failure_capacity <= 0:
            raise ValueError("'failure_capacity' must be a positive integer")
        self._planner = planner
        self._dispatcher = dispatcher or QoSDispatcher(
            planner,
            high_quota=high_quota,
            medium_quota=medium_quota,
            low_quota=low_quota,
        )
        self._capacity = capacity
        self._condition = threading.Condition()
        self._without_qos: deque[WorkItem] = deque()
        self._recent_failures: deque[dict] = deque(maxlen=failure_capacity)
        self._selected_item: WorkItem | None = None
        self._pending = 0
        self._in_flight = 0
        self._admitted = 0
        self._rejected = 0
        self._completed = 0
        self._failed = 0
        self._cancelled = 0
        self._sequence = 0
        self._closed = False
        self._draining_run_id: UUID | None = None

    # -- admission ----------------------------------------------------------

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def class_cycle(self) -> tuple[PriorityLevel, ...]:
        return self._dispatcher.cycle

    def next_sequence(self) -> int:
        """Reserve the next admission sequence number."""
        with self._condition:
            sequence = self._sequence
            self._sequence += 1
            return sequence

    def admit(self, item: WorkItem, *, accepted_before_drain: bool = False) -> bool:
        """Admit one work item, or reject it when admission is closed/full."""
        accepted, _ = self.admit_many([item], accepted_before_drain=accepted_before_drain)
        return bool(accepted)

    def admit_many(
        self, items: Iterable[WorkItem], *, accepted_before_drain: bool = False
    ) -> tuple[list[WorkItem], list[WorkItem]]:
        """Admit readings together under one lock and wake the attention worker."""
        accepted: list[WorkItem] = []
        rejected: list[WorkItem] = []
        with self._condition:
            for item in items:
                if not isinstance(item, WorkItem):
                    raise TypeError("'items' must contain WorkItem instances")
                if (
                    self._closed
                    or (
                        self._draining_run_id is not None
                        and item.run_id == self._draining_run_id
                        and not accepted_before_drain
                    )
                    or self._pending >= self._capacity
                ):
                    self._rejected += 1
                    rejected.append(item)
                    continue
                if item.scenario == "WITHOUT_QOS":
                    self._without_qos.append(item)
                else:
                    self._planner.plan(item)
                self._pending += 1
                self._admitted += 1
                accepted.append(item)
            if accepted:
                self._condition.notify_all()
        return accepted, rejected

    # -- selection and attention hand-off ----------------------------------

    def wait_for_work(self, timeout: float | None = None) -> bool:
        """Block until work is pending; return whether there is pending work."""
        with self._condition:
            if self._pending == 0 and not self._closed:
                self._condition.wait(timeout)
            return self._pending > 0

    def select_next(self) -> Optional[WorkItem]:
        """Remove and return the next admitted work item, if any."""
        with self._condition:
            item: Optional[ScheduledItem]
            if self._without_qos:
                item = self._without_qos.popleft()
            else:
                item = self._dispatcher.select_next()
            if item is None:
                return None
            if not isinstance(item, WorkItem):
                # The production planner must only contain work items.  A
                # legacy demonstration classification here would be a wiring
                # error, not telemetry to process.
                raise TypeError(
                    "production dispatch selected a non-WorkItem "
                    f"({type(item).__name__})"
                )
            self._pending -= 1
            self._in_flight += 1
            self._selected_item = item
            return item

    def finish(self, *, success: bool) -> None:
        """Mark the current attention as finished and expose the outcome."""
        with self._condition:
            if self._in_flight > 0:
                self._in_flight -= 1
            if success:
                self._completed += 1
            else:
                self._failed += 1
                if self._selected_item is not None:
                    item = self._selected_item
                    self._recent_failures.append({
                        "work_id": str(item.id),
                        "device_code": item.device_code,
                        "sensor_name": item.sensor_name,
                        "run_id": str(item.run_id) if item.run_id else None,
                        "scenario": item.scenario,
                    })
            self._selected_item = None
            self._condition.notify_all()

    # -- lifecycle ----------------------------------------------------------

    def close_admission(self) -> None:
        """Stop accepting new work; already admitted work can still drain."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def cancel_pending(self) -> list[WorkItem]:
        """Close admission and atomically remove pending work, not in-flight work."""
        with self._condition:
            self._closed = True
            cancelled = list(self._without_qos)
            self._without_qos.clear()
            for priority in (PriorityLevel.HIGH, PriorityLevel.MEDIUM, PriorityLevel.LOW):
                while True:
                    item = self._planner.dequeue(priority)
                    if item is None:
                        break
                    if not isinstance(item, WorkItem):
                        raise TypeError("production dispatch contains a non-WorkItem")
                    cancelled.append(item)
            self._pending -= len(cancelled)
            self._cancelled += len(cancelled)
            self._condition.notify_all()
            return cancelled

    def begin_drain(self, run_id: UUID) -> None:
        """Reject new work for ``run_id``; other runs stay unaffected.

        Already admitted work of the draining run is never reassigned: it
        keeps its sealed ``run_id`` and is still attended.
        """
        if not isinstance(run_id, UUID):
            raise TypeError("'run_id' must be a UUID")
        with self._condition:
            if self._draining_run_id is not None and self._draining_run_id != run_id:
                raise RuntimeError("another experiment is already draining")
            self._draining_run_id = run_id
            self._condition.notify_all()

    def end_drain(self) -> None:
        with self._condition:
            self._draining_run_id = None
            self._condition.notify_all()

    def wait_until_idle(self, timeout: float) -> bool:
        """Wait for admitted work to be attended; ``False`` on timeout."""
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError("'timeout' must be a number of seconds")
        deadline = time.monotonic() + float(timeout)
        with self._condition:
            while self._pending or self._in_flight:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def wake(self) -> None:
        with self._condition:
            self._condition.notify_all()

    @property
    def is_closed(self) -> bool:
        with self._condition:
            return self._closed

    @property
    def draining_run_id(self) -> UUID | None:
        with self._condition:
            return self._draining_run_id

    @property
    def is_draining(self) -> bool:
        with self._condition:
            return self._draining_run_id is not None

    @property
    def pending(self) -> int:
        with self._condition:
            return self._pending

    @property
    def in_flight(self) -> int:
        with self._condition:
            return self._in_flight

    def is_empty(self) -> bool:
        with self._condition:
            return self._pending == 0 and self._in_flight == 0

    @property
    def counters(self) -> dict[str, int]:
        with self._condition:
            return {
                "admitted": self._admitted,
                "rejected": self._rejected,
                "completed": self._completed,
                "failed": self._failed,
                "cancelled": self._cancelled,
                "pending": self._pending,
                "in_flight": self._in_flight,
            }

    def snapshot(self) -> dict[str, object]:
        """Observable runtime state without consuming or fabricating work."""
        with self._condition:
            snapshot: dict[str, object] = {
                **self.counters,
                "capacity": self._capacity,
                "closed": self._closed,
                "draining": self._draining_run_id is not None,
                "draining_run_id": (
                    str(self._draining_run_id)
                    if self._draining_run_id is not None
                    else None
                ),
                "without_qos_pending": len(self._without_qos),
                "recent_failures": list(self._recent_failures),
            }
            try:
                snapshot["queues"] = {
                    priority.value: self._planner.size(priority)
                    for priority in (PriorityLevel.HIGH, PriorityLevel.MEDIUM, PriorityLevel.LOW)
                }
                snapshot["wfq"] = {
                    "policy": "criticality_bands_v1",
                    "band_weights": self._planner.wfq.band_weights,
                    "pending_by_band": {
                        band: sum(
                            WFQScheduler.band_for(item) == band
                            for item in self._planner.get_queue(PriorityLevel.HIGH)
                        )
                        for band in ("H7", "H8", "H9")
                    },
                }
                def summarize(items):
                    return [{
                        "work_id": str(item.id),
                        "source_message_id": str(item.source_message_id),
                        "device_code": item.device_code,
                        "sensor_name": item.sensor_name,
                        "sequence": item.sequence,
                        "scenario": item.scenario,
                        "priority": item.priority,
                        "run_id": str(item.run_id) if item.run_id else None,
                        "admitted_at": item.admitted_at.isoformat(),
                    } for item in items[:5]]
                snapshot["pending_sample"] = {
                    priority.value: summarize(self._planner.get_queue(priority))
                    for priority in (PriorityLevel.HIGH, PriorityLevel.MEDIUM, PriorityLevel.LOW)
                }
                snapshot["pending_sample"]["without_qos"] = summarize(list(self._without_qos))
            except Exception:  # pragma: no cover - defensive for custom planners
                snapshot["queues"] = {}
                snapshot["pending_sample"] = {}
            return snapshot
