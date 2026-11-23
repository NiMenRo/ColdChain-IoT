"""Managed local evidence, scoped by server-derived run UUIDs.

No user-supplied paths, campaign imports, SQL writes or network calls on reads.
Missing/partial journals never certify final delivery rates.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from app.qos.application.telemetry_evidence import reconcile

logger = logging.getLogger(__name__)
_lock = threading.RLock()
MAX_JOURNAL_BYTES = 64 * 1024 * 1024


def _utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def directory(run_id) -> Path:
    root = Path(os.getenv("TELEMETRY_EVIDENCE_DIR") or
                Path(__file__).resolve().parents[3] / ".coldchain" / "evidence")
    return root.resolve() / str(UUID(str(run_id)))


def _save(run_id, value):
    target = directory(run_id) / "manifest.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    temporary.replace(target)


def manifest(run_id):
    target = directory(run_id) / "manifest.json"
    if not target.exists():
        return None
    value = json.loads(target.read_text(encoding="utf-8"))
    if value.get("run_id") != str(run_id) or value.get("version") != 1:
        raise ValueError("Invalid capture manifest")
    return value


def start_capture(run, config):
    if not getattr(config, "telemetry_evidence_enabled", False):
        return
    try:
        with _lock:
            directory(run.id).mkdir(parents=True, exist_ok=False)
            _save(run.id, {
                "version": 1, "run_id": str(run.id), "started_at": _utc(run.started_at).isoformat(),
                "clock_domain": f"managed-local-{run.id}",
                "grace_seconds": config.telemetry_evidence_grace_s,
                "config": config.effective_qos_config(), "producers": [],
                "emission_ended_at": None, "sealed": False, "sealed_at": None,
            })
        from app.acquisition.telemetry_trace import record_trace
        record_trace("capture_opened", run_id=str(run.id))
    except (OSError, ValueError, TypeError):
        logger.exception("Managed capture unavailable for run %s", run.id)


def capture_target(run_id):
    """Cheap recording lookup; paths are never returned to HTTP clients."""
    if run_id is None:
        return None
    try:
        run_id = str(UUID(str(run_id)))
        target = directory(run_id)
        if (target / "manifest.json").is_file():
            return target / "backend.jsonl", f"managed-local-{run_id}"
    except (ValueError, TypeError, OSError):
        pass
    return None


def producer_environment(run_id, env):
    with _lock:
        value = manifest(run_id)
        if value is None:
            return None
        name = f"producer-{uuid4().hex}.jsonl"
        value["producers"].append({"name": name, "exit_code": None, "forced": False})
        _save(run_id, value)
        env.update({
            "TELEMETRY_TRACE_FILE": str(directory(run_id) / name),
            "TELEMETRY_CLOCK_DOMAIN": value["clock_domain"],
            "COLDCHAIN_MANAGED_EVIDENCE": "true",
            "COLDCHAIN_STOP_FILE": str(directory(run_id) / f"{name}.stop"),
        })
        return name


def producer_stopped(run_id, name, exit_code, forced):
    with _lock:
        value = manifest(run_id)
        if value is None:
            return
        for row in value["producers"]:
            if row["name"] == name:
                row.update(exit_code=exit_code, forced=forced)
        _save(run_id, value)


def request_close(run_id):
    """Freeze the emission boundary once; retries must not extend the window."""
    with _lock:
        value = manifest(run_id)
        if value is None:
            return None
        if not value["emission_ended_at"]:
            value["emission_ended_at"] = datetime.now(timezone.utc).isoformat()
            _save(run_id, value)
        return _utc(value["emission_ended_at"]) + timedelta(seconds=value["grace_seconds"])


def seal_capture(run_id):
    from app.acquisition.telemetry_trace import record_trace
    with _lock:
        value = manifest(run_id)
        if value is not None:
            value["sealed"] = record_trace("capture_closed", run_id=str(run_id))
            value["sealed_at"] = datetime.now(timezone.utc).isoformat() if value["sealed"] else None
            _save(run_id, value)


def _events(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JOURNAL_BYTES:
        raise ValueError("Missing or oversized capture")
    data = path.read_text(encoding="utf-8")
    if data and not data.endswith("\n"):
        raise ValueError("Partial capture")
    rows = [json.loads(line) for line in data.splitlines() if line]
    sequences = {}
    for row in rows:
        key = row["journal_session"]
        expected = sequences.get(key, 0) + 1
        if row["journal_sequence"] != expected or row.get("capture_errors", 0):
            raise ValueError("Capture contains missing or failed writes")
        sequences[key] = expected
    return rows


def _empty(run_id, status, reason):
    return {
        "run_id": str(run_id), "status": status, "reasons": [reason],
        "counts": {}, "window": None, "configuration": None,
        "pending_messages": None, "pdr_percent": None, "loss_percent": None,
        "received_payload_bytes": None, "payload_goodput_bytes_per_second": None,
        "device_to_persist_ms": {"count": 0, "mean": None, "p95": None},
        "device_to_alert_persist_ms": {"count": 0, "mean": None, "p95": None},
        "message_delay_variation_ms": {"count": 0, "mean": None, "p95": None},
        "by_priority": {}, "clock_unmeasurable": None,
        "scope": "managed_local_producer",
    }


def report_for_run(run, priority_by_work_id=None):
    try:
        value = manifest(run.id)
        if value is None:
            return _empty(run.id, "unavailable", "Esta ejecución no tiene captura gestionada; no se reconstruyen envíos históricos.")
        if not value["producers"]:
            return _empty(run.id, "incomplete" if run.finished_at else "provisional",
                          "No hay evidencia del productor gestionado. Las tasas no están disponibles.")
        backend = _events(directory(run.id) / "backend.jsonl")
        total_bytes = (directory(run.id) / "backend.jsonl").stat().st_size
        sender = []
        sessions_closed = bool(value["producers"])
        for producer in value["producers"]:
            name = producer["name"]
            if Path(name).name != name or not name.startswith("producer-") or not name.endswith(".jsonl"):
                raise ValueError("Invalid producer manifest")
            total_bytes += (directory(run.id) / name).stat().st_size
            if total_bytes > MAX_JOURNAL_BYTES:
                raise ValueError("Capture exceeds the aggregate read limit")
            rows = _events(directory(run.id) / name)
            sender.extend(rows)
            sessions_closed &= (
                producer["exit_code"] == 0 and not producer["forced"]
                and bool(rows) and rows[-1]["event"] == "producer_closed"
                and rows[-1].get("pending_publications") == 0
            )
        current = datetime.now(timezone.utc)
        started = _utc(value["started_at"])
        ended = _utc(value["emission_ended_at"]) if value["emission_ended_at"] else current
        # A zero-duration just-opened run has no rates or fabricated elapsed time.
        if ended <= started:
            return _empty(run.id, "in_progress", "La captura acaba de iniciarse.")
        complete = bool(run.finished_at and value["sealed"] and sessions_closed)
        backend_sessions = {row["journal_session"] for row in backend}
        closed_sessions = {row["journal_session"] for row in backend if row["event"] == "capture_closed"}
        backend_complete = (
            any(row["event"] == "capture_opened" for row in backend)
            and backend_sessions <= closed_sessions
        )
        complete &= backend_complete
        result = reconcile(
            sender, backend, started_at=started, emission_ended_at=ended,
            observed_until=current, grace_seconds=value["grace_seconds"],
            run_id=str(run.id), complete_capture=complete,
            priority_by_work_id=priority_by_work_id,
            processing_observed_until=_utc(value["sealed_at"]) if value.get("sealed_at") else current,
        )
        reasons = []
        if not value["producers"]:
            reasons.append("No hay evidencia del productor gestionado.")
        if run.finished_at and not sessions_closed:
            reasons.append("El productor no confirmó un cierre íntegro de su captura.")
        if run.finished_at and not backend_complete:
            reasons.append("El backend no confirmó una captura íntegra de principio a fin.")
        if run.finished_at and not value["sealed"]:
            reasons.append("El cierre de la captura no quedó confirmado.")
        if result["counts"]["untraced_receptions"] or result["counts"]["uncorrelated_receptions"]:
            complete = False
            reasons.append("Hay recepciones sin evidencia de envío correlacionable.")
        if result["counts"]["publication_outcome_unknown"]:
            reasons.append("Hay publicaciones sin resultado confirmado.")
        final = complete and result["status"] == "final"
        if not run.finished_at:
            status = "in_progress" if not reasons else "provisional"
        else:
            status = "final" if final else "incomplete" if reasons else "provisional"
        counts = result["counts"]
        return {
            "run_id": str(run.id), "status": status, "reasons": reasons,
            "counts": counts, "window": result["window"], "configuration": value["config"],
            "pending_messages": counts["not_received"],
            "pdr_percent": result["pdr_percent"] if final else None,
            "loss_percent": result["loss_percent"] if final else None,
            "received_payload_bytes": result["observed_payload_bytes"],
            "payload_goodput_bytes_per_second": result["payload_goodput_bytes_per_second"] if final else None,
            "device_to_persist_ms": result["device_to_persist_ms"],
            "device_to_alert_persist_ms": result["device_to_alert_persist_ms"],
            "message_delay_variation_ms": result["message_delay_variation_ms"],
            "by_priority": result["by_priority"],
            "clock_unmeasurable": result["unmeasurable"]["clock_domain"] + result["unmeasurable"]["timestamp"],
            "scope": "managed_local_producer",
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        logger.warning("Incomplete evidence for run %s", run.id)
        return _empty(
            run.id, "provisional" if not run.finished_at else "incomplete",
            "La captura está ausente, incompleta, no es válida o supera el límite de lectura. No se publican tasas.",
        )
