"""Bounded transport queue with explicit, observable rejection.

The queue is transport-only: it stores raw MQTT messages until the ingestion
worker normalizes them.  When it is full the *new* message is rejected instead
of silently evicting the oldest one, so admission is observable to callers and
no already-received telemetry disappears without a counter.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional


class MessageQueue:

    def __init__(self, max_size: int = 1000):
        if isinstance(max_size, bool) or not isinstance(max_size, int) or max_size <= 0:
            raise ValueError("'max_size' must be a positive integer")
        self._capacity = max_size
        self._queue: deque = deque()
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._rejected = 0
        self._draining_run_id: str | None = None
        self._processing: dict[str, int] = {}

    def _append_locked(self, message: dict) -> bool:
        raw_run_id = message.get("run_id") if isinstance(message, dict) else None
        run_id = str(raw_run_id) if raw_run_id else None
        if len(self._queue) >= self._capacity or (run_id is not None and run_id == self._draining_run_id):
            self._rejected += 1
            return False
        self._queue.append(message)
        self._condition.notify_all()
        return True

    def append_received(self, message: dict) -> bool:
        """Seal context and enqueue atomically against the experiment barrier."""
        from app.experiments.active import resolve_scenario

        with self._condition:
            run_id, scenario = resolve_scenario()
            message.update(
                run_id=str(run_id) if run_id is not None else None,
                scenario=scenario,
                received_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                received_monotonic=time.monotonic(),
            )
            return self._append_locked(message)

    def begin_drain(self, run_id) -> None:
        with self._condition:
            run_key = str(run_id)
            if self._draining_run_id not in (None, run_key):
                raise RuntimeError("another experiment is already draining")
            self._draining_run_id = run_key

    def end_drain(self, run_id) -> None:
        with self._condition:
            if self._draining_run_id == str(run_id):
                self._draining_run_id = None
                self._condition.notify_all()

    def wait_run_ingested(self, run_id, timeout: float) -> bool:
        """Wait until accepted messages leave both transport and ingestion."""
        key = str(run_id)
        deadline = time.monotonic() + timeout
        with self._condition:
            while (self._processing.get(key, 0) or
                   any(isinstance(m, dict) and str(m.get("run_id")) == key for m in self._queue)):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def rejected(self) -> int:
        """Messages rejected due to transport capacity or a draining run."""
        with self._lock:
            return self._rejected

    def append(self, message: dict) -> bool:
        """Admit one message; return ``False`` when the queue is full.

        The new message is rejected and the oldest pending messages are kept.
        """
        with self._lock:
            return self._append_locked(message)

    def pop(self) -> Optional[dict]:
        with self._lock:
            if self._queue:
                return self._queue.popleft()
            return None

    def pop_for_processing(self) -> Optional[dict]:
        with self._condition:
            if not self._queue:
                return None
            message = self._queue.popleft()
            run_id = message.get("run_id") if isinstance(message, dict) else None
            if run_id is not None:
                key = str(run_id)
                self._processing[key] = self._processing.get(key, 0) + 1
            return message

    def finish_processing(self, message: dict) -> None:
        with self._condition:
            run_id = message.get("run_id") if isinstance(message, dict) else None
            if run_id is not None:
                key = str(run_id)
                remaining = self._processing.get(key, 0) - 1
                if remaining > 0:
                    self._processing[key] = remaining
                else:
                    self._processing.pop(key, None)
            self._condition.notify_all()

    def get_all(self) -> list:
        with self._lock:
            return list(self._queue)

    def clear(self) -> None:
        with self._condition:
            self._queue.clear()
            self._condition.notify_all()

    def cancel_pending(self) -> list[dict]:
        """Atomically return and remove undelivered transport messages."""
        with self._condition:
            pending = list(self._queue)
            self._queue.clear()
            self._condition.notify_all()
            return pending

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)
