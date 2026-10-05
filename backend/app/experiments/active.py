"""Active experiment run holder (TSK-059.7).

Single resolution point for the WITH_QOS / WITHOUT_QOS scenario. The
pipeline resolves the scenario once per message from here; services never
query the scenario themselves. Thread-safe for the worker thread.

No active run  →  legacy behavior: WITH_QOS, run_id NULL.
"""

from __future__ import annotations

import threading
import uuid

from app.database.infrastructure.models import EXPERIMENT_SCENARIOS

_lock = threading.Lock()
_active: tuple[uuid.UUID, str] | None = None


def set_active_run(run_id: uuid.UUID, scenario: str) -> None:
    """Mark an experiment run as active. Raises if one is already active."""
    if not isinstance(run_id, uuid.UUID):
        raise TypeError("'run_id' must be a UUID instance")
    if not isinstance(scenario, str) or scenario not in EXPERIMENT_SCENARIOS:
        raise ValueError(
            f"scenario must be one of {sorted(EXPERIMENT_SCENARIOS)}"
        )
    with _lock:
        global _active
        if _active is not None:
            raise RuntimeError(
                "an experiment run is already active; finish it before starting another"
            )
        _active = (run_id, scenario)


def clear_active_run() -> None:
    """Release the active run (idempotent)."""
    with _lock:
        global _active
        _active = None


def get_active_run() -> tuple[uuid.UUID, str] | None:
    """Return (run_id, scenario) or None when no run is active."""
    with _lock:
        return _active


def resolve_scenario() -> tuple[uuid.UUID | None, str]:
    """Scenario for the next message: active run or legacy WITH_QOS default."""
    active = get_active_run()
    if active is None:
        return None, "WITH_QOS"
    return active[0], active[1]
