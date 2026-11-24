import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.acquisition.telemetry_trace import record_trace
from app.experiments import active, evidence
from app.experiments.tests.test_experiment_api import _factory, _client
from app.database.infrastructure.models import ExperimentRunORM, DeviceORM, SensorReadingORM, TrafficClassificationORM
from simulator.mqtt.trace import record_trace as sender_trace


@pytest.fixture(autouse=True)
def isolated_capture(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEMETRY_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.delenv("TELEMETRY_TRACE_FILE", raising=False)
    monkeypatch.delenv("COLDCHAIN_MANAGED_EVIDENCE", raising=False)
    active.clear_active_run()
    yield
    active.clear_active_run()


def _capture():
    now = datetime.now(timezone.utc)
    run = SimpleNamespace(id=uuid4(), started_at=now - timedelta(seconds=20), finished_at=None)
    config = SimpleNamespace(
        telemetry_evidence_enabled=True, telemetry_evidence_grace_s=2,
        effective_qos_config=lambda: {"wfq_policy": "criticality_bands_v1",
                                     "class_quotas": {"high": 4, "medium": 2, "low": 1},
                                     "wfq_band_weights": {"H7": 1, "H8": 2, "H9": 3}},
    )
    evidence.start_capture(run, config)
    env = {}
    name = evidence.producer_environment(run.id, env)
    return run, name, env


def _send(monkeypatch, run, name, env, count=2, receive=1):
    started = datetime.now(timezone.utc) - timedelta(seconds=10)
    monkeypatch.setenv("TELEMETRY_TRACE_FILE", env["TELEMETRY_TRACE_FILE"])
    sender_trace("producer_opened", run_id=str(run.id))
    messages = []
    for sequence in range(count):
        trace = {
            "message_id": str(uuid4()), "producer_session_id": "00000000-0000-0000-0000-000000000001",
            "sequence": sequence, "run_id": str(run.id), "clock_domain": env["TELEMETRY_CLOCK_DOMAIN"],
        }
        message = {"trace": trace, "device_code": "TEST", "size_bytes": 521,
                   "event_at": started.isoformat(), "generated_at": started.isoformat()}
        messages.append(message)
        sender_trace("publish_attempt", **message)
        sender_trace("publish_complete", **message)
    sender_trace("producer_closed", run_id=str(run.id), pending_publications=0)
    monkeypatch.delenv("TELEMETRY_TRACE_FILE")
    for message in messages[:receive]:
        record_trace("received", **message, received_at=(started + timedelta(seconds=1)).isoformat())
    return messages


def _close(run, name, forced=False):
    evidence.producer_stopped(run.id, name, -15 if forced else 0, forced)
    value = evidence.manifest(run.id)
    value["emission_ended_at"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    evidence._save(run.id, value)
    run.finished_at = datetime.now(timezone.utc)
    evidence.seal_capture(run.id)


def test_missing_capture_does_not_import_campaign_or_invent_delivery():
    run = SimpleNamespace(id=uuid4(), finished_at=None)
    result = evidence.report_for_run(run)
    assert result["status"] == "unavailable"
    assert result["pdr_percent"] is result["pending_messages"] is None
    assert result["counts"] == {}


def test_final_report_uses_real_journals_and_measured_loss(monkeypatch):
    run, name, env = _capture()
    _send(monkeypatch, run, name, env)
    _close(run, name)
    result = evidence.report_for_run(run)
    assert result["status"] == "final"
    assert result["pdr_percent"] == result["loss_percent"] == 50
    assert result["counts"]["sent_unique"] == 2
    assert result["counts"]["received_unique"] == 1
    assert result["received_payload_bytes"] == 521
    assert result["pending_messages"] == 1


def test_active_run_does_not_call_missing_receipt_a_final_loss(monkeypatch):
    run, name, env = _capture()
    _send(monkeypatch, run, name, env)
    result = evidence.report_for_run(run)
    assert result["status"] == "in_progress"
    assert result["pending_messages"] == 1
    assert result["pdr_percent"] is result["loss_percent"] is None
    assert result["payload_goodput_bytes_per_second"] is None


def test_duplicate_receipts_do_not_inflate_pdr_or_bytes(monkeypatch):
    run, name, env = _capture()
    messages = _send(monkeypatch, run, name, env, count=1, receive=1)
    record_trace("received", **messages[0], received_at=messages[0]["event_at"])
    _close(run, name)
    result = evidence.report_for_run(run)
    assert result["pdr_percent"] == 100
    assert result["counts"]["duplicate_receptions"] == 1
    assert result["received_payload_bytes"] == 521


def test_forced_producer_termination_cannot_certify_complete_capture(monkeypatch):
    run, name, env = _capture()
    _send(monkeypatch, run, name, env)
    _close(run, name, forced=True)
    result = evidence.report_for_run(run)
    assert result["status"] == "incomplete"
    assert result["pdr_percent"] is None


@pytest.mark.parametrize("damage", ["partial", "missing", "sequence_gap"])
def test_corrupt_or_missing_capture_never_publishes_rates(monkeypatch, damage):
    run, name, env = _capture()
    _send(monkeypatch, run, name, env)
    _close(run, name)
    path = evidence.directory(run.id) / name
    if damage == "partial":
        with path.open("a") as stream:
            stream.write('{"unfinished":')
    elif damage == "missing":
        path.unlink()  # This test's own temporary journal only.
    else:
        rows = path.read_text().splitlines()
        path.write_text("\n".join(rows[:1] + rows[2:]) + "\n")
    result = evidence.report_for_run(run)
    assert result["status"] == "incomplete"
    assert result["pdr_percent"] is None


def test_grace_deadline_does_not_move_when_finish_is_retried():
    run, name, env = _capture()
    assert evidence.request_close(run.id) == evidence.request_close(run.id)


def test_backend_restart_without_old_session_footer_is_incomplete(monkeypatch):
    import app.acquisition.telemetry_trace as tracing
    run, name, env = _capture()
    _send(monkeypatch, run, name, env)
    monkeypatch.setattr(tracing, "_session", uuid4().hex)
    # A restarted writer has a new sequence within its new process session.
    monkeypatch.setattr(tracing, "_sequences", {})
    _close(run, name)
    result = evidence.report_for_run(run)
    assert result["status"] == "incomplete"
    assert result["pdr_percent"] is None


def test_unconfirmed_seal_does_not_remain_provisional_forever(monkeypatch):
    run, name, env = _capture()
    _send(monkeypatch, run, name, env)
    _close(run, name)
    value = evidence.manifest(run.id)
    value["sealed"] = False
    evidence._save(run.id, value)
    result = evidence.report_for_run(run)
    assert result["status"] == "incomplete"
    assert result["pdr_percent"] is None


def test_commit_after_reception_grace_is_not_removed_from_end_to_end_latency(monkeypatch):
    run, name, env = _capture()
    messages = _send(monkeypatch, run, name, env)
    committed = datetime.now(timezone.utc) - timedelta(seconds=1)
    generated = datetime.fromisoformat(messages[0]["generated_at"])
    record_trace("persisted", run_id=str(run.id),
                 source_message_id=messages[0]["trace"]["message_id"],
                 work_id=str(uuid4()), sensor_name="temperature", priority="high",
                 generated_at=generated.isoformat(), committed_at=committed.isoformat(),
                 alerts=[{"alert_id": str(uuid4())}])
    _close(run, name)
    result = evidence.report_for_run(run)
    assert committed > datetime.fromisoformat(result["window"]["reception_deadline"])
    assert result["device_to_persist_ms"]["count"] == 1
    assert result["device_to_persist_ms"]["mean"] == (committed - generated).total_seconds() * 1000
    assert result["device_to_alert_persist_ms"]["count"] == 1


def test_get_evidence_is_authenticated_and_has_no_public_file_paths(monkeypatch):
    factory = _factory()
    run, name, env = _capture()
    _send(monkeypatch, run, name, env)
    _close(run, name)
    with factory.begin() as db:
        db.add(ExperimentRunORM(id=run.id, scenario="WITH_QOS",
                                started_at=run.started_at, finished_at=run.finished_at))
    client = _client(factory)
    response = client.get(f"/experiment-runs/{run.id}/evidence")
    assert response.status_code == 200, response.text
    assert response.json()["pdr_percent"] == 50
    assert response.json()["counts"]["database_readings_persisted"] == 0
    assert "producer-" not in response.text
    assert str(evidence.directory(run.id)) not in response.text
    assert client.get(f"/experiment-runs/{uuid4()}/evidence").status_code == 404
    from app.auth.dependencies import get_current_user
    client.app.dependency_overrides.pop(get_current_user)
    assert client.get(f"/experiment-runs/{run.id}/evidence").status_code in (401, 403)


def test_fifo_evaluation_labels_are_read_only_and_do_not_create_classifications(monkeypatch):
    factory = _factory()
    run, name, env = _capture()
    messages = _send(monkeypatch, run, name, env, count=1, receive=1)
    source_id = messages[0]["trace"]["message_id"]
    work_id, device_id = uuid4(), uuid4()
    generated = messages[0]["generated_at"]
    record_trace("persisted", run_id=str(run.id), source_message_id=source_id,
                 work_id=str(work_id), sensor_name="temperature", priority=None,
                 generated_at=generated,
                 committed_at=(datetime.fromisoformat(generated) + timedelta(seconds=2)).isoformat(),
                 alerts=[])
    _close(run, name)
    with factory.begin() as db:
        db.add(ExperimentRunORM(id=run.id, scenario="WITHOUT_QOS",
                                started_at=run.started_at, finished_at=run.finished_at))
        db.add(DeviceORM(id=device_id, code="TEST", name="Test", location="test",
                         device_type="cold_room", status="active"))
        db.flush()
        db.add(SensorReadingORM(id=work_id, device_id=device_id, run_id=run.id,
                               source_message_id=UUID(source_id), sensor_name="temperature",
                               temperature=9.5, processing_version=2))
    response = _client(factory).get(f"/experiment-runs/{run.id}/evidence")
    assert response.status_code == 200, response.text
    assert response.json()["by_priority"]["high"]["persist"] == {
        "count": 1, "mean": 2000, "p95": 2000,
    }
    with factory() as db:
        assert db.query(TrafficClassificationORM).count() == 0


def test_client_metadata_cannot_select_evidence_directory(monkeypatch):
    from app.auth.dependencies import AuthenticatedUser
    from app.security.dependencies import require_admin
    import app.experiments.api as api

    factory = _factory()
    client = _client(factory)
    client.app.dependency_overrides[require_admin] = lambda: AuthenticatedUser(
        id=uuid4(), email="admin@invalid", name="Admin", role="admin", is_active=True,
    )
    client.app.state.backend_config = SimpleNamespace(
        telemetry_evidence_enabled=True, telemetry_evidence_grace_s=2,
        effective_qos_config=lambda: {},
    )
    monkeypatch.setattr(api, "start_worker", lambda run_id: False)
    response = client.post("/experiment-runs", json={
        "scenario": "WITH_QOS",
        "config_snapshot": {"telemetry_evidence": {"directory": "../../outside", "enabled": False}},
    })
    assert response.status_code == 201, response.text
    data = response.json()
    assert json.loads(data["config_snapshot"])["telemetry_evidence"]["enabled"] is True
    assert evidence.directory(data["id"]).is_dir()


def test_finish_closes_admission_before_stopping_producer_and_grace(monkeypatch):
    import app.experiments.api as api
    from app.auth.dependencies import AuthenticatedUser
    from app.security.dependencies import require_admin
    factory = _factory()
    run, name, env = _capture()
    _send(monkeypatch, run, name, env, count=1, receive=1)
    with factory.begin() as db:
        db.add(ExperimentRunORM(id=run.id, scenario="WITH_QOS", started_at=run.started_at))
    client = _client(factory)
    client.app.dependency_overrides[require_admin] = lambda: AuthenticatedUser(
        id=uuid4(), email="admin@invalid", name="Admin", role="admin", is_active=True,
    )
    order = []
    client.app.state.dispatch_coordinator = SimpleNamespace(
        begin_drain=lambda run_id: order.append("dispatch_drain"),
        wait_until_idle=lambda timeout: True, end_drain=lambda: None,
    )
    client.app.state.message_queue = SimpleNamespace(
        begin_drain=lambda run_id: order.append("transport_drain"),
        wait_run_ingested=lambda run_id, timeout: True, end_drain=lambda run_id: None,
    )

    def stop(run_id):
        order.append("stop")
        evidence.producer_stopped(run_id, name, 0, False)

    monkeypatch.setattr(api, "stop_worker", stop)
    monkeypatch.setattr(api.time, "sleep", lambda seconds: order.append("grace"))
    result = client.post(f"/experiment-runs/{run.id}/finish")
    assert result.status_code == 200, result.text
    assert order[:4] == ["transport_drain", "dispatch_drain", "stop", "grace"]
    assert evidence.manifest(run.id)["sealed"] is True
