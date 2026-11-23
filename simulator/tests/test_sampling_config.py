import pytest

from simulator.config import SimulatorConfig


def test_sampling_interval_can_be_configured(monkeypatch):
    monkeypatch.setenv("SIMULATOR_SAMPLING_INTERVAL", "10")
    assert SimulatorConfig().sampling_interval == 10


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_sampling_interval_must_be_positive_and_finite(monkeypatch, value):
    monkeypatch.setenv("SIMULATOR_SAMPLING_INTERVAL", value)
    with pytest.raises(ValueError):
        SimulatorConfig()
