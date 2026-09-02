from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.infrastructure.session import get_db
from app.history.application.history_service import HistoryService

router = APIRouter(prefix="/history", tags=["history"])
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
def reading_trends(device_code: Optional[str]=None, from_ts: Optional[str]=None, to_ts: Optional[str]=None, interval: str=Query("hour", pattern="^(minute|hour|day)$"), db: Session=Depends(get_db)):
    f = _parse_dt(from_ts); t = _parse_dt(to_ts)
    rows = service.readings.trends(db, device_code=device_code, from_ts=f, to_ts=t, interval=interval)
    return [{"bucket": r.bucket.isoformat() if hasattr(r.bucket, 'isoformat') else str(r.bucket), "avg_temp": float(r.avg_temp or 0), "min_temp": float(r.min_temp or 0), "max_temp": float(r.max_temp or 0), "avg_hum": float(r.avg_hum or 0), "min_hum": float(r.min_hum or 0), "max_hum": float(r.max_hum or 0)} for r in rows]

@router.get("/readings")
def list_readings(device_code: Optional[str]=None, from_ts: Optional[str]=None, to_ts: Optional[str]=None, sort: str="timestamp.desc", page: int=Query(1, ge=1), per_page: int=Query(20, ge=1, le=100), db: Session=Depends(get_db)):
    _validate_page(per_page, page)
    f = _parse_dt(from_ts); t = _parse_dt(to_ts)
    if f and t and f > t:
        raise HTTPException(400, "from must be <= to")
    total, items = service.readings.list(db, device_code=device_code, from_ts=f, to_ts=t, sort=sort, page=page, per_page=per_page)
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
        "predictions": [_serialize(x) for x in bundle["predictions"]],
    }

@router.get("/classifications")
def list_classifications(device_code: Optional[str]=None, priority: Optional[str]=None, queue: Optional[str]=None, from_ts: Optional[str]=None, to_ts: Optional[str]=None, sort: str="timestamp.desc", page: int=1, per_page: int=20, db: Session=Depends(get_db)):
    _validate_page(per_page, page)
    f = _parse_dt(from_ts); t = _parse_dt(to_ts)
    total, items = service.classifications.list(db, device_code=device_code, priority=priority, queue=queue, from_ts=f, to_ts=t, sort=sort, page=page, per_page=per_page)
    return {"total": total, "page": page, "per_page": per_page, "count": len(items), "results": [_serialize(i) for i in items]}

@router.get("/classifications/{id}")
def get_classification(id: UUID, db: Session=Depends(get_db)):
    obj = service.classifications.get_by_id(db, id)
    if not obj:
        raise HTTPException(404, "Classification not found")
    return _serialize(obj)

@router.get("/qos/trends")
def qos_trends(device_code: Optional[str]=None, from_ts: Optional[str]=None, to_ts: Optional[str]=None, interval: str=Query("hour", pattern="^(minute|hour|day)$"), db: Session=Depends(get_db)):
    f = _parse_dt(from_ts); t = _parse_dt(to_ts)
    rows = service.qos.trends(db, device_code=device_code, from_ts=f, to_ts=t, interval=interval)
    return [{"bucket": r.bucket.isoformat() if hasattr(r.bucket, 'isoformat') else str(r.bucket), "avg_latency": float(r.avg_latency or 0), "min_latency": float(r.min_latency or 0), "max_latency": float(r.max_latency or 0), "avg_packet_loss": float(r.avg_packet_loss or 0), "avg_throughput": float(r.avg_throughput or 0), "avg_pdr": float(r.avg_pdr or 0), "avg_jitter": float(r.avg_jitter or 0)} for r in rows]

@router.get("/qos")
def list_qos(device_code: Optional[str]=None, from_ts: Optional[str]=None, to_ts: Optional[str]=None, sort: str="timestamp.desc", page: int=1, per_page: int=20, db: Session=Depends(get_db)):
    _validate_page(per_page, page)
    f = _parse_dt(from_ts); t = _parse_dt(to_ts)
    total, items = service.qos.list(db, device_code=device_code, from_ts=f, to_ts=t, sort=sort, page=page, per_page=per_page)
    return {"total": total, "page": page, "per_page": per_page, "count": len(items), "results": [_serialize(i) for i in items]}

@router.get("/qos/{id}")
def get_qos(id: UUID, db: Session=Depends(get_db)):
    obj = service.qos.get_by_id(db, id)
    if not obj:
        raise HTTPException(404, "QoSMetric not found")
    return _serialize(obj)

@router.get("/alerts")
def list_alerts(device_code: Optional[str]=None, type: Optional[str]=None, acknowledged: Optional[bool]=None, from_ts: Optional[str]=None, to_ts: Optional[str]=None, sort: str="created_at.desc", page: int=1, per_page: int=20, db: Session=Depends(get_db)):
    _validate_page(per_page, page)
    f = _parse_dt(from_ts); t = _parse_dt(to_ts)
    total, items = service.alerts.list(db, device_code=device_code, type=type, acknowledged=acknowledged, from_ts=f, to_ts=t, sort=sort, page=page, per_page=per_page)
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
def summary(db: Session=Depends(get_db)):
    return service.summary(db)
