from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.infrastructure.models import DeviceORM, SensorReadingORM, TrafficClassificationORM


class ReadingHistoryRepository:
    def list(self, db: Session, *, device_code: str | None = None, from_ts: datetime | None = None, to_ts: datetime | None = None, sort: str = "timestamp.desc", page: int = 1, per_page: int = 20):
        q = db.query(SensorReadingORM).join(DeviceORM, SensorReadingORM.device_id == DeviceORM.id)
        if device_code:
            q = q.filter(DeviceORM.code == device_code)
        if from_ts:
            q = q.filter(SensorReadingORM.timestamp >= from_ts)
        if to_ts:
            q = q.filter(SensorReadingORM.timestamp <= to_ts)
        total = q.count()
        # sort
        desc = sort.endswith(".desc")
        field = sort.split(".")[0]
        col = getattr(SensorReadingORM, field, SensorReadingORM.timestamp)
        q = q.order_by(col.desc() if desc else col.asc())
        items = q.offset((page - 1) * per_page).limit(per_page).all()
        return total, items

    def get_by_id(self, db: Session, id: UUID):
        return db.query(SensorReadingORM).filter_by(id=id).first()

    def get_bundle(self, db: Session, id: UUID):
        sr = self.get_by_id(db, id)
        if not sr:
            return None
        tc = db.query(TrafficClassificationORM).filter_by(reading_id=sr.id).first()
        from app.database.infrastructure.models import QoSMetricORM, AlertORM, PredictionORM
        qos = db.query(QoSMetricORM).filter_by(classification_id=tc.id).all() if tc else []
        alerts = db.query(AlertORM).filter_by(device_id=sr.device_id).all()
        preds = db.query(PredictionORM).filter_by(reading_id=sr.id).all()
        device = db.query(DeviceORM).filter_by(id=sr.device_id).first()
        return {"device": device, "sensor_reading": sr, "traffic_classification": tc, "qos_metrics": qos, "alerts": alerts, "predictions": preds}

    def trends(self, db: Session, *, device_code: str | None = None, from_ts: datetime | None = None, to_ts: datetime | None = None, interval: str = "hour"):
        # interval: minute, hour, day
        trunc = func.date_trunc(interval, SensorReadingORM.timestamp)
        q = db.query(
            trunc.label("bucket"),
            func.avg(SensorReadingORM.temperature).label("avg_temp"),
            func.min(SensorReadingORM.temperature).label("min_temp"),
            func.max(SensorReadingORM.temperature).label("max_temp"),
            func.avg(SensorReadingORM.humidity).label("avg_hum"),
            func.min(SensorReadingORM.humidity).label("min_hum"),
            func.max(SensorReadingORM.humidity).label("max_hum"),
        ).join(DeviceORM, SensorReadingORM.device_id == DeviceORM.id)
        if device_code:
            q = q.filter(DeviceORM.code == device_code)
        if from_ts:
            q = q.filter(SensorReadingORM.timestamp >= from_ts)
        if to_ts:
            q = q.filter(SensorReadingORM.timestamp <= to_ts)
        q = q.group_by(trunc).order_by(trunc)
        return q.all()
