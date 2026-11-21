"""Complete run aggregates with a bounded plotting representation.

One streamed SELECT includes every row visible to that statement; only chart
points are grouped. No page ceiling or synthetic samples fill missing types.
"""

from datetime import datetime, timezone
from math import floor, isfinite

from app.database.infrastructure.models import ExperimentMetricORM

COUNTERS = {
    "messages_received", "messages_invalid", "messages_rejected_transport",
    "readings_persisted", "alerts_generated", "readings_admitted",
    "readings_rejected", "readings_failed",
}


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def analyze_run(db, run, max_points=300, bucket_seconds=None):
    started = _utc(run.started_at)
    observed = datetime.now(timezone.utc)
    ended = _utc(run.finished_at) if run.finished_at else observed
    width = max((ended - started).total_seconds() / max_points, bucket_seconds or 0, 0.001)
    buckets, stats = {}, {}
    query = db.query(
        ExperimentMetricORM.metric_type, ExperimentMetricORM.value, ExperimentMetricORM.timestamp,
    ).filter(ExperimentMetricORM.run_id == run.id).order_by(
        ExperimentMetricORM.timestamp, ExperimentMetricORM.id,
    ).yield_per(1000)
    total = 0
    for metric_type, value, timestamp in query:
        if not isfinite(value):
            raise ValueError("La ejecución contiene mediciones no válidas.")
        total += 1
        item = stats.setdefault(metric_type, {"count": 0, "sum": 0.0, "mean": None, "max": value, "latest": value})
        item["count"] += 1
        item["sum"] += value
        item["max"] = max(item["max"], value)
        item["latest"] = value
        elapsed = (_utc(timestamp) - started).total_seconds()
        index = max(0, min(max_points - 1, floor(elapsed / width)))
        bucket = buckets.setdefault(metric_type, {}).setdefault(
            index, {"count": 0, "sum": 0.0, "max": value},
        )
        bucket["count"] += 1
        bucket["sum"] += value
        bucket["max"] = max(bucket["max"], value)
    series = {}
    for metric_type, item in stats.items():
        item["mean"] = item["sum"] / item["count"]
        series[metric_type] = [
            {"elapsedMin": (index + 0.5) * width / 60,
             "start_seconds": index * width, "end_seconds": (index + 1) * width,
             "value": bucket["sum"] if metric_type in COUNTERS else bucket["sum"] / bucket["count"],
             "max": bucket["max"], "count": bucket["count"]}
            for index, bucket in sorted(buckets[metric_type].items())
        ]
    return {
        "run_id": str(run.id), "total_samples": total, "provisional": run.finished_at is None,
        "max_points": max_points, "bucket_seconds": width, "metrics": stats, "series": series,
    }
