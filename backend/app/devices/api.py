"""Device management API (TSK-059.8).

Thin router over DeviceRepository/DeviceSensorRepository/AuditService.
Repositories flush; the router owns commit/rollback (single transaction).
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.auth.authorization import authenticated
from app.database.infrastructure.repositories import (
    DeviceRepository,
    DeviceSensorRepository,
)
from app.database.infrastructure.session import get_db
from app.devices.schemas import (
    CreateDeviceRequest,
    DeviceDetailResponse,
    DeviceListResponse,
    DeviceResponse,
    UpdateDeviceSensorsRequest,
)
from app.security.dependencies import require_admin

router = APIRouter(prefix="/devices", tags=["devices"])
_devices = DeviceRepository()
_sensors = DeviceSensorRepository()
_audit = AuditService()


def _to_response(device) -> DeviceResponse:
    return DeviceResponse(
        id=str(device.id),
        code=device.code,
        name=device.name,
        location=device.location,
        device_type=device.device_type,
        status=device.status,
        registration_date=device.registration_date,
    )


def _to_detail(device, sensors: list[str]) -> DeviceDetailResponse:
    return DeviceDetailResponse(
        device=_to_response(device),
        sensors=sorted(sensors),
    )


def _sensor_set(sensors: list[str]) -> list[str]:
    """Deduplicated sensor set; raises 400 on duplicates after normalization."""
    normalized = [s for s in sensors]
    unique = sorted(set(normalized))
    if len(unique) != len(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate sensors are not allowed.",
        )
    return unique


@router.post(
    "",
    response_model=DeviceDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a device with its sensors",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Admin role required"},
        409: {"description": "Device code already exists"},
    },
)
def create_device(
    body: CreateDeviceRequest,
    db: Session = Depends(get_db),
    _current=Depends(require_admin),
):
    sensors = _sensor_set(body.sensors)
    if not sensors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one sensor is required.",
        )
    if _devices.exists(db, body.code):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A device with this code already exists.",
        )
    try:
        device = _devices.create(
            db,
            code=body.code,
            name=body.name,
            location=body.location,
            device_type=body.device_type,
            status=body.status,
        )
        for sensor_type in sensors:
            _sensors.create(db, device_id=device.id, sensor_type=sensor_type)
        _audit.record(
            db,
            actor_user_id=_current.id,
            action="device.create",
            resource=f"devices/{device.id}",
        )
        db.commit()
        db.refresh(device)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A device with this code already exists.",
        )
    return _to_detail(device, sensors)


@router.get(
    "",
    response_model=DeviceListResponse,
    summary="List devices",
    responses={401: {"description": "Not authenticated"}},
)
def list_devices(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    device_type: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    _current=Depends(authenticated),
):
    total, items = _devices.list(
        db, page=page, per_page=per_page, status=status,
        device_type=device_type, search=search,
    )
    return DeviceListResponse(
        total=total,
        page=page,
        per_page=per_page,
        count=len(items),
        results=[_to_response(d) for d in items],
    )


@router.get(
    "/{device_id}",
    response_model=DeviceDetailResponse,
    summary="Get device detail with sensors",
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Device not found"},
    },
)
def get_device(
    device_id: UUID,
    db: Session = Depends(get_db),
    _current=Depends(authenticated),
):
    device = _devices.get_by_id(db, device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found."
        )
    sensors = [s.sensor_type for s in _sensors.list_by_device(db, device.id)]
    return _to_detail(device, sensors)


@router.put(
    "/{device_id}/sensors",
    response_model=DeviceDetailResponse,
    summary="Replace device sensor configuration",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Admin role required"},
        404: {"description": "Device not found"},
    },
)
def replace_device_sensors(
    device_id: UUID,
    body: UpdateDeviceSensorsRequest,
    db: Session = Depends(get_db),
    _current=Depends(require_admin),
):
    device = _devices.get_by_id(db, device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found."
        )
    desired = _sensor_set(body.sensors)
    if not desired:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one sensor is required.",
        )
    current = sorted(s.sensor_type for s in _sensors.list_by_device(db, device.id))
    to_add = [s for s in desired if s not in current]
    to_remove = [s for s in current if s not in desired]
    try:
        for sensor_type in to_add:
            _sensors.create(db, device_id=device.id, sensor_type=sensor_type)
        for sensor_type in to_remove:
            row = _sensors.get(db, device.id, sensor_type)
            if row is not None:
                _sensors.delete(db, row)
        _audit.record(
            db,
            actor_user_id=_current.id,
            action="device.sensors_update",
            resource=f"devices/{device.id}",
            old_value={"sensors": current},
            new_value={"sensors": desired},
        )
        db.commit()
        db.refresh(device)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sensor configuration conflict.",
        )
    return _to_detail(device, desired)
