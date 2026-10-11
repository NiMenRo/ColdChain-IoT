"""Schemas for system threshold configuration (TSK-059.4).

Only threshold fields are administrable. qos_algorithm/qos_enabled are
read-only reserved configuration and are never accepted in the request.
"""

from __future__ import annotations

from pydantic import BaseModel, model_validator


class SystemConfigUpdate(BaseModel):
    min_temperature: float | None = None
    max_temperature: float | None = None
    min_humidity: float | None = None
    max_humidity: float | None = None

    @model_validator(mode="after")
    def _check_ranges(self) -> SystemConfigUpdate:
        if (
            self.min_temperature is not None
            and self.max_temperature is not None
            and self.min_temperature > self.max_temperature
        ):
            raise ValueError("min_temperature must be <= max_temperature")
        if (
            self.min_humidity is not None
            and self.max_humidity is not None
            and self.min_humidity > self.max_humidity
        ):
            raise ValueError("min_humidity must be <= max_humidity")
        for field in (
            "min_temperature",
            "max_temperature",
            "min_humidity",
            "max_humidity",
        ):
            value = getattr(self, field)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise ValueError(f"{field} must be numeric")
        return self


class SystemConfigResponse(BaseModel):
    id: str
    min_temperature: float
    max_temperature: float
    min_humidity: float
    max_humidity: float
