from __future__ import annotations
from datetime import datetime
from uuid import UUID
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database.infrastructure.models import QoSMetricORM, TrafficClassificationORM, SensorReadingORM, DeviceORM

class QoSHistoryRepository:
    def list(self, db: Session, *, device_code: str | None = None, from_ts: datetime | None = None, to_ts: datetime | None = None, sort: str = "timestamp.desc", page: int = 1, per_page: int = 20):
        q = db.query(QoSMetricORM).join(TrafficClassificationORM, QoSMetricORM.classification_id == TrafficClassificationORM.id).join(SensorReadingORM, TrafficClassificationORM.reading_id == SensorReadingORM.id).join(DeviceORM, SensorReadingORM.device_id == DeviceORM.id)
        if device_code:
            q = q.filter(DeviceORM.code == device_code)
        if from_ts:
            q = q.filter(QoSMetricORM.timestamp >= from_ts)
        if to_ts:
            q = q.filter(QoSMetricORM.timestamp <= to_ts)
        total = q.count()
        desc = sort.endswith(".desc")
        field = sort.split(".")[0]
        col = getattr(QoSMetricORM, field, QoSMetricORM.timestamp)
        q = q.order_by(col.desc() if desc else col.asc())
        items = q.offset((page - 1) * per_page).limit(per_page).all()
        return total, items
    def get_by_id(self, db: Session, id: UUID):
        return db.query(QoSMetricORM).filter_by(id=id).first()
    def trends(self, db: Session, *, device_code: str | None = None, from_ts: datetime | None = None, to_ts: datetime | None = None, interval: str = "hour"):
        trunc = func.date_trunc(interval, QoSMetricORM.timestamp)
        q = db.query(
            trunc.label("bucket"),
            func.avg(QoSMetricORM.latency).label("avg_latency"),
            func.min(QoSMetricORM.latency).label("min_latency"),
            func.max(QoSMetricORM.latency).label("max_latency"),
            func.avg(QoSMetricORM.packet_loss).label("avg_packet_loss"),
            func.avg(QoSMetricORM.throughput).label("avg_throughput"),
            func.avg(QoSMetricORM.pdr).label("avg_pdr"),
            func.avg(QoSMetricORM.jitter).label("avg_jitter"),
        ).join(TrafficClassificationORM, QoSMetricORM.classification_id == TrafficClassificationORM.id).join(SensorReadingORM, TrafficClassificationORM.reading_id == SensorReadingORM.id).join(DeviceORM, SensorReadingORM.device_id == DeviceORM.id)
        if device_code:
            q = q.filter(DeviceORM.code == device_code)
        if from_ts:
            q = q.filter(QoSMetricORM.timestamp >= from_ts)
        if to_ts:
            q = q.filter(QoSMetricORM.timestamp <= to_ts)
        q = q.group_by(trunc).order_by(trunc)
        return q.all()
