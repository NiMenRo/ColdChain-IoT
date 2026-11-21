"""Opt-in append-only publication evidence; never a replacement for receipts."""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

_lock = threading.Lock()
_session = uuid4().hex
_sequences = {}
_errors = {}
logger = logging.getLogger(__name__)


def record_trace(event: str, **fields) -> bool:
    path = os.getenv("TELEMETRY_TRACE_FILE", "").strip()
    if not path:
        return False
    try:
        with _lock:
            _sequences[path] = _sequences.get(path, 0) + 1
            row = {"trace_version": 1, "event": event,
                   "event_at": datetime.now(timezone.utc).isoformat(), **fields,
                   "journal_session": _session, "journal_sequence": _sequences[path],
                   "capture_errors": _errors.get(path, 0)}
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        return True
    except (OSError, TypeError, ValueError):
        _errors[path] = _errors.get(path, 0) + 1
        logger.exception("Publication trace unavailable; this campaign has incomplete evidence")
        return False
