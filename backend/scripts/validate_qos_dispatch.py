"""Deterministic, offline scheduler corpus; prints JSON to stdout.

No database, MQTT, notifications or wall-clock latency is used. This is
selection evidence only, not an end-to-end benchmark.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.qos.application.dispatcher import DispatchCoordinator
from app.qos.application.traffic_planning_service import TrafficPlanningService
from app.qos.domain.work_item import WorkItem

STAMP = datetime(2026, 1, 1, tzinfo=timezone.utc)
CLASSES = (
    ("energy", 1.0, "on", "low", 3.0, "FIFO"),
    ("humidity", 82.0, 82.0, "medium", 6.0, "Round Robin"),
    ("temperature", 9.5, 9.5, "high", 9.0, "WFQ"),
)


def run_case(scenario: str, messages: int) -> dict:
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=messages * 3)
    corpus = []
    for message in range(messages):
        source = uuid5(NAMESPACE_URL, f"coldchain-corpus/message/{message}")
        for sensor, value, raw, priority, criticality, queue in CLASSES:
            sequence = len(corpus)
            work_id = uuid5(NAMESPACE_URL, f"coldchain-corpus/reading/{sequence}")
            reading = NormalizedReading(
                f"CAVA-{message % 2 + 1:03}", "cold_room", sensor, value,
                STAMP.isoformat(), raw,
            )
            classification = None
            if scenario == "WITH_QOS":
                classification = TrafficClassification(
                    id=uuid5(NAMESPACE_URL, f"coldchain-corpus/class/{sequence}"),
                    reading_id=work_id, criticality=criticality, priority=priority,
                    queue=queue, classification_time=STAMP, timestamp=STAMP,
                )
            work = WorkItem.from_reading(
                reading, id=work_id, source_message_id=source, sequence=sequence,
                scenario=scenario, run_id=None, admitted_at=STAMP,
                admitted_monotonic=float(sequence), classification=classification,
            )
            assert coordinator.admit(work)
            corpus.append((work, priority))

    labels = {work.id: label for work, label in corpus}
    trace = []
    while (item := coordinator.select_next()) is not None:
        trace.append({
            "selection": len(trace), "sequence": item.sequence,
            "reading_id": str(item.id), "message_id": str(item.source_message_id),
            "device": item.device_code, "sensor": item.sensor_name,
            "evaluation_class": labels[item.id],
            "dispatch_priority": item.priority,
        })
        coordinator.finish(success=True)
    assert len(trace) == len(corpus)
    if scenario == "WITHOUT_QOS":
        assert [entry["sequence"] for entry in trace] == list(range(len(corpus)))
    return {
        "scenario": scenario, "messages": messages, "readings": len(corpus),
        "selected_by_evaluation_class": dict(sorted(Counter(
            entry["evaluation_class"] for entry in trace
        ).items())),
        "final_dispatch": coordinator.snapshot(), "selection_trace": trace,
    }


def main() -> None:
    report = {
        "version": 1,
        "kind": "offline_deterministic_selection_only",
        "policy": {"high": 4, "medium": 2, "low": 1},
        "wfq_weights": "default unit weights", "cost": "one reading",
        "arrival": "all readings admitted before selection; low, medium, high per message",
        "measurements": None,
        "limitations": [
            "Evaluation classes are fixed corpus labels, not calculated classifier results.",
            "No event, persistence, notification, MQTT, database, wall-clock latency or throughput measured.",
            "All readings are pre-admitted; this is not a real-time load experiment.",
        ],
        "cases": [run_case(scenario, count)
                  for count in (1, 7, 21)
                  for scenario in ("WITH_QOS", "WITHOUT_QOS")],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
