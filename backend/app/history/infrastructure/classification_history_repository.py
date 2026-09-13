from __future__ import annotations
from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import Session
from app.database.infrastructure.models import DeviceORM, SensorReadingORM, TrafficClassificationORM

class ClassificationHistoryRepository:
    def list(self, db: Session, *, device_code: str | None = None, priority: str | None = None, queue: str | None = None, from_ts: datetime | None = None, to_ts: datetime | None = None, sort: str = "timestamp.desc", page: int = 1, per_page: int = 20):
        q = db.query(TrafficClassificationORM).join(SensorReadingORM, TrafficClassificationORM.reading_id == SensorReadingORM.id).join(DeviceORM, SensorReadingORM.device_id == DeviceORM.id)
        if device_code:
            q = q.filter(DeviceORM.code == device_code)
        if priority:
            q = q.filter(TrafficClassificationORM.priority == priority)
        if queue:
            q = q.filter(TrafficClassificationORM.queue == queue)
        if from_ts:
            q = q.filter(TrafficClassificationORM.timestamp >= from_ts)
        if to_ts:
            q = q.filter(TrafficClassificationORM.timestamp <= to_ts)
        total = q.count()
        desc = sort.endswith(".desc")
        field = sort.split(".")[0]
        col = getattr(TrafficClassificationORM, field, TrafficClassificationORM.timestamp)
        q = q.order_by(col.desc() if desc else col.asc())
        items = q.offset((page - 1) * per_page).limit(per_page).all()
        return total, items
    def get_by_id(self, db: Session, id: UUID):
        return db.query(TrafficClassificationORM).filter_by(id=id).first()
