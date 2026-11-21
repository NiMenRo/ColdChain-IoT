import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _runner():
    path = Path(__file__).resolve().parents[3] / "scripts" / "validate_telemetry_campaign.py"
    spec = importlib.util.spec_from_file_location("campaign_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_campaign_requires_explicit_execution_and_output(monkeypatch):
    module = _runner()
    monkeypatch.setattr("sys.argv", ["validate_telemetry_campaign.py"])
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 2


def test_existing_output_directory_is_never_overwritten(monkeypatch, tmp_path):
    module = _runner()
    sentinel = tmp_path / "preserve.json"
    sentinel.write_text("user evidence", encoding="utf-8")
    monkeypatch.setattr(module, "docker", lambda *args: pytest.fail("must not start containers"))
    with pytest.raises(FileExistsError):
        module.campaign(tmp_path)
    assert sentinel.read_text(encoding="utf-8") == "user evidence"


def test_docker_error_does_not_expose_password_or_command(monkeypatch):
    module = _runner()
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=1, stdout="", stderr="diagnostic with sensitive-value",
    ))
    with pytest.raises(RuntimeError) as exc:
        module.docker("run", "-e", "PASSWORD=sensitive-value")
    assert str(exc.value) == "Docker run failed (exit 1)"


def test_real_corpus_uses_only_reachable_priorities_without_injecting_weights():
    module = _runner()
    from app.acquisition.normalizer import NormalizedReading
    from app.classification.application.risk_matrix_evaluator import RiskMatrixEvaluator
    from app.classification.application.criticality_calculator import CriticalityCalculator

    evaluator = RiskMatrixEvaluator()
    scores = set()
    for values in module.MIXED:
        for sensor, value in values.items():
            reading = NormalizedReading(
                "CAMPAIGN-001", "cold_room", sensor,
                float(value) if sensor != "energy" else float(value == "on"),
                "2026-11-20T12:00:00+00:00", value,
            )
            criteria = evaluator.evaluate(reading)
            scores.add(CriticalityCalculator().calculate(
                criteria.impact, criteria.urgency, criteria.risk,
            ))
    assert scores == {3, 6, 8, 9}


def test_offline_analysis_labels_baseline_without_inventing_runtime_classifications():
    path = Path(__file__).resolve().parents[3] / "scripts" / "summarize_telemetry_campaign.py"
    spec = importlib.util.spec_from_file_location("campaign_summary", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.score("temperature", 9.5) == 9
    assert module.score("humidity", 75) == 8
    assert module.score("energy", "on") == 3
    assert module.stats([]) == {"count": 0, "mean_ms": None, "p95_ms": None}
