from __future__ import annotations

from datetime import datetime, timezone

from app.acquisition.normalizer import NormalizedReading
from app.events.domain import RuleEvaluation, ThresholdConfig


class RuleEngine:
    """Detects threshold breaches in normalized IoT readings.

    The engine is intentionally decoupled from the classification subsystem
    (``RiskMatrixEvaluator``, ``TrafficClassification``) and from the alerting
    domain (``Alert``): it only consumes ``NormalizedReading`` objects plus an
    injected ``ThresholdConfig`` and reports, per reading, whether a configured
    condition was breached. Threshold values are never hard-coded here.
    """

    def __init__(self, config: ThresholdConfig) -> None:
        if not isinstance(config, ThresholdConfig):
            raise TypeError("'config' must be a ThresholdConfig instance")
        self._config = config

    def evaluate(self, readings: list[NormalizedReading]) -> list[RuleEvaluation]:
        """Evaluate every reading and return one ``RuleEvaluation`` per reading."""
        if not isinstance(readings, list):
            raise TypeError("'readings' must be a list")
        return [self._evaluate_one(reading) for reading in readings]

    def _evaluate_one(self, reading: NormalizedReading) -> RuleEvaluation:
        if not isinstance(reading, NormalizedReading):
            raise TypeError("'reading' must be a NormalizedReading instance")

        sensor = reading.sensor_name
        if sensor == "temperature":
            breached = (
                reading.value < self._config.min_temperature
                or reading.value > self._config.max_temperature
            )
            threshold: tuple[float, float] | frozenset[str] = (
                self._config.min_temperature,
                self._config.max_temperature,
            )
            observed: float | str = reading.value
        elif sensor == "humidity":
            breached = (
                reading.value < self._config.min_humidity
                or reading.value > self._config.max_humidity
            )
            threshold = (
                self._config.min_humidity,
                self._config.max_humidity,
            )
            observed = reading.value
        elif sensor == "energy":
            state = str(reading.raw_value).strip().lower()
            breached = state not in self._config.allowed_energy_states
            threshold = self._config.allowed_energy_states
            observed = state
        else:
            raise ValueError(f"Unsupported sensor type: {sensor!r}")

        return RuleEvaluation(
            rule_id=f"{sensor}_threshold",
            device_code=reading.device_code,
            variable=sensor,
            observed_value=observed,
            threshold=threshold,
            breached=breached,
            evaluated_at=datetime.now(timezone.utc),
        )
