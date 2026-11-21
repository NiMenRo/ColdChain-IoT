"""Read-only campaign analysis, including OFFLINE labels for the FIFO baseline."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
from collections import defaultdict
from datetime import datetime
from math import ceil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.acquisition.normalizer import NormalizedReading
from app.classification.application.criticality_calculator import CriticalityCalculator
from app.classification.application.risk_matrix_evaluator import RiskMatrixEvaluator


def stats(values):
    ordered = sorted(values)
    return {
        "count": len(values), "mean_ms": sum(values) / len(values) if values else None,
        "p95_ms": ordered[ceil(len(ordered) * 0.95) - 1] if ordered else None,
    }


def score(sensor, value):
    """Evaluation label only; never create a classification in WITHOUT_QOS."""
    reading = NormalizedReading(
        "CAMPAIGN-001", "cold_room", sensor,
        float(value) if sensor != "energy" else float(value == "on"),
        "2026-11-20T00:00:00+00:00", value,
    )
    criteria = RiskMatrixEvaluator().evaluate(reading)
    return CriticalityCalculator().calculate(criteria.impact, criteria.urgency, criteria.risk)


def events(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def summarize(directory):
    campaign = json.loads((directory / "campaign.json").read_text(encoding="utf-8"))
    cases = []
    groups = defaultdict(list)
    for case in campaign["cases"]:
        case_dir = directory / case["directory"]
        corpus_by_message = {}
        for manifest_path in sorted(case_dir.glob("producer-*.manifest.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # foo.manifest.json -> foo.jsonl
            sender_path = manifest_path.with_name(manifest_path.name.replace(".manifest.json", ".jsonl"))
            for row in events(sender_path):
                if row["event"] == "publish_attempt":
                    corpus_by_message[row["trace"]["message_id"]] = manifest["corpus"][row["trace"]["sequence"]]
        by_score, by_class = defaultdict(list), defaultdict(list)
        for row in events(case_dir / "backend.jsonl"):
            if row["event"] != "persisted":
                continue
            values = corpus_by_message[row["source_message_id"]]
            measured = (
                datetime.fromisoformat(row["committed_at"])
                - datetime.fromisoformat(row["generated_at"])
            ).total_seconds() * 1000
            if measured < 0:
                raise ValueError("Negative end-to-end latency")
            criticality = score(row["sensor_name"], values[row["sensor_name"]])
            priority = "high" if criticality >= 7 else "medium" if criticality >= 4 else "low"
            by_score[str(criticality)].append(measured)
            by_class[priority].append(measured)
        item = {
            "label": case["label"], "scenario": case["scenario"], "repetition": case["repetition"],
            "run_id": case["run_id"], "pdr_percent": case["reconciliation"]["pdr_percent"],
            "loss_percent": case["reconciliation"]["loss_percent"],
            "payload_goodput_bytes_per_second": case["reconciliation"]["payload_goodput_bytes_per_second"],
            "counts": case["reconciliation"]["counts"],
            "database_readings": case["database_readings"], "database_alerts": case["database_alerts"],
            "device_to_persist_ms_by_evaluation_class": {key: stats(values) for key, values in by_class.items()},
            "device_to_persist_ms_by_evaluation_criticality": {key: stats(values) for key, values in by_score.items()},
            "preloaded_attention": case["preloaded_attention"],
            "selection_prefix_100_by_criticality": case["selection_prefix_100_by_criticality"],
        }
        cases.append(item)
        if case["label"] in ("paced_10_messages_s", "burst"):
            groups[(case["label"], case["scenario"])].append(item)
    comparisons = []
    for (label, scenario), runs in groups.items():
        per_class = {}
        for priority in ("high", "medium", "low"):
            means = [row["device_to_persist_ms_by_evaluation_class"][priority]["mean_ms"] for row in runs]
            per_class[priority] = {
                "mean_of_run_means_ms": sum(means) / len(means),
                "min_run_mean_ms": min(means), "max_run_mean_ms": max(means),
            }
        comparisons.append({
            "label": label, "scenario": scenario, "repetitions": len(runs),
            "sent_unique": sum(row["counts"]["sent_unique"] for row in runs),
            "received_unique": sum(row["counts"]["received_unique"] for row in runs),
            "database_readings": sum(row["database_readings"] for row in runs),
            "device_to_persist_ms_by_evaluation_class": per_class,
        })
    return {
        "cases": cases, "comparisons": comparisons,
        "environment": {
            "platform": platform.platform(), "python": platform.python_version(),
            "packages": {name: importlib.metadata.version(name)
                         for name in ("paho-mqtt", "SQLAlchemy", "psycopg", "alembic")},
        },
        "source_sha256": {
            name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
            for name in (
                "backend/scripts/validate_telemetry_campaign.py",
                "backend/scripts/summarize_telemetry_campaign.py",
                "backend/app/acquisition/pipeline.py",
                "backend/app/acquisition/telemetry_trace.py",
                "backend/app/qos/application/wfq_scheduler.py",
                "backend/app/qos/application/telemetry_evidence.py",
                "simulator/mqtt/client.py", "simulator/mqtt/publisher.py",
                "simulator/mqtt/trace.py",
            )
        },
        "limitations": campaign["limitations"] + [
            "Evaluation labels are derived offline from the saved input corpus, including WITHOUT_QOS.",
            "No universal performance improvement or statistical significance is inferred from three repetitions.",
            "Goodput uses the declared emission-plus-grace window, not maximum service capacity.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.directory), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
