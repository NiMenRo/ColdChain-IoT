from __future__ import annotations

from enum import Enum


class CriticalityLevel(str, Enum):
    """Interpretation of the criticality score C."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CriticalityCalculator:
    """Computes the criticality of an IoT event using C = I + U + R.

    Each criterion (Impact, Urgency, Risk) must be an integer between 1 and 3.
    The resulting score C ranges from 3 to 9 and is classified as:

    * C >= 7  → HIGH   (Muy critico)
    * 4 <= C < 7 → MEDIUM (Medio)
    * C < 4  → LOW    (Bajo)
    """

    MIN_CRITERION = 1
    MAX_CRITERION = 3

    def calculate(self, impact: int, urgency: int, risk: int) -> float:
        """Return C = I + U + R after validating all criteria."""
        self._validate_criterion("impact", impact)
        self._validate_criterion("urgency", urgency)
        self._validate_criterion("risk", risk)
        return impact + urgency + risk

    def classify(self, criticality: float) -> CriticalityLevel:
        """Map a criticality score to its interpretation level."""
        if criticality >= 7:
            return CriticalityLevel.HIGH
        if criticality >= 4:
            return CriticalityLevel.MEDIUM
        return CriticalityLevel.LOW

    def _validate_criterion(self, name: str, value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"'{name}' must be an integer")
        if value < self.MIN_CRITERION or value > self.MAX_CRITERION:
            raise ValueError(
                f"'{name}' must be between {self.MIN_CRITERION} and {self.MAX_CRITERION}"
            )
