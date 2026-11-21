"""Run-scoped simulator worker: start/stop lifecycle without real processes."""

import sys
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.experiments import worker


class _Proc:
    def __init__(self):
        self.pid = 4242
        self.terminated = False
        self.killed = False
        self._rc = None

    def poll(self):
        return self._rc

    def terminate(self):
        self.terminated = True
        self._rc = 0

    def wait(self, timeout=None):
        self._rc = 0
        return 0

    def kill(self):
        self.killed = True
        self._rc = -9


def _enable(monkeypatch, value):
    monkeypatch.setenv("COLDCHAIN_SIM_WORKER_ENABLED", value)
    worker._workers.clear()


def test_disabled_by_default_starts_nothing(monkeypatch):
    _enable(monkeypatch, "")
    with patch("subprocess.Popen") as popen:
        assert worker.start_worker(uuid.uuid4()) is False
        popen.assert_not_called()


def test_start_spawns_continuous_simulator(monkeypatch):
    _enable(monkeypatch, "true")
    proc = _Proc()
    with patch("subprocess.Popen", return_value=proc) as popen:
        run_id = uuid.uuid4()
        assert worker.start_worker(run_id) is True
        argv = popen.call_args[0][0]
        assert argv[-2:] == ["--cycles", "0"]
        assert "main.py" in argv[1]
        # second start reuses the running worker
        assert worker.start_worker(run_id) is True
        assert popen.call_count == 1


def test_stop_terminates_and_clears(monkeypatch):
    _enable(monkeypatch, "true")
    proc = _Proc()
    with patch("subprocess.Popen", return_value=proc):
        run_id = uuid.uuid4()
        assert worker.start_worker(run_id) is True
        assert worker.stop_worker(run_id) is True
        assert proc.terminated is True
        # stopping again is a no-op success
        assert worker.stop_worker(run_id) is False


def test_stop_unknown_run_is_noop():
    worker._workers.clear()
    assert worker.stop_worker(uuid.uuid4()) is False


class _Row:
    def __init__(self, snapshot):
        self.config_snapshot = snapshot


class _Query:
    def __init__(self, row):
        self._row = row

    def filter_by(self, **kwargs):
        return self

    def first(self):
        return self._row


class _Session:
    def __init__(self, row):
        self._row = row

    def query(self, *args, **kwargs):
        return _Query(self._row)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _session_factory(row):
    def _factory():
        return _Session(row)
    return _factory


def test_resolve_condition_from_snapshot(monkeypatch):
    import app.database.infrastructure.session as session_module

    monkeypatch.setattr(
        session_module, "SessionLocal",
        _session_factory(_Row('{"sensor_condition": "critica"}')),
    )
    assert worker.resolve_sensor_condition(uuid.uuid4()) == "critica"

    # The UI persists `altered`; it must reach the simulator as `critica`
    # instead of silently omitting the flag.
    monkeypatch.setattr(
        session_module, "SessionLocal",
        _session_factory(_Row('{"sensor_condition": "altered"}')),
    )
    assert worker.resolve_sensor_condition(uuid.uuid4()) == "critica"

    monkeypatch.setattr(
        session_module, "SessionLocal",
        _session_factory(_Row('{"sensor_condition": "normal"}')),
    )
    assert worker.resolve_sensor_condition(uuid.uuid4()) == "normal"


def test_resolve_condition_ignores_missing_or_invalid(monkeypatch):
    import app.database.infrastructure.session as session_module

    monkeypatch.setattr(session_module, "SessionLocal", _session_factory(None))
    assert worker.resolve_sensor_condition(uuid.uuid4()) is None

    monkeypatch.setattr(
        session_module, "SessionLocal", _session_factory(_Row("not-json")),
    )
    assert worker.resolve_sensor_condition(uuid.uuid4()) is None

    monkeypatch.setattr(
        session_module, "SessionLocal",
        _session_factory(_Row('{"sensor_condition": "extrema"}')),
    )
    assert worker.resolve_sensor_condition(uuid.uuid4()) is None


def test_start_passes_condition_flag(monkeypatch):
    _enable(monkeypatch, "true")
    monkeypatch.setattr(worker, "resolve_sensor_condition", lambda run_id: "critica")
    proc = _Proc()
    with patch("subprocess.Popen", return_value=proc) as popen:
        assert worker.start_worker(uuid.uuid4()) is True
        argv = popen.call_args[0][0]
        assert argv[-4:] == ["--cycles", "0", "--condition", "critica"]


def test_start_omits_condition_flag_without_snapshot(monkeypatch):
    _enable(monkeypatch, "true")
    monkeypatch.setattr(worker, "resolve_sensor_condition", lambda run_id: None)
    proc = _Proc()
    with patch("subprocess.Popen", return_value=proc) as popen:
        assert worker.start_worker(uuid.uuid4()) is True
        assert popen.call_args[0][0][-2:] == ["--cycles", "0"]


def test_worker_separates_publication_journal_and_propagates_run_identity(monkeypatch, tmp_path):
    _enable(monkeypatch, "true")
    monkeypatch.setattr(worker, "resolve_sensor_condition", lambda run_id: None)
    backend_path = tmp_path / "backend.jsonl"
    monkeypatch.setattr(worker, "_child_env", lambda: {
        "TELEMETRY_TRACE_FILE": str(backend_path), "TELEMETRY_CLOCK_DOMAIN": "same-host",
    })
    run_id = uuid.uuid4()
    with patch("subprocess.Popen", return_value=_Proc()) as popen:
        assert worker.start_worker(run_id)
        env = popen.call_args.kwargs["env"]
        assert env["COLDCHAIN_RUN_ID"] == str(run_id)
        assert env["TELEMETRY_TRACE_FILE"] != str(backend_path)
        assert str(run_id) in env["TELEMETRY_TRACE_FILE"]
        assert env["TELEMETRY_CLOCK_DOMAIN"] == "same-host"


def test_child_env_prefers_simulator_dotenv(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "MQTT_USERNAME=simulator\nMQTT_PASSWORD=s3cret\nMQTT_CA_CERT=ca.crt\nOTHER=keep\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(worker, "_simulator_cwd", lambda: tmp_path)
    monkeypatch.setenv("MQTT_USERNAME", "backend")
    monkeypatch.delenv("MQTT_PASSWORD", raising=False)
    env = worker._child_env()
    assert env["MQTT_USERNAME"] == "simulator"
    assert env["MQTT_PASSWORD"] == "s3cret"
    assert env["MQTT_CA_CERT"] == "ca.crt"
    assert "OTHER" not in env


def test_managed_worker_uses_cooperative_stop_and_records_exit(monkeypatch, tmp_path):
    from app.experiments import evidence
    from app.experiments.tests.test_evidence import _capture
    monkeypatch.setenv("TELEMETRY_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.delenv("TELEMETRY_TRACE_FILE", raising=False)
    _enable(monkeypatch, "true")
    run, _unused_name, _env = _capture()
    monkeypatch.setattr(worker, "resolve_sensor_condition", lambda run_id: None)
    monkeypatch.setattr(worker, "_child_env", lambda: {})
    proc = _Proc()
    with patch("subprocess.Popen", return_value=proc):
        assert worker.start_worker(run.id)
    name = evidence.manifest(run.id)["producers"][-1]["name"]
    assert worker.stop_worker(run.id)
    assert not proc.terminated
    assert (evidence.directory(run.id) / f"{name}.stop").exists()
    captured = evidence.manifest(run.id)["producers"][-1]
    assert captured["exit_code"] == 0
    assert captured["forced"] is False


def test_managed_worker_timeout_is_recorded_as_forced(monkeypatch, tmp_path):
    from app.experiments import evidence
    from app.experiments.tests.test_evidence import _capture
    monkeypatch.setenv("TELEMETRY_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.delenv("TELEMETRY_TRACE_FILE", raising=False)
    _enable(monkeypatch, "true")
    run, _unused_name, _env = _capture()
    monkeypatch.setattr(worker, "resolve_sensor_condition", lambda run_id: None)
    monkeypatch.setattr(worker, "_child_env", lambda: {})

    class Slow(_Proc):
        def wait(self, timeout=None):
            if not self.terminated:
                raise worker.subprocess.TimeoutExpired("controlled", timeout)
            return super().wait(timeout)

    proc = Slow()
    with patch("subprocess.Popen", return_value=proc):
        assert worker.start_worker(run.id)
    assert worker.stop_worker(run.id)
    assert proc.terminated
    assert evidence.manifest(run.id)["producers"][-1]["forced"] is True
