import importlib.util
import json
from pathlib import Path

import pytest

from app.qos.tests.test_telemetry_evidence import NOW, _message, _producer, _receipt


def _cli():
    path = Path(__file__).resolve().parents[3] / "scripts" / "reconcile_telemetry.py"
    spec = importlib.util.spec_from_file_location("reconcile_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(producer, backend):
    return [
        "reconcile_telemetry.py", "--producer", str(producer), "--backend", str(backend),
        "--start", NOW.isoformat(), "--end", "2026-11-20T12:00:05+00:00",
        "--observed-until", "2026-11-20T12:00:10+00:00", "--grace-seconds", "5",
        "--confirm-complete-capture",
    ]


def test_cli_reads_journals_and_returns_real_payload_counts(monkeypatch, tmp_path, capsys):
    first, lost = _message(), _message()
    sender = tmp_path / "sender.jsonl"
    receiver = tmp_path / "receiver.jsonl"
    sender.write_text("\n".join(json.dumps(row) for row in _producer(first) + _producer(lost)),
                      encoding="utf-8")
    receiver.write_text(json.dumps(_receipt(first)), encoding="utf-8")
    monkeypatch.setattr("sys.argv", _args(sender, receiver))
    _cli().main()
    result = json.loads(capsys.readouterr().out)
    assert result["pdr_percent"] == 50
    assert result["payload_goodput_bytes_per_second"] == 23.7


def test_cli_rejects_partial_or_corrupt_journals(monkeypatch, tmp_path, capsys):
    sender = tmp_path / "sender.jsonl"
    receiver = tmp_path / "receiver.jsonl"
    sender.write_text('{"event":', encoding="utf-8")
    receiver.write_text("", encoding="utf-8")
    monkeypatch.setattr("sys.argv", _args(sender, receiver))
    with pytest.raises(SystemExit) as exc:
        _cli().main()
    assert exc.value.code == 2
    assert "corrupt evidence" in capsys.readouterr().err
