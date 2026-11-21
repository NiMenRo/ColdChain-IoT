"""Read-only reconciliation; prints JSON, never starts services or changes SQL."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.qos.application.telemetry_evidence import reconcile


def _read(paths):
    rows = []
    for name in paths:
        with Path(name).open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("event is not an object")
                    rows.append(row)
                except ValueError as exc:
                    raise ValueError(f"{name}:{number}: corrupt evidence ({exc})") from exc
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer", nargs="+", required=True)
    parser.add_argument("--backend", nargs="+", required=True)
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    parser.add_argument("--observed-until", required=True, type=datetime.fromisoformat)
    parser.add_argument("--grace-seconds", required=True, type=float)
    parser.add_argument("--run-id")
    parser.add_argument("--confirm-complete-capture", action="store_true")
    args = parser.parse_args()
    try:
        report = reconcile(
            _read(args.producer), _read(args.backend), started_at=args.start,
            emission_ended_at=args.end, observed_until=args.observed_until,
            grace_seconds=args.grace_seconds, run_id=args.run_id,
            complete_capture=args.confirm_complete_capture,
        )
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
