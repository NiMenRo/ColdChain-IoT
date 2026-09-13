from __future__ import annotations
from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import Session
from app.database.infrastructure.models import PredictionORM, SensorReadingORM, DeviceORM

class PredictionHistoryRepository:
    def list(self, db: Session, *, device_code: str | None = None, model_version: str | None = None, from_ts: datetime | None = None, to_ts: datetime | None = None, sort: str = "prediction_time.desc", page: int = 1, per_page: int = 20):
        q = db.query(PredictionORM).join(SensorReadingORM, PredictionORM.reading_id == SensorReadingORM.id).join(DeviceORM, SensorReadingORM.device_id == DeviceORM.id)
        if device_code:
            q = q.filter(DeviceORM.code == device_code)
        if model_version:
            q = q.filter(PredictionORM.model_version == model_version)
        if from_ts:
            q = q.filter(PredictionORM.prediction_time >= from_ts)
        if to_ts:
            q = q.filter(PredictionORM.prediction_time <= to_ts)
        total = q.count()
        desc = sort.endswith(".desc")
        field = sort.split(".")[0]
        col = getattr(PredictionORM, field, PredictionORM.prediction_time)
        q = q.order_by(col.desc() if desc else col.asc())
        items = q.offset((page - 1) * per_page).limit(per_page).all()
        return total, items
    def get_by_id(self, db: Session, id: UUID):
        return db.query(PredictionORM).filter_by(id=id).first()
