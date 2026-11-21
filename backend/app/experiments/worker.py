"""Run-scoped simulator worker.

While an experiment run is open, telemetry must flow so the pipeline can
persist readings/alerts and record run metrics. This module launches the
device simulator (``simulator/main.py --cycles 0``) as a child process
scoped to the run id and stops it when the run finishes.

Explicitly opt-in via ``COLDCHAIN_SIM_WORKER_ENABLED=true`` (set by
coldchain.ps1 for local runs). Default off so unit tests and plain
uvicorn invocations never spawn processes. All failures are warn-only:
a worker problem must never break run start/finish semantics.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)

_workers: dict[str, subprocess.Popen] = {}
_worker_evidence: dict[str, str] = {}

#: Snapshot sensor conditions and the simulator flag they map to. The UI
#: persists ``altered`` while the simulator CLI accepts ``critica``; mapping
#: here makes the selected condition explicit instead of silently falling
#: back to the simulator's default (critical) behavior.
SNAPSHOT_SENSOR_CONDITIONS = {
    "normal": "normal",
    "altered": "critica",
    "critica": "critica",
}


def worker_enabled() -> bool:
    return os.getenv("COLDCHAIN_SIM_WORKER_ENABLED", "").strip().lower() == "true"


def resolve_sensor_condition(run_id: UUID) -> str | None:
    """Best-effort read of `sensor_condition` from the run snapshot.

    Returns 'critica'/'normal' or None when the run, the snapshot, or the
    value is missing/invalid. Never raises: a worker problem must never
    break run start semantics (falls back to default simulator behavior).
    """
    try:
        import json

        from app.database.infrastructure.models import ExperimentRunORM
        from app.database.infrastructure.session import SessionLocal

        with SessionLocal() as db:
            row = db.query(ExperimentRunORM).filter_by(id=run_id).first()
            if row is None or not row.config_snapshot:
                return None
            try:
                data = json.loads(row.config_snapshot)
            except (ValueError, TypeError):
                return None
            cond = data.get("sensor_condition") if isinstance(data, dict) else None
            cond = cond.strip().lower() if isinstance(cond, str) else None
            return SNAPSHOT_SENSOR_CONDITIONS.get(cond)
    except Exception:
        logger.warning("sensor_condition lookup skipped for run %s", run_id)
        return None


def _simulator_cwd() -> Path:
    # backend/app/experiments/worker.py -> repo root -> simulator/
    return Path(__file__).resolve().parents[3] / "simulator"


def _child_env() -> dict[str, str]:
    """Environment for the simulator child process.

    The broker ACL only authorizes the ``simulator`` user to publish
    telemetry (the ``backend`` user is read-only), so the worker takes
    MQTT credentials from ``simulator/.env`` (local, never versioned)
    when present. Missing file/vars → parent env (broker will reject
    publishes; the run itself is unaffected).
    """
    env = {**os.environ}
    dotenv = _simulator_cwd() / ".env"
    try:
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key in ("MQTT_USERNAME", "MQTT_PASSWORD", "MQTT_CA_CERT") and value:
                env[key] = value
    except OSError:
        logger.warning("simulator .env not found at %s; using parent MQTT env", dotenv)
    return env


def start_worker(run_id: UUID) -> bool:
    """Launch the continuous simulator for a run. True if (already) running."""
    key = str(run_id)
    existing = _workers.get(key)
    if existing is not None:
        if existing.poll() is None:
            return True
        _workers.pop(key, None)
    if not worker_enabled():
        return False
    argv = [sys.executable, "main.py", "--cycles", "0"]
    condition = resolve_sensor_condition(run_id)
    if condition is not None:
        argv += ["--condition", condition]
    try:
        env = _child_env()
        env["COLDCHAIN_RUN_ID"] = key
        from app.experiments.evidence import producer_environment
        try:
            evidence_name = producer_environment(run_id, env)
        except (OSError, ValueError, TypeError):
            logger.exception("Managed evidence unavailable for run %s; simulator continues", key)
            evidence_name = None
        if evidence_name:
            _worker_evidence[key] = evidence_name
        elif env.get("TELEMETRY_TRACE_FILE"):
            # Never let different processes append to the backend's journal.
            backend_trace = Path(env["TELEMETRY_TRACE_FILE"]).resolve()
            env["TELEMETRY_TRACE_FILE"] = str(
                backend_trace.with_name(f"producer-{key}-{uuid.uuid4().hex}.jsonl")
            )
        proc = subprocess.Popen(
            argv,
            cwd=str(_simulator_cwd()),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
    except Exception:
        logger.exception("simulator worker failed to start for run %s", key)
        return False
    _workers[key] = proc
    logger.info("simulator worker started for run %s (pid %s)", key, proc.pid)
    return True


def stop_worker(run_id: UUID) -> bool:
    """Stop the simulator worker for a run. True if stopped/already gone."""
    key = str(run_id)
    proc = _workers.pop(key, None)
    evidence_name = _worker_evidence.pop(key, None)
    if proc is None:
        return False
    if proc.poll() is not None:
        if evidence_name:
            from app.experiments.evidence import producer_stopped
            producer_stopped(run_id, evidence_name, proc.poll(), False)
        return True
    if evidence_name:
        from app.experiments.evidence import directory, producer_stopped
        forced = False
        try:
            (directory(run_id) / f"{evidence_name}.stop").touch()
            exit_code = proc.wait(timeout=15)
        except Exception:
            forced = True
            proc.terminate()
            try:
                exit_code = proc.wait(timeout=3)
            except Exception:
                proc.kill()
                exit_code = proc.wait(timeout=3)
        producer_stopped(run_id, evidence_name, exit_code, forced)
        return True
    try:
        proc.terminate()
        proc.wait(timeout=15)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    logger.info("simulator worker stopped for run %s", key)
    return True


def stop_all_workers() -> None:
    """Best-effort shutdown of every tracked worker (process exit paths)."""
    for key in list(_workers):
        try:
            stop_worker(key)
        except Exception:
            logger.exception("failed to stop simulator worker for run %s", key)
