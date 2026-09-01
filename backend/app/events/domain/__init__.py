from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID


@dataclass
class Alert:
    """A domain event raised when a monitored device requires operator attention.

    An alert is always associated with exactly one device and one user, and
    records the event ``type``, a human-readable ``message`` and a numeric
    ``criticality`` score (the same C = I + U + R value used by the
    classification subsystem) so that downstream priority logic can reuse it.
    """

    id: UUID
    device_id: UUID
    user_id: UUID
    type: str
    message: str
    criticality: float
    acknowledged: bool
    created_at: datetime

    def __post_init__(self) -> None:
        self._validate_id()
        self._validate_device_id()
        self._validate_user_id()
        self._validate_type()
        self._validate_message()
        self._validate_criticality()
        self._validate_acknowledged()
        self._validate_created_at()

    def _validate_id(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("'id' must be a UUID instance")

    def _validate_device_id(self) -> None:
        if not isinstance(self.device_id, UUID):
            raise TypeError("'device_id' must be a UUID instance")

    def _validate_user_id(self) -> None:
        if not isinstance(self.user_id, UUID):
            raise TypeError("'user_id' must be a UUID instance")

    def _validate_type(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("'type' must be a str instance")
        if not self.type.strip():
            raise ValueError("'type' must be a non-empty string")

    def _validate_message(self) -> None:
        if not isinstance(self.message, str):
            raise TypeError("'message' must be a str instance")
        if not self.message.strip():
            raise ValueError("'message' must be a non-empty string")

    def _validate_criticality(self) -> None:
        if isinstance(self.criticality, bool) or not isinstance(self.criticality, (int, float)):
            raise TypeError("'criticality' must be a numeric value")

    def _validate_acknowledged(self) -> None:
        if not isinstance(self.acknowledged, bool):
            raise TypeError("'acknowledged' must be a bool instance")

    def _validate_created_at(self) -> None:
        if not isinstance(self.created_at, datetime):
            raise TypeError("'created_at' must be a datetime instance")


_SUPPORTED_VARIABLES = ("temperature", "humidity", "energy")


@dataclass
class ThresholdConfig:
    """In-memory threshold configuration injected into the rule engine.

    All fields are required and provided by the caller; the engine never
    invents threshold values. ``allowed_energy_states`` lists the energy
    states considered normal (any other state is treated as a breach).
    """

    min_temperature: float
    max_temperature: float
    min_humidity: float
    max_humidity: float
    allowed_energy_states: frozenset[str]

    def __post_init__(self) -> None:
        self._validate_temperature()
        self._validate_humidity()
        self._validate_energy_states()

    def _validate_temperature(self) -> None:
        self._validate_bound("min_temperature", self.min_temperature)
        self._validate_bound("max_temperature", self.max_temperature)
        if self.min_temperature > self.max_temperature:
            raise ValueError("'min_temperature' must be <= 'max_temperature'")

    def _validate_humidity(self) -> None:
        self._validate_bound("min_humidity", self.min_humidity)
        self._validate_bound("max_humidity", self.max_humidity)
        if self.min_humidity > self.max_humidity:
            raise ValueError("'min_humidity' must be <= 'max_humidity'")

    def _validate_bound(self, name: str, value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"'{name}' must be a numeric value")

    def _validate_energy_states(self) -> None:
        if isinstance(self.allowed_energy_states, set):
            self.allowed_energy_states = frozenset(self.allowed_energy_states)
        if not isinstance(self.allowed_energy_states, frozenset):
            raise TypeError("'allowed_energy_states' must be a frozenset")
        if not self.allowed_energy_states:
            raise ValueError("'allowed_energy_states' must not be empty")
        for state in self.allowed_energy_states:
            if not isinstance(state, str):
                raise TypeError("'allowed_energy_states' must contain only strings")


@dataclass
class RuleEvaluation:
    """Result of evaluating a single normalized reading against the thresholds.

    One instance is produced per reading evaluated by ``RuleEngine``. It records
    whether the configured condition was breached and the timestamp of the
    evaluation, so downstream components can later measure detection-to-alert
    latency. It deliberately carries no ``severity`` (that belongs to alerting,
    not to raw condition detection).
    """

    rule_id: str
    device_code: str
    variable: str
    observed_value: float | str
    threshold: tuple[float, float] | frozenset[str]
    breached: bool
    evaluated_at: datetime

    def __post_init__(self) -> None:
        self._validate_rule_id()
        self._validate_device_code()
        self._validate_variable()
        self._validate_observed_value()
        self._validate_threshold()
        self._validate_breached()
        self._validate_evaluated_at()

    def _validate_rule_id(self) -> None:
        if not isinstance(self.rule_id, str):
            raise TypeError("'rule_id' must be a str instance")
        if not self.rule_id.strip():
            raise ValueError("'rule_id' must be a non-empty string")

    def _validate_device_code(self) -> None:
        if not isinstance(self.device_code, str):
            raise TypeError("'device_code' must be a str instance")
        if not self.device_code.strip():
            raise ValueError("'device_code' must be a non-empty string")

    def _validate_variable(self) -> None:
        if self.variable not in _SUPPORTED_VARIABLES:
            raise ValueError(
                f"'variable' must be one of {_SUPPORTED_VARIABLES}"
            )

    def _validate_observed_value(self) -> None:
        if self.variable in ("temperature", "humidity"):
            if isinstance(self.observed_value, bool) or not isinstance(
                self.observed_value, (int, float)
            ):
                raise TypeError(
                    "'observed_value' must be numeric for temperature/humidity"
                )
        else:
            if not isinstance(self.observed_value, str):
                raise TypeError("'observed_value' must be a str for energy")
            if not self.observed_value.strip():
                raise ValueError(
                    "'observed_value' must be a non-empty string for energy"
                )

    def _validate_threshold(self) -> None:
        if self.variable in ("temperature", "humidity"):
            if (
                not isinstance(self.threshold, tuple)
                or len(self.threshold) != 2
                or any(
                    isinstance(t, bool) or not isinstance(t, (int, float))
                    for t in self.threshold
                )
            ):
                raise TypeError(
                    "'threshold' must be a (min, max) numeric tuple for "
                    "temperature/humidity"
                )
        else:
            if not isinstance(self.threshold, frozenset):
                raise TypeError(
                    "'threshold' must be a frozenset for energy"
                )

    def _validate_breached(self) -> None:
        if not isinstance(self.breached, bool):
            raise TypeError("'breached' must be a bool instance")

    def _validate_evaluated_at(self) -> None:
        if not isinstance(self.evaluated_at, datetime):
            raise TypeError("'evaluated_at' must be a datetime instance")
        if self.evaluated_at.tzinfo is None:
            raise TypeError("'evaluated_at' must be timezone-aware")


_SUPPORTED_EVENT_TYPES = (
    "TEMPERATURE_EXCEEDED",
    "TEMPERATURE_BELOW_MIN",
    "HUMIDITY_ABOVE_MAX",
    "HUMIDITY_BELOW_MIN",
    "ENERGY_STATE_ANOMALY",
)


@dataclass
class DetectedEvent:
    """Critical condition detected from a rule evaluation breach.

    Represents the fact that a monitored variable exceeded its configured
    threshold.  It carries no severity or criticality — those concepts
    belong to ``TrafficClassification`` and will be used downstream when
    building ``Alert`` objects.
    """

    id: UUID
    device_code: str
    variable: str
    event_type: str
    message: str
    observed_value: float | str
    threshold: tuple[float, float] | frozenset[str]
    detected_at: datetime

    def __post_init__(self) -> None:
        self._validate_id()
        self._validate_device_code()
        self._validate_variable()
        self._validate_event_type()
        self._validate_message()
        self._validate_observed_value()
        self._validate_threshold()
        self._validate_detected_at()

    def _validate_id(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("'id' must be a UUID instance")

    def _validate_device_code(self) -> None:
        if not isinstance(self.device_code, str):
            raise TypeError("'device_code' must be a str instance")
        if not self.device_code.strip():
            raise ValueError("'device_code' must be a non-empty string")

    def _validate_variable(self) -> None:
        if self.variable not in _SUPPORTED_VARIABLES:
            raise ValueError(
                f"'variable' must be one of {_SUPPORTED_VARIABLES}"
            )

    def _validate_event_type(self) -> None:
        if not isinstance(self.event_type, str):
            raise TypeError("'event_type' must be a str instance")
        if not self.event_type.strip():
            raise ValueError("'event_type' must be a non-empty string")

    def _validate_message(self) -> None:
        if not isinstance(self.message, str):
            raise TypeError("'message' must be a str instance")
        if not self.message.strip():
            raise ValueError("'message' must be a non-empty string")

    def _validate_observed_value(self) -> None:
        if self.variable in ("temperature", "humidity"):
            if isinstance(self.observed_value, bool) or not isinstance(
                self.observed_value, (int, float)
            ):
                raise TypeError(
                    "'observed_value' must be numeric for temperature/humidity"
                )
        else:
            if not isinstance(self.observed_value, str):
                raise TypeError("'observed_value' must be a str for energy")
            if not self.observed_value.strip():
                raise ValueError(
                    "'observed_value' must be a non-empty string for energy"
                )

    def _validate_threshold(self) -> None:
        if self.variable in ("temperature", "humidity"):
            if (
                not isinstance(self.threshold, tuple)
                or len(self.threshold) != 2
                or any(
                    isinstance(t, bool) or not isinstance(t, (int, float))
                    for t in self.threshold
                )
            ):
                raise TypeError(
                    "'threshold' must be a (min, max) numeric tuple for "
                    "temperature/humidity"
                )
        else:
            if not isinstance(self.threshold, frozenset):
                raise TypeError(
                    "'threshold' must be a frozenset for energy"
                )

    def _validate_detected_at(self) -> None:
        if not isinstance(self.detected_at, datetime):
            raise TypeError("'detected_at' must be a datetime instance")
        if self.detected_at.tzinfo is None:
            raise TypeError("'detected_at' must be timezone-aware")
