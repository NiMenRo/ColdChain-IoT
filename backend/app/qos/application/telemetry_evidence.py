"""Offline reconciliation of independently captured sender/receiver evidence.

No rates are derived from backend-generated sequence numbers or legacy QoS
records. Journals are opt-in evidence, not a durable delivery guarantee.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from math import ceil, isfinite
from typing import Iterable
from uuid import UUID


def _time(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Evidence timestamps must have an explicit timezone")
    return parsed


def _identity(row: dict) -> tuple | None:
    trace = row.get("trace")
    if not isinstance(trace, dict):
        return None
    message_id = str(UUID(str(trace.get("message_id"))))
    session = str(UUID(str(trace.get("producer_session_id"))))
    sequence = trace.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ValueError("Invalid producer sequence")
    device = row.get("device_code")
    if not isinstance(device, str) or not device:
        raise ValueError("Missing emitting device")
    run = trace.get("run_id")
    if run is not None:
        run = str(UUID(str(run)))
    return message_id, session, device, sequence, run


def _stats(values: list[float]) -> dict:
    ordered = sorted(values)
    return {
        "count": len(values),
        "mean": sum(values) / len(values) if values else None,
        "p95": ordered[ceil(0.95 * len(values)) - 1] if values else None,
    }


def reconcile(
    producer_events: Iterable[dict],
    backend_events: Iterable[dict],
    *,
    started_at: datetime,
    emission_ended_at: datetime,
    observed_until: datetime,
    grace_seconds: float,
    run_id: str | None,
    complete_capture: bool = False,
    priority_by_work_id: dict[str, str] | None = None,
    processing_observed_until: datetime | None = None,
) -> dict:
    """Reconcile a fixed emission cohort with an explicit reception deadline.

    ``complete_capture`` is an operator attestation that every participating
    process journal was collected intact. It is not inferred from receipts.
    Missing publication outcomes still prevent a final PDR.
    """
    start, end, observed = map(_time, (started_at, emission_ended_at, observed_until))
    if end <= start or observed < start:
        raise ValueError("Invalid observation window")
    if isinstance(grace_seconds, bool) or not isfinite(grace_seconds) or grace_seconds < 0:
        raise ValueError("grace_seconds must be finite and non-negative")
    deadline = end + timedelta(seconds=grace_seconds)
    processing_limit = (
        min(_time(processing_observed_until), observed)
        if processing_observed_until is not None else min(deadline, observed)
    )
    selected_run = str(UUID(run_id)) if run_id is not None else None
    producers, backend = list(producer_events), list(backend_events)
    unmatched_publications = sum(row.get("event") == "publication_unmatched" for row in producers)
    identities: dict[str, tuple] = {}
    sequences: dict[tuple, str] = {}
    for row in producers + backend:
        if row.get("trace_version") != 1:
            raise ValueError("Unsupported or missing trace_version")
        identity = _identity(row)
        if identity is None:
            continue
        message_id, session, device, sequence, run = identity
        if message_id in identities and identities[message_id] != identity:
            raise ValueError("Conflicting emission identity for the same message_id")
        sequence_key = (session, device, sequence, run)
        if sequence_key in sequences and sequences[sequence_key] != message_id:
            raise ValueError("Producer reused a sequence within the same session/device/run")
        identities[message_id] = identity
        sequences[sequence_key] = message_id

    attempts: dict[str, dict] = {}
    known_attempts: set[str] = set()
    completed: set[str] = set()
    errors: set[str] = set()
    for row in producers:
        identity = _identity(row)
        if identity is None or identity[-1] != selected_run:
            continue
        when = _time(row["event_at"])
        message_id = identity[0]
        if row["event"] == "publish_attempt":
            known_attempts.add(message_id)
            if start <= when < end and when <= observed:
                attempts.setdefault(message_id, row)
        if when <= observed:
            if row["event"] == "publish_complete":
                completed.add(message_id)
            elif row["event"] == "publish_error":
                errors.add(message_id)
    sent = set(attempts) & completed
    uncertain = set(attempts) - completed - errors
    received: dict[str, dict] = {}
    duplicates = late = uncorrelated = legacy = 0
    for row in backend:
        if row["event"] != "received":
            continue
        when = _time(row["received_at"])
        if when > observed:
            continue
        identity = _identity(row)
        if identity is None:
            legacy += 1
            continue
        if identity[-1] != selected_run:
            continue
        message_id = identity[0]
        if message_id not in attempts:
            if message_id in known_attempts:
                # Complete journals may span several windows. Traffic whose
                # emission is known to be outside this cohort is not missing
                # sender evidence for this cohort.
                continue
            uncorrelated += 1
            continue
        if when > deadline:
            late += 1
            continue
        if when < start:
            raise ValueError("Receipt precedes the cohort window; check clock synchronization")
        if message_id in received:
            duplicates += 1
            if when >= _time(received[message_id]["received_at"]):
                continue
        received[message_id] = row

    matched = sent & set(received)
    byte_sizes = []
    for message_id in matched:
        value = received[message_id].get("size_bytes")
        expected_size = attempts[message_id].get("size_bytes")
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("Receipt has no measured payload byte count")
        if value != expected_size:
            raise ValueError("Sender and receiver payload sizes differ")
        byte_sizes.append(value)

    persistence_ms: list[float] = []
    alert_persistence_ms: list[float] = []
    persist_ids: set[str] = set()
    missing_clock = invalid_delta = 0
    by_sensor: dict[str, list[float]] = {}
    by_priority: dict[str, dict[str, list[float]]] = {}
    for row in backend:
        if row["event"] != "persisted" or row.get("source_message_id") not in matched:
            continue
        committed = _time(row["committed_at"])
        if committed > processing_limit:
            continue
        work_id = row["work_id"]
        if work_id in persist_ids:
            continue
        persist_ids.add(work_id)
        origin = attempts[row["source_message_id"]]["trace"]
        if not origin.get("clock_domain") or origin["clock_domain"] != row.get("backend_clock_domain"):
            missing_clock += 1
            continue
        try:
            delta = (committed - _time(row["generated_at"])).total_seconds() * 1000
        except (TypeError, ValueError):
            invalid_delta += 1
            continue
        if delta < 0:
            invalid_delta += 1
            continue
        persistence_ms.append(delta)
        by_sensor.setdefault(row["sensor_name"], []).append(delta)
        priority = (priority_by_work_id or {}).get(work_id, row.get("priority"))
        if priority in ("high", "medium", "low"):
            bucket = by_priority.setdefault(priority, {"persist": [], "alert": []})
            bucket["persist"].append(delta)
            if row.get("alerts"):
                bucket["alert"].append(delta)
        if row.get("alerts"):
            # Alerts and reading share a transaction; this is their confirmed
            # persistence, not notification dispatch or human receipt.
            alert_persistence_ms.append(delta)

    closed = observed >= deadline
    final = bool(
        complete_capture and closed and not uncertain and not uncorrelated
        and not unmatched_publications
    )
    duration = (deadline - start).total_seconds()
    pdr = 100 * len(matched) / len(sent) if final and sent else None
    reading_counts = {
        event: len({
            row["work_id"] for row in backend
            if row["event"] == event and row.get("source_message_id") in attempts
            and _time(row["event_at"]) <= processing_limit
        })
        for event in ("reading_admitted", "reading_rejected", "reading_failed",
                      "reading_cancelled", "replay_skipped")
    }
    configurations = [
        row["config"] for row in backend
        if row["event"] == "dispatch_config" and _time(row["event_at"]) <= observed
    ]
    return {
        "evidence_version": 1,
        "run_id": selected_run,
        "window": {
            "started_at": start.isoformat(), "emission_ended_at": end.isoformat(),
            "reception_deadline": deadline.isoformat(), "observed_until": observed.isoformat(),
            "grace_seconds": grace_seconds, "rate_interval_seconds": duration,
            "closed": closed, "complete_capture_attested": complete_capture,
            "processing_observed_until": processing_limit.isoformat(),
        },
        "status": "final" if final else "provisional",
        "counts": {
            "publication_attempts": len(attempts),
            "publication_errors": len(set(attempts) & errors),
            "publication_outcome_unknown": len(uncertain),
            "unmatched_publication_callbacks": unmatched_publications,
            "sent_unique": len(sent), "received_unique": len(matched),
            "not_received": len(sent - set(received)),
            "duplicate_receptions": duplicates, "late_receptions": late,
            "uncorrelated_receptions": uncorrelated, "untraced_receptions": legacy,
            "persisted_readings": len(persist_ids),
            **reading_counts,
        },
        "pdr_percent": pdr,
        "loss_percent": 100 - pdr if pdr is not None else None,
        "received_payload_bytes": sum(byte_sizes) if final and sent else None,
        "observed_payload_bytes": sum(byte_sizes) if attempts else None,
        "payload_goodput_bytes_per_second": sum(byte_sizes) / duration if final and sent else None,
        "device_to_persist_ms": _stats(persistence_ms),
        "device_to_alert_persist_ms": _stats(alert_persistence_ms),
        "device_to_persist_ms_by_sensor": {key: _stats(values) for key, values in by_sensor.items()},
        "by_priority": {
            key: {"persist": _stats(values["persist"]), "alert": _stats(values["alert"])}
            for key, values in by_priority.items()
        },
        "unmeasurable": {"clock_domain": missing_clock, "timestamp": invalid_delta},
        "dispatch_configurations": configurations,
        "limitations": [
            "PDR is application-message reception, not IP packet loss or notification delivery.",
            "Sent means observed on_publish completion; publish() acceptance is not receipt.",
            "Window closure and cross-host timing require synchronized clocks.",
            "Equal clock domains are an operator assertion, not synchronization verification.",
            "Capture is opt-in; missing/corrupt journals invalidate experimental conclusions.",
            "Late means after the fixed deadline; it does not prove permanent loss.",
        ],
    }
