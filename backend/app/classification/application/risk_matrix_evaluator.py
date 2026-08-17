from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.acquisition.normalizer import NormalizedReading


@dataclass(frozen=True)
class RiskCriteria:
    """Impact, Urgency and Risk values derived from a sensor reading."""

    impact: int
    urgency: int
    risk: int


class RiskMatrixEvaluator:
    """Derives I/U/R criteria from raw sensor readings using the product risk matrix.

    The matrix (see ``context/matriz_riesgo_productos_carnicos.md``) assigns
    (impact, urgency, risk) tuples based on temperature, humidity and energy
    conditions.  Range boundaries use a half-open convention:

    * Temperature: 0<=T<=4 -> (1,1,1); 4<T<=8 -> (2,2,2); T>8 -> (3,3,3);
      -5<=T<0 -> (2,2,2); T<-5 -> (3,3,2)
    * Humidity: 85<=H<=90 -> (1,1,1); 80<=H<85 or 90<H<=95 -> (2,2,2);
      H<80 or H>95 -> (3,3,2)
    * Energy: on -> (1,1,1); intermittent/inestable -> (2,3,2); off -> (3,3,3)

    Values that do not map to any condition raise a ``ValueError`` instead of
    silently falling back, because the matrix covers the whole domain.
    """

    ENERGY_RULES: dict[str, tuple[int, int, int]] = {
        "on": (1, 1, 1),
        "intermittent": (2, 3, 2),
        "off": (3, 3, 3),
    }

    UNKNOWN_ENERGY_MESSAGE = "Unknown energy state: {value!r}"

    def evaluate(self, reading: NormalizedReading) -> RiskCriteria:
        """Return the RiskCriteria for a single normalized sensor reading."""
        if not isinstance(reading, NormalizedReading):
            raise TypeError("'reading' must be a NormalizedReading instance")

        sensor_name = reading.sensor_name
        if sensor_name == "temperature":
            return self.evaluate_temperature(reading.value)
        if sensor_name == "humidity":
            return self.evaluate_humidity(reading.value)
        if sensor_name == "energy":
            return self.evaluate_energy(reading.raw_value)

        raise ValueError(f"Unsupported sensor type: {sensor_name!r}")

    def evaluate_temperature(self, temperature: float) -> RiskCriteria:
        """Map a temperature reading (celsius) to I/U/R criteria."""
        if temperature > 8:
            return RiskCriteria(impact=3, urgency=3, risk=3)
        if temperature > 4:
            return RiskCriteria(impact=2, urgency=2, risk=2)
        if temperature >= 0:
            return RiskCriteria(impact=1, urgency=1, risk=1)
        if temperature >= -5:
            return RiskCriteria(impact=2, urgency=2, risk=2)
        return RiskCriteria(impact=3, urgency=3, risk=2)

    def evaluate_humidity(self, humidity: float) -> RiskCriteria:
        """Map a humidity reading (percent) to I/U/R criteria."""
        if humidity >= 85 and humidity <= 90:
            return RiskCriteria(impact=1, urgency=1, risk=1)
        if (humidity >= 80 and humidity < 85) or (humidity > 90 and humidity <= 95):
            return RiskCriteria(impact=2, urgency=2, risk=2)
        if humidity < 80 or humidity > 95:
            return RiskCriteria(impact=3, urgency=3, risk=2)
        raise ValueError(f"Humidity value out of range: {humidity!r}")

    def evaluate_energy(self, value: Any) -> RiskCriteria:
        """Map an energy state to I/U/R criteria.

        The original (raw) value is used instead of the normalized float so that
        the energy state string (``on``/``off``/``intermittent``) is preserved.
        """
        state = str(value).strip().lower()
        if state not in self.ENERGY_RULES:
            raise ValueError(self.UNKNOWN_ENERGY_MESSAGE.format(value=value))
        impact, urgency, risk = self.ENERGY_RULES[state]
        return RiskCriteria(impact=impact, urgency=urgency, risk=risk)