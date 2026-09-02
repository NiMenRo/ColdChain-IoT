from __future__ import annotations
from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import Session
from app.database.infrastructure.models import AlertORM, DeviceORM

class AlertHistoryRepository:
    def list(self, db: Session, *, device_code: str | None = None, type: str | None = None, acknowledged: bool | None = None, from_ts: datetime | None = None, to_ts: datetime | None = None, sort: str = "created_at.desc", page: int = 1, per_page: int = 20):
        q = db.query(AlertORM)
        if device_code:
            q = q.join(DeviceORM, AlertORM.device_id == DeviceORM.id).filter(DeviceORM.code == device_code)
        if type:
            q = q.filter(AlertORM.type == type)
        if acknowledged is not None:
            q = q.filter(AlertORM.acknowledged == acknowledged)
        if from_ts:
            q = q.filter(AlertORM.created_at >= from_ts)
        if to_ts:
            q = q.filter(AlertORM.created_at <= to_ts)
        total = q.count()
        desc = sort.endswith(".desc")
        field = sort.split(".")[0]
        col = getattr(AlertORM, field, AlertORM.created_at)
        q = q.order_by(col.desc() if desc else col.asc())
        items = q.offset((page - 1) * per_page).limit(per_page).all()
        return total, items
    def get_by_id(self, db: Session, id: UUID):
        return db.query(AlertORM).filter_by(id=id).first()
