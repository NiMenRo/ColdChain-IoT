from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.auth.authorization import authenticated
from app.database.infrastructure.session import get_db
from app.history.application.history_service import HistoryService

router = APIRouter(
    prefix="/history", tags=["history"], dependencies=[Depends(authenticated)]
)
service = HistoryService()

def _parse_dt(v: str | None):
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        raise HTTPException(400, "Invalid datetime, use ISO-8601")
def _validate_page(per_page: int, page: int):
    if page < 1:
        raise HTTPException(400, "page must be >=1")
    if not 1 <= per_page <= 100:
        raise HTTPException(400, "per_page must be 1..100")
def _parse_run_id(v: str | None):
    """Optional run scope. Malformed UUID -> 400; unknown-but-valid UUID
    simply matches zero rows (never simulated, never 404)."""
    if not v:
        return None
    try:
        return UUID(str(v).strip())
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, "Invalid run_id, must be a UUID")
def _parse_processing_version(v: int | None):
    if v is None:
        return None
    if v not in (1, 2):
        raise HTTPException(400, "processing_version must be 1 or 2")
    return v
def _serialize(obj):
    if obj is None:
        return None
    d = {}
    for k, v in obj.__dict__.items():
        if k.startswith("_"):
            continue
        if isinstance(v, UUID):
            d[k] = str(v)
        elif isinstance(v, datetime):
            d[k] = v.isoformat()
        else:
            d[k] = v
    return d

@router.get("/readings/trends")
def reading_trends(device_code: Optional[str]=None, from_ts: Optional[str]=None, to_ts: Optional[str]=None, run_id: Optional[str]=None, interval: str=Query("hour", pattern="^(minute|hour|day)$"), db: Session=Depends(get_db)):
    f = _parse_dt(from_ts); t = _parse_dt(to_ts)
    rows = service.readings.trends(db, device_code=device_code, from_ts=f, to_ts=t, run_id=_parse_run_id(run_id), interval=interval)
    def _num(v):
        # TSK-059.3 — NULL means sensor not enabled; never coerce to 0.
        return float(v) if v is not None else None
    return [{"bucket": r.bucket.isoformat() if hasattr(r.bucket, 'isoformat') else str(r.bucket), "avg_temp": _num(r.avg_temp), "min_temp": _num(r.min_temp), "max_temp": _num(r.max_temp), "avg_hum": _num(r.avg_hum), "min_hum": _num(r.min_hum), "max_hum": _num(r.max_hum)} for r in rows]

@router.get("/readings")
def list_readings(device_code: Optional[str]=None, from_ts: Optional[str]=None, to_ts: Optional[str]=None, run_id: Optional[str]=None, processing_version: Optional[int]=None, sort: str="timestamp.desc", page: int=Query(1, ge=1), per_page: int=Query(20, ge=1, le=100), db: Session=Depends(get_db)):
    _validate_page(per_page, page)
    f = _parse_dt(from_ts); t = _parse_dt(to_ts)
    if f and t and f > t:
        raise HTTPException(400, "from must be <= to")
    total, items = service.readings.list(db, device_code=device_code, from_ts=f, to_ts=t, run_id=_parse_run_id(run_id), processing_version=_parse_processing_version(processing_version), sort=sort, page=page, per_page=per_page)
    return {"total": total, "page": page, "per_page": per_page, "count": len(items), "results": [_serialize(i) for i in items]}

@router.get("/readings/{id}")
def get_reading(id: UUID, db: Session=Depends(get_db)):
    obj = service.readings.get_by_id(db, id)
    if not obj:
        raise HTTPException(404, "Reading not found")
    return _serialize(obj)

@router.get("/readings/{id}/bundle")
def get_bundle(id: UUID, db: Session=Depends(get_db)):
    bundle = service.readings.get_bundle(db, id)
    if not bundle or not bundle["sensor_reading"]:
        raise HTTPException(404, "Reading not found")
    return {
        "device": _serialize(bundle["device"]),
        "sensor_reading": _serialize(bundle["sensor_reading"]),
        "traffic_classification": _serialize(bundle["traffic_classification"]),
        "qos_metrics": [_serialize(x) for x in bundle["qos_metrics"]],
        "alerts": [_serialize(x) for x in bundle["alerts"]],
        "alerts_legacy": bundle["alerts_legacy"],
        "predictions": [_serialize(x) for x in bundle["predictions"]],
    }

@router.get("/devices/{code}/latest-values")
def latest_values(code: str, db: Session=Depends(get_db)):
    values = service.readings.latest_values(db, code)
    if all(row is None for row in values.values()):
        # Preserve the existing device-history distinction: unknown devices are
        # 404, while a known device with no readings returns no values.
        if service.devices.get_by_code(db, code) is None:
            raise HTTPException(404, "Device not found")
    return {sensor: _serialize(row) for sensor, row in values.items()}

@router.get("/classifications")
def list_classifications(device_code: Optional[str]=None, priority: Optional[str]=None, queue: Optional[str]=None, from_ts: Optional[str]=None, to_ts: Optional[str]=None, run_id: Optional[str]=None, sort: str="timestamp.desc", page: int=1, per_page: int=20, db: Session=Depends(get_db)):
    _validate_page(per_page, page)
    f = _parse_dt(from_ts); t = _parse_dt(to_ts)
    total, items = service.classifications.list(db, device_code=device_code, priority=priority, queue=queue, from_ts=f, to_ts=t, run_id=_parse_run_id(run_id), sort=sort, page=page, per_page=per_page)
    return {"total": total, "page": page, "per_page": per_page, "count": len(items), "results": [_serialize(i) for i in items]}

@router.get("/classifications/{id}")
def get_classification(id: UUID, db: Session=Depends(get_db)):
    obj = service.classifications.get_by_id(db, id)
    if not obj:
        raise HTTPException(404, "Classification not found")
    return _serialize(obj)

@router.get("/qos/trends")
def qos_trends(device_code: Optional[str]=None, from_ts: Optional[str]=None, to_ts: Optional[str]=None, run_id: Optional[str]=None, interval: str=Query("hour", pattern="^(minute|hour|day)$"), processing_version: int=Query(2, ge=1, le=2), db: Session=Depends(get_db)):
    f = _parse_dt(from_ts); t = _parse_dt(to_ts)
    rows = service.qos.trends(db, device_code=device_code, from_ts=f, to_ts=t, run_id=_parse_run_id(run_id), interval=interval, processing_version=processing_version)
    def nullable(value):
        return None if value is None else float(value)
    return [{"bucket": r.bucket.isoformat() if hasattr(r.bucket, 'isoformat') else str(r.bucket), "avg_latency": nullable(r.avg_latency), "min_latency": nullable(r.min_latency), "max_latency": nullable(r.max_latency), "avg_packet_loss": nullable(r.avg_packet_loss), "avg_throughput": nullable(r.avg_throughput), "avg_pdr": nullable(r.avg_pdr), "avg_jitter": nullable(r.avg_jitter)} for r in rows]

@router.get("/qos")
def list_qos(device_code: Optional[str]=None, from_ts: Optional[str]=None, to_ts: Optional[str]=None, run_id: Optional[str]=None, sort: str="timestamp.desc", page: int=1, per_page: int=20, db: Session=Depends(get_db)):
    _validate_page(per_page, page)
    f = _parse_dt(from_ts); t = _parse_dt(to_ts)
    total, items = service.qos.list(db, device_code=device_code, from_ts=f, to_ts=t, run_id=_parse_run_id(run_id), sort=sort, page=page, per_page=per_page)
    return {"total": total, "page": page, "per_page": per_page, "count": len(items), "results": [_serialize(i) for i in items]}

@router.get("/qos/{id}")
def get_qos(id: UUID, db: Session=Depends(get_db)):
    obj = service.qos.get_by_id(db, id)
    if not obj:
        raise HTTPException(404, "QoSMetric not found")
    return _serialize(obj)

@router.get("/alerts")
def list_alerts(device_code: Optional[str]=None, type: Optional[str]=None, acknowledged: Optional[bool]=None, from_ts: Optional[str]=None, to_ts: Optional[str]=None, run_id: Optional[str]=None, sort: str="created_at.desc", page: int=1, per_page: int=20, db: Session=Depends(get_db)):
    _validate_page(per_page, page)
    f = _parse_dt(from_ts); t = _parse_dt(to_ts)
    total, items = service.alerts.list(db, device_code=device_code, type=type, acknowledged=acknowledged, from_ts=f, to_ts=t, run_id=_parse_run_id(run_id), sort=sort, page=page, per_page=per_page)
    return {"total": total, "page": page, "per_page": per_page, "count": len(items), "results": [_serialize(i) for i in items]}

@router.get("/alerts/{id}")
def get_alert(id: UUID, db: Session=Depends(get_db)):
    obj = service.alerts.get_by_id(db, id)
    if not obj:
        raise HTTPException(404, "Alert not found")
    return _serialize(obj)

@router.get("/predictions")
def list_predictions(device_code: Optional[str]=None, model_version: Optional[str]=None, from_ts: Optional[str]=None, to_ts: Optional[str]=None, sort: str="prediction_time.desc", page: int=1, per_page: int=20, db: Session=Depends(get_db)):
    _validate_page(per_page, page)
    f = _parse_dt(from_ts); t = _parse_dt(to_ts)
    total, items = service.predictions.list(db, device_code=device_code, model_version=model_version, from_ts=f, to_ts=t, sort=sort, page=page, per_page=per_page)
    return {"total": total, "page": page, "per_page": per_page, "count": len(items), "results": [_serialize(i) for i in items]}

@router.get("/predictions/{id}")
def get_prediction(id: UUID, db: Session=Depends(get_db)):
    obj = service.predictions.get_by_id(db, id)
    if not obj:
        raise HTTPException(404, "Prediction not found")
    return _serialize(obj)

@router.get("/devices")
def list_devices(page: int=1, per_page: int=20, db: Session=Depends(get_db)):
    _validate_page(per_page, page)
    total, items = service.devices.list(db, page=page, per_page=per_page)
    return {"total": total, "page": page, "per_page": per_page, "count": len(items), "results": [_serialize(i) for i in items]}

@router.get("/devices/{code}/history")
def device_history(code: str, from_ts: Optional[str]=None, to_ts: Optional[str]=None, page: int=1, per_page: int=20, db: Session=Depends(get_db)):
    _validate_page(per_page, page)
    f = _parse_dt(from_ts); t = _parse_dt(to_ts)
    res = service.devices.history(db, code, from_ts=f, to_ts=t, page=page, per_page=per_page)
    if res is None:
        raise HTTPException(404, "Device not found")
    device, total, items = res
    return {"device": _serialize(device), "total": total, "page": page, "per_page": per_page, "count": len(items), "results": [_serialize(i) for i in items]}

@router.get("/summary")
def summary(run_id: Optional[str]=None, db: Session=Depends(get_db)):
    return service.summary(db, run_id=_parse_run_id(run_id))
