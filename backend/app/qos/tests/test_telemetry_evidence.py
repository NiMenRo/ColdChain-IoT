from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.qos.application.telemetry_evidence import reconcile

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)


def _message(sequence=0, session=None):
    return {
        "trace_version": 1, "event_at": NOW.isoformat(), "size_bytes": 237,
        "device_code": "CAVA-001", "generated_at": (NOW - timedelta(seconds=1)).isoformat(),
        "trace": {"message_id": str(uuid4()), "producer_session_id": session or str(uuid4()),
                  "sequence": sequence, "run_id": None, "clock_domain": "test-clock"},
    }


def _producer(message):
    return [{**message, "event": event} for event in
            ("publish_attempt", "publish_accepted", "publish_complete")]


def _receipt(message, **overrides):
    return {**message, "event": "received",
            "received_at": (NOW + timedelta(seconds=1)).isoformat(), **overrides}


def _persist(message, sensor="temperature", **overrides):
    return {
        "trace_version": 1, "event": "persisted",
        "event_at": (NOW + timedelta(seconds=2)).isoformat(),
        "committed_at": (NOW + timedelta(seconds=2)).isoformat(),
        "source_message_id": message["trace"]["message_id"], "work_id": str(uuid4()),
        "generated_at": message["generated_at"], "sensor_name": sensor,
        "backend_clock_domain": "test-clock", "alerts": [{"alert_id": str(uuid4())}],
        **overrides,
    }


def _report(producer, backend, **overrides):
    return reconcile(
        producer, backend, **{
            "started_at": NOW, "emission_ended_at": NOW + timedelta(seconds=5),
            "observed_until": NOW + timedelta(seconds=10), "grace_seconds": 5,
            "run_id": None, "complete_capture": True, **overrides,
        },
    )


def test_controlled_loss_is_measured_instead_of_assuming_all_delivered():
    first, lost = _message(), _message()
    report = _report(_producer(first) + _producer(lost), [_receipt(first)])
    assert report["status"] == "final"
    assert report["counts"]["sent_unique"] == 2
    assert report["counts"]["not_received"] == 1
    assert report["pdr_percent"] == report["loss_percent"] == 50
    assert report["received_payload_bytes"] == 237
    assert report["payload_goodput_bytes_per_second"] == 23.7


def test_duplicate_receipts_and_three_sensors_do_not_multiply_bytes_or_pdr():
    message = _message()
    report = _report(_producer(message), [
        _receipt(message), _receipt(message),
        *[_persist(message, sensor) for sensor in ("temperature", "humidity", "energy")],
    ])
    assert report["counts"]["received_unique"] == 1
    assert report["counts"]["duplicate_receptions"] == 1
    assert report["counts"]["persisted_readings"] == 3
    assert report["pdr_percent"] == 100
    assert report["received_payload_bytes"] == 237
    assert report["device_to_persist_ms"]["mean"] == 3000
    assert report["device_to_alert_persist_ms"]["count"] == 3


@pytest.mark.parametrize("overrides", [
    {"complete_capture": False},
    {"observed_until": NOW + timedelta(seconds=6)},
])
def test_unclosed_or_unattested_capture_has_no_final_rates(overrides):
    message = _message()
    report = _report(_producer(message), [_receipt(message)], **overrides)
    assert report["status"] == "provisional"
    assert report["pdr_percent"] is None
    assert report["loss_percent"] is None
    assert report["payload_goodput_bytes_per_second"] is None


def test_accepted_publication_without_completion_is_not_a_measured_send():
    message = _message()
    report = _report(_producer(message)[:2], [])
    assert report["counts"]["publication_outcome_unknown"] == 1
    assert report["counts"]["sent_unique"] == 0
    assert report["pdr_percent"] is None


def test_publication_error_is_not_network_loss():
    message = _message()
    report = _report([
        {**message, "event": "publish_attempt"}, {**message, "event": "publish_error"},
    ], [])
    assert report["counts"]["publication_errors"] == 1
    assert report["counts"]["sent_unique"] == 0
    assert report["pdr_percent"] is None


def test_no_evidence_is_not_zero_latency_or_zero_measured_throughput():
    report = _report([], [])
    assert report["pdr_percent"] is None
    assert report["payload_goodput_bytes_per_second"] is None
    assert report["device_to_persist_ms"] == {"count": 0, "mean": None, "p95": None}
    assert report["message_delay_variation_ms"]["mean"] is None


def test_jitter_uses_consecutive_messages_of_same_stream():
    session = str(uuid4())
    first, second, gap = (_message(i, session) for i in (0, 1, 3))
    second["event_at"] = (NOW + timedelta(seconds=1)).isoformat()
    gap["event_at"] = (NOW + timedelta(seconds=3)).isoformat()
    report = _report(
        _producer(first) + _producer(second) + _producer(gap),
        [_receipt(first), _receipt(second, received_at=(NOW + timedelta(seconds=2, milliseconds=250)).isoformat()),
         _receipt(gap, received_at=(NOW + timedelta(seconds=4)).isoformat())],
    )
    assert report["message_delay_variation_ms"] == {"count": 1, "mean": 250, "p95": 250}


def test_restarted_producer_can_restart_sequence_in_another_session():
    before, after = _message(0), _message(0)
    report = _report(_producer(before) + _producer(after), [_receipt(before), _receipt(after)])
    assert report["counts"]["sent_unique"] == report["counts"]["received_unique"] == 2
    assert report["pdr_percent"] == 100


def test_sequence_reuse_within_one_session_is_corrupt_evidence():
    session = str(uuid4())
    with pytest.raises(ValueError, match="reused a sequence"):
        _report(_producer(_message(0, session)) + _producer(_message(0, session)), [])


def test_late_reception_does_not_rewrite_fixed_deadline_loss():
    message = _message()
    report = _report(
        _producer(message),
        [_receipt(message, received_at=(NOW + timedelta(seconds=11)).isoformat())],
        observed_until=NOW + timedelta(seconds=12),
    )
    assert report["counts"]["late_receptions"] == 1
    assert report["pdr_percent"] == 0
    assert report["loss_percent"] == 100


@pytest.mark.parametrize("overrides", [
    {"backend_clock_domain": None}, {"backend_clock_domain": "another-host"},
    {"generated_at": "2026-11-20T12:00:00"},
    {"generated_at": (NOW + timedelta(seconds=3)).isoformat()},
])
def test_uncomparable_or_invalid_clocks_do_not_fabricate_latency(overrides):
    message = _message()
    report = _report(_producer(message), [_receipt(message), _persist(message, **overrides)])
    assert report["device_to_persist_ms"]["count"] == 0
    assert report["device_to_persist_ms"]["mean"] is None


def test_conflicting_payload_sizes_are_rejected():
    message = _message()
    with pytest.raises(ValueError, match="sizes differ"):
        _report(_producer(message), [_receipt(message, size_bytes=128)])


def test_identity_conflicts_are_not_silently_deduplicated():
    message = _message()
    receipt = _receipt(message, device_code="OTHER")
    with pytest.raises(ValueError, match="Conflicting emission"):
        _report(_producer(message), [receipt])


def test_report_is_run_scoped():
    message = _message()
    message["trace"]["run_id"] = str(uuid4())
    report = _report(_producer(message), [_receipt(message)])
    assert report["counts"]["sent_unique"] == 0
    assert _report(_producer(message), [_receipt(message)],
                   run_id=message["trace"]["run_id"])["counts"]["sent_unique"] == 1


def test_other_known_emission_windows_do_not_invalidate_selected_cohort():
    selected, previous = _message(), _message()
    previous["event_at"] = (NOW - timedelta(seconds=20)).isoformat()
    report = _report(
        _producer(selected) + _producer(previous),
        [_receipt(selected),
         _receipt(previous, received_at=(NOW - timedelta(seconds=19)).isoformat())],
    )
    assert report["status"] == "final"
    assert report["pdr_percent"] == 100
    assert report["counts"]["sent_unique"] == 1


def test_unmatched_publication_completion_invalidates_final_rates():
    message = _message()
    report = _report(
        _producer(message) + [{
            "trace_version": 1, "event": "publication_unmatched",
            "event_at": NOW.isoformat(), "mqtt_mid": 42,
        }],
        [_receipt(message)],
    )
    assert report["status"] == "provisional"
    assert report["pdr_percent"] is None
