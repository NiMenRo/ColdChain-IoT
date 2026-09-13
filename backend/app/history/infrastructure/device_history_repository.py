from __future__ import annotations
from uuid import UUID
from sqlalchemy.orm import Session
from app.database.infrastructure.models import DeviceORM, SensorReadingORM

class DeviceHistoryRepository:
    def list(self, db: Session, *, page: int = 1, per_page: int = 20):
        q = db.query(DeviceORM)
        total = q.count()
        items = q.order_by(DeviceORM.code.asc()).offset((page - 1) * per_page).limit(per_page).all()
        return total, items
    def get_by_code(self, db: Session, code: str):
        return db.query(DeviceORM).filter_by(code=code).first()
    def get_by_id(self, db: Session, id: UUID):
        return db.query(DeviceORM).filter_by(id=id).first()
    def history(self, db: Session, code: str, from_ts=None, to_ts=None, page=1, per_page=20):
        device = self.get_by_code(db, code)
        if not device:
            return None
        q = db.query(SensorReadingORM).filter_by(device_id=device.id)
        if from_ts:
            q = q.filter(SensorReadingORM.timestamp >= from_ts)
        if to_ts:
            q = q.filter(SensorReadingORM.timestamp <= to_ts)
        total = q.count()
        items = q.order_by(SensorReadingORM.timestamp.desc()).offset((page - 1) * per_page).limit(per_page).all()
        return device, total, items
