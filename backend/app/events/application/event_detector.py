from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.events.domain import DetectedEvent, RuleEvaluation


class EventDetector:
    """Detects critical events from rule evaluation breaches.

    Consumes ``RuleEvaluation`` objects produced by ``RuleEngine`` and
    generates a ``DetectedEvent`` for each evaluation where ``breached``
    is ``True``.  This class does **not** evaluate thresholds — it
    only filters and transforms existing breach results.
    """

    _VARIABLE_LABELS = {
        "temperature": "Temperatura",
        "humidity": "Humedad",
        "energy": "Energía",
    }

    _UNITS = {
        "temperature": "°C",
        "humidity": "%",
        "energy": "",
    }

    def detect(self, evaluations: list[RuleEvaluation]) -> list[DetectedEvent]:
        """Filter breached evaluations and produce a ``DetectedEvent`` for each."""
        if not isinstance(evaluations, list):
            raise TypeError("'evaluations' must be a list")
        for evaluation in evaluations:
            if not isinstance(evaluation, RuleEvaluation):
                raise TypeError(
                    "Every element in 'evaluations' must be a RuleEvaluation instance"
                )
        return [
            self._evaluation_to_event(evaluation)
            for evaluation in evaluations
            if evaluation.breached
        ]

    def _evaluation_to_event(self, evaluation: RuleEvaluation) -> DetectedEvent:
        event_type = self._event_type_for(evaluation)
        message = self._message_for(evaluation)
        return DetectedEvent(
            id=uuid4(),
            device_code=evaluation.device_code,
            variable=evaluation.variable,
            event_type=event_type,
            message=message,
            observed_value=evaluation.observed_value,
            threshold=evaluation.threshold,
            detected_at=datetime.now(timezone.utc),
        )

    def _event_type_for(self, evaluation: RuleEvaluation) -> str:
        variable = evaluation.variable
        if variable == "temperature":
            min_t, max_t = evaluation.threshold
            if evaluation.observed_value > max_t:
                return "TEMPERATURE_EXCEEDED"
            return "TEMPERATURE_BELOW_MIN"
        if variable == "humidity":
            min_h, max_h = evaluation.threshold
            if evaluation.observed_value > max_h:
                return "HUMIDITY_ABOVE_MAX"
            return "HUMIDITY_BELOW_MIN"
        return "ENERGY_STATE_ANOMALY"

    def _message_for(self, evaluation: RuleEvaluation) -> str:
        variable = evaluation.variable
        label = self._VARIABLE_LABELS[variable]
        unit = self._UNITS[variable]
        observed = evaluation.observed_value

        if variable == "energy":
            observed_str = f"'{observed}'"
            allowed = ", ".join(sorted(evaluation.threshold))
            return (
                f"{label} observada ({observed_str}) fuera de los "
                f"estados permitidos {{{allowed}}}"
            )

        observed_str = f"{observed}{unit}"
        min_val, max_val = evaluation.threshold
        return (
            f"{label} observada ({observed_str}) fuera del rango "
            f"configurado ({min_val}{unit}-{max_val}{unit})"
        )
