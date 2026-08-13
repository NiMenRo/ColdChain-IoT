from __future__ import annotations

from enum import Enum


class PriorityLevel(str, Enum):
    """Priority level assigned to an IoT message based on its criticality score."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PriorityAssigner:
    """Maps a criticality score to a priority level.

    Thresholds (derived from the project's criticality classification):

    * C >= 7  → HIGH   (Alta)
    * 4 <= C < 7 → MEDIUM (Media)
    * C < 4  → LOW    (Baja)

    Valid criticality range: 3 to 9 (result of C = I + U + R with I, U, R in [1, 3]).
    """

    MIN_CRITICALITY = 3
    MAX_CRITICALITY = 9

    def assign(self, criticality: float) -> PriorityLevel:
        """Return the priority level for the given criticality score."""
        self._validate(criticality)
        if criticality >= 7:
            return PriorityLevel.HIGH
        if criticality >= 4:
            return PriorityLevel.MEDIUM
        return PriorityLevel.LOW

    def _validate(self, criticality: object) -> None:
        if isinstance(criticality, bool) or not isinstance(criticality, (int, float)):
            raise TypeError("'criticality' must be numeric")
        if criticality < self.MIN_CRITICALITY or criticality > self.MAX_CRITICALITY:
            raise ValueError(
                f"'criticality' must be between {self.MIN_CRITICALITY} "
                f"and {self.MAX_CRITICALITY}"
            )
