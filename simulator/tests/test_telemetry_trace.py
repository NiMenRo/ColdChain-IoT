import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from simulator.mqtt.client import MQTTClient
from simulator.mqtt.publisher import DevicePublisher
from simulator.tests.test_publisher_single_read import FakeMQTTClient, _make_device


def test_producer_assigns_sequences_before_receiving_anything(monkeypatch):
    monkeypatch.delenv("COLDCHAIN_RUN_ID", raising=False)
    device, _ = _make_device()
    fake = FakeMQTTClient()
    publisher = DevicePublisher(fake)
    publisher.publish_telemetry(device)
    publisher.publish_telemetry(device)
    first, second = [payload["trace"] for _, payload, _ in fake.published]
    assert first["sequence"] == 0
    assert second["sequence"] == 1
    assert first["producer_session_id"] == second["producer_session_id"]
    assert UUID(first["message_id"]) != UUID(second["message_id"])
    restarted = DevicePublisher(fake)
    restarted.publish_telemetry(device)
    assert fake.published[-1][1]["trace"]["sequence"] == 0
    assert fake.published[-1][1]["trace"]["producer_session_id"] != first["producer_session_id"]


def test_actual_utf8_bytes_and_synchronous_qos_zero_completion_are_recorded(monkeypatch, tmp_path):
    target = tmp_path / "sender.jsonl"
    monkeypatch.setenv("TELEMETRY_TRACE_FILE", str(target))
    with patch("simulator.mqtt.client.mqtt.Client") as factory:
        transport = factory.return_value
        client = MQTTClient("unused", 8883)
        payload = {"device_code": "CÁMARA", "trace": None, "temperature": 3}

        def complete(topic, wire_payload, qos):
            assert isinstance(wire_payload, bytes)
            assert json.loads(wire_payload) == payload
            client._on_publish(transport, None, 4, SimpleNamespace(is_failure=False), None)
            return SimpleNamespace(rc=0, mid=4)

        transport.publish.side_effect = complete
        assert client.publish("unused", payload)
        rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
        assert [row["event"] for row in rows] == [
            "publish_attempt", "publish_complete", "publish_accepted",
        ]
        wire = transport.publish.call_args.args[1]
        assert all(row["size_bytes"] == len(wire) for row in rows)
        assert not client._pending_publications


def test_async_completion_is_distinct_from_library_acceptance(monkeypatch, tmp_path):
    target = tmp_path / "sender.jsonl"
    monkeypatch.setenv("TELEMETRY_TRACE_FILE", str(target))
    with patch("simulator.mqtt.client.mqtt.Client") as factory:
        factory.return_value.publish.return_value = SimpleNamespace(rc=0, mid=12)
        client = MQTTClient("unused", 8883)
        assert client.publish("unused", {"device_code": "A"})
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        assert [row["event"] for row in rows] == ["publish_attempt", "publish_accepted"]
        client._on_publish(None, None, 12, SimpleNamespace(is_failure=False), None)
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        assert rows[-1]["event"] == "publish_complete"
        assert not client._pending_publications


def test_publication_failure_records_no_completion(monkeypatch, tmp_path):
    target = tmp_path / "sender.jsonl"
    monkeypatch.setenv("TELEMETRY_TRACE_FILE", str(target))
    with patch("simulator.mqtt.client.mqtt.Client") as factory:
        factory.return_value.publish.return_value = SimpleNamespace(rc=4, mid=12)
        client = MQTTClient("unused", 8883)
        assert not client.publish("unused", {"device_code": "A"})
        assert [json.loads(line)["event"] for line in target.read_text().splitlines()] == [
            "publish_attempt", "publish_error",
        ]


def test_trace_disabled_has_no_files_or_external_effects(monkeypatch):
    monkeypatch.delenv("TELEMETRY_TRACE_FILE", raising=False)
    from simulator.mqtt.trace import record_trace
    assert record_trace("publish_attempt", size_bytes=1) is False


def test_managed_client_writes_open_and_closed_evidence(monkeypatch, tmp_path):
    target = tmp_path / "managed.jsonl"
    monkeypatch.setenv("TELEMETRY_TRACE_FILE", str(target))
    monkeypatch.setenv("COLDCHAIN_MANAGED_EVIDENCE", "true")
    with patch("simulator.mqtt.client.mqtt.Client"):
        client = MQTTClient("unused", 8883)
        client.start()
        client.stop()
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    assert [row["event"] for row in rows] == ["producer_opened", "producer_closed"]
    assert rows[-1]["pending_publications"] == 0
    assert [row["journal_sequence"] for row in rows] == [1, 2]


def test_stop_signal_interrupts_sampling_and_prevents_new_publications(monkeypatch, tmp_path):
    from simulator import main
    stop = tmp_path / "producer.stop"
    stop.touch()
    monkeypatch.setenv("COLDCHAIN_STOP_FILE", str(stop))
    monkeypatch.setattr(main.time, "sleep", lambda value: (_ for _ in ()).throw(
        AssertionError("must not sleep after stop signal")))
    main._sampling_pause(100)
    main._publish_all_devices([object()], object())
