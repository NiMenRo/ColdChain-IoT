"""Schemas for device management (TSK-059.8).

Sensor types mirror the DeviceSensor CHECK; extra fields are forbidden.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

SensorType = Literal["temperature", "humidity", "energy"]


def _normalize_sensor(value):
    if isinstance(value, str):
        return value.strip().lower()
    return value


NormalizedSensor = Annotated[SensorType, BeforeValidator(_normalize_sensor)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateDeviceRequest(_StrictModel):
    code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1)
    device_type: str = Field(..., min_length=1)
    status: str = "active"
    # No min_length here: an empty list must answer 400 (router), not 422.
    sensors: list[NormalizedSensor] = Field(...)


class UpdateDeviceSensorsRequest(_StrictModel):
    # Empty list answered with 400 by the router, not 422.
    sensors: list[NormalizedSensor] = Field(...)


class DeviceResponse(BaseModel):
    id: str
    code: str
    name: str
    location: str
    device_type: str
    status: str
    registration_date: datetime


class DeviceDetailResponse(BaseModel):
    device: DeviceResponse
    sensors: list[SensorType]


class DeviceListResponse(BaseModel):
    total: int
    page: int
    per_page: int
    count: int
    results: list[DeviceResponse]
