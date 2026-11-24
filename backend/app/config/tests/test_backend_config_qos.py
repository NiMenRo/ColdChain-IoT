import json

import pytest

from app.config import BackendConfig


QOS_ENVIRONMENT = (
    "MAX_QUEUE_SIZE",
    "QOS_HIGH_QUOTA",
    "QOS_MEDIUM_QUOTA",
    "QOS_LOW_QUOTA",
    "QOS_WFQ_FLOW_WEIGHTS",
    "QOS_WFQ_BAND_WEIGHTS",
    "QOS_PENDING_CAPACITY",
    "QOS_RECENT_TRACE_CAPACITY",
    "QOS_RECENT_FAILURE_CAPACITY",
    "QOS_DRAIN_TIMEOUT_S",
)


@pytest.fixture(autouse=True)
def unset_qos_environment(monkeypatch):
    for name in QOS_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


def test_qos_defaults_match_the_approved_policy_and_limits():
    config = BackendConfig()

    assert config.effective_qos_config() == {
        "class_quotas": {"high": 4, "medium": 2, "low": 1},
        "wfq_policy": "criticality_bands_v1",
        "wfq_band_weights": {"H8": 2, "H9": 3},
        "capacities": {
            "transport_messages": 1000,
            "pending_work_items": 3000,
            "recent_trace_entries": 1000,
            "recent_failure_entries": 100,
        },
        "timeouts": {"drain_s": 2.0},
    }
    assert config.qos_wfq_band_weights == {"H8": 2, "H9": 3}


def test_qos_environment_overrides_are_validated_and_serializable(monkeypatch):
    monkeypatch.setenv("MAX_QUEUE_SIZE", "11")
    monkeypatch.setenv("QOS_HIGH_QUOTA", "5")
    monkeypatch.setenv("QOS_MEDIUM_QUOTA", "3")
    monkeypatch.setenv("QOS_LOW_QUOTA", "2")
    monkeypatch.setenv("QOS_PENDING_CAPACITY", "33")
    monkeypatch.setenv("QOS_RECENT_TRACE_CAPACITY", "22")
    monkeypatch.setenv("QOS_RECENT_FAILURE_CAPACITY", "7")
    monkeypatch.setenv("QOS_DRAIN_TIMEOUT_S", "5.5")
    monkeypatch.setenv(
        "QOS_WFQ_BAND_WEIGHTS",
        '{"H8": 1.5, "H9": 2}',
    )

    effective = BackendConfig().effective_qos_config()

    assert effective["class_quotas"] == {"high": 5, "medium": 3, "low": 2}
    assert effective["wfq_band_weights"] == {"H8": 1.5, "H9": 2.0}
    assert effective["capacities"] == {
        "transport_messages": 11,
        "pending_work_items": 33,
        "recent_trace_entries": 22,
        "recent_failure_entries": 7,
    }
    assert effective["timeouts"] == {"drain_s": 5.5}
    assert json.loads(json.dumps(effective)) == effective


@pytest.mark.parametrize(
    "name,value",
    [
        ("MAX_QUEUE_SIZE", "0"),
        ("QOS_HIGH_QUOTA", "-1"),
        ("QOS_MEDIUM_QUOTA", "zero"),
        ("QOS_LOW_QUOTA", "1.5"),
        ("QOS_PENDING_CAPACITY", "0"),
        ("QOS_RECENT_TRACE_CAPACITY", "-2"),
        ("QOS_RECENT_FAILURE_CAPACITY", ""),
    ],
)
def test_rejects_non_positive_or_malformed_integer_limits(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        BackendConfig()


@pytest.mark.parametrize(
    "value",
    ["0", "-1", "zero", "", "nan", "inf"],
)
def test_rejects_non_positive_or_malformed_drain_timeout(monkeypatch, value):
    monkeypatch.setenv("QOS_DRAIN_TIMEOUT_S", value)
    with pytest.raises(ValueError, match="QOS_DRAIN_TIMEOUT_S"):
        BackendConfig()


@pytest.mark.parametrize(
    "weights",
    [
        "not-json",
        "[]",
        '{"H7": 1}',
        '{"H7": 1, "H8": 2, "H9": 3, "H10": 4}',
        '{"H7": 0, "H8": 2, "H9": 3}',
        '{"H7": -1, "H8": 2, "H9": 3}',
        '{"H7": true, "H8": 2, "H9": 3}',
        '{"H7": "2", "H8": 2, "H9": 3}',
        '{"H7": 1e999, "H8": 2, "H9": 3}',
    ],
)
def test_rejects_malformed_or_non_positive_wfq_weights(monkeypatch, weights):
    monkeypatch.setenv("QOS_WFQ_BAND_WEIGHTS", weights)
    with pytest.raises(ValueError, match="QOS_WFQ_BAND_WEIGHTS"):
        BackendConfig()


def test_old_flow_weights_require_explicit_migration(monkeypatch):
    monkeypatch.setenv("QOS_WFQ_FLOW_WEIGHTS", '{"CAVA-001:temperature": 2}')
    with pytest.raises(ValueError, match="obsolete"):
        BackendConfig()


def test_effective_qos_config_never_serializes_credentials(monkeypatch):
    monkeypatch.setenv("MQTT_USERNAME", "should-not-appear")
    monkeypatch.setenv("MQTT_PASSWORD", "must-not-appear")
    monkeypatch.setenv("MQTT_CA_CERT", "private-ca-path")

    rendered = json.dumps(BackendConfig().effective_qos_config())

    assert "should-not-appear" not in rendered
    assert "must-not-appear" not in rendered
    assert "private-ca-path" not in rendered
