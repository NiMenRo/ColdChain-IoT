"""Shared experiment-metric recording (TSK-059.7).

Single helper used by the pipeline and the MQTT subscriber so counters come
from the real events (enqueue, invalid, persist, alerts). Only called with an
active run id; without a run nothing is touched (legacy behavior).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


def record_metrics(
    run_id: UUID | None, entries: list[tuple[str, float, datetime | None]]
) -> None:
    """Persist common experiment metrics in their own transaction.

    entries: (metric_type, value, timestamp|None). Failures are logged only so
    telemetry is never blocked by metrics. MessageQueue stays transport-only.
    """
    if run_id is None or not entries:
        return
    try:
        from app.database.infrastructure.repositories import ExperimentMetricRepository
        from app.database.infrastructure.session import SessionLocal

        repo = ExperimentMetricRepository()
        with SessionLocal() as db:
            with db.begin():
                for metric_type, value, ts in entries:
                    repo.append(
                        db,
                        run_id=run_id,
                        metric_type=metric_type,
                        value=value,
                        timestamp=ts,
                    )
    except Exception:
        logger.exception("Failed to record experiment metrics for run %s", run_id)
