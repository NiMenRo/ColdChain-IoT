"""Opt-in evidence journal, independent of SQL/notifications and legacy metrics.

Each backend process must use its own file. Consumers reconcile by emission
identity, never by an MQTT mid or backend admission sequence.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_session = uuid4().hex
_sequences = {}
_errors = {}


def emission_trace(payload) -> dict | None:
    trace = payload.get("trace") if isinstance(payload, dict) else None
    if trace is None:
        return None
    if not isinstance(trace, dict):
        raise ValueError("trace must be an object")
    for name in ("message_id", "producer_session_id"):
        UUID(str(trace.get(name)))
    sequence = trace.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ValueError("trace.sequence must be a non-negative integer")
    if trace.get("run_id") is not None:
        UUID(str(trace["run_id"]))
    if trace.get("clock_domain") is not None and (
        not isinstance(trace["clock_domain"], str) or not trace["clock_domain"].strip()
    ):
        raise ValueError("trace.clock_domain must be a non-empty string or null")
    return {name: trace.get(name) for name in
            ("message_id", "producer_session_id", "sequence", "run_id", "clock_domain")}


def record_trace(event: str, **fields) -> bool:
    path = os.getenv("TELEMETRY_TRACE_FILE", "").strip()
    targets = {}
    if path:
        targets[str(Path(path).resolve())] = os.getenv("TELEMETRY_CLOCK_DOMAIN") or None
    from app.experiments.evidence import capture_target
    run_id = fields.get("run_id") or (fields.get("trace") or {}).get("run_id")
    if run_id is None:
        from app.experiments.active import get_active_run
        active = get_active_run()
        run_id = active[0] if active else None
    managed = capture_target(run_id)
    if managed:
        target, domain = managed
        targets[str(target)] = domain
    if not targets:
        return False
    success = True
    with _lock:
        for path, domain in targets.items():
            _sequences[path] = _sequences.get(path, 0) + 1
            row = {
                "trace_version": 1, "event": event,
                "event_at": datetime.now(timezone.utc).isoformat(),
                **fields, "backend_clock_domain": domain,
                "journal_session": _session, "journal_sequence": _sequences[path],
                "capture_errors": _errors.get(path, 0),
            }
            try:
                target = Path(path)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            except (OSError, TypeError, ValueError):
                _errors[path] = _errors.get(path, 0) + 1
                success = False
                logger.exception("Telemetry trace unavailable; capture is incomplete")
    return success
