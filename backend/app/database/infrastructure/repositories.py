from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.database.infrastructure.models import (
    AlertORM,
    DeviceORM,
    PredictionORM,
    QoSMetricORM,
    SensorReadingORM,
    SystemConfigORM,
    TrafficClassificationORM,
    UserORM,
)
from app.database.infrastructure.models import HUMAN_USER_ROLES
from app.database.seed import SYSTEM_USER_ID
from app.events.domain import Alert
from app.qos.domain import QoSMetric


def _parse_timestamp(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class SensorReadingRepository:
    def save(self, db: Session, readings: list[NormalizedReading], device_id: uuid.UUID) -> SensorReadingORM:
        if not readings:
            raise ValueError("readings must not be empty")
        device = db.query(DeviceORM).filter_by(id=device_id).first()
        if device is None:
            raise ValueError(f"device_id {device_id} is not registered")
        device_codes = {reading.device_code for reading in readings}
        if device_codes != {device.code}:
            raise ValueError(
                "reading device_code does not match the registered device_id"
            )
        # Group by same device_code + timestamp (documented grouping, no generic mapper)
        # Assume readings belong to the same bundle (same MQTT message)
        by_key: dict[tuple[str, str], list[NormalizedReading]] = {}
        for r in readings:
            by_key.setdefault((r.device_code, r.timestamp), []).append(r)
        # For TSK-042, persist 1 SensorReading per bundle; if multiple keys, use the first
        first_key = next(iter(by_key))
        group = by_key[first_key]
        values: dict[str, object] = {}
        for r in group:
            if r.sensor_name == "temperature":
                values["temperature"] = float(r.value)
            elif r.sensor_name == "humidity":
                values["humidity"] = float(r.value)
            elif r.sensor_name == "energy":
                values["energy"] = str(r.raw_value).strip().lower()
        if "temperature" not in values or "humidity" not in values or "energy" not in values:
            raise ValueError("Missing temperature/humidity/energy in readings group")
        ts = _parse_timestamp(group[0].timestamp)
        obj = SensorReadingORM(
            device_id=device_id,
            temperature=values["temperature"],
            humidity=values["humidity"],
            energy=values["energy"],
            timestamp=ts,
        )
        db.add(obj)
        db.flush()
        return obj


class TrafficClassificationRepository:
    def save(self, db: Session, tc: TrafficClassification, reading_id: uuid.UUID) -> TrafficClassificationORM:
        obj = TrafficClassificationORM(
            id=tc.id,
            reading_id=reading_id,
            criticality=tc.criticality,
            priority=tc.priority,
            queue=tc.queue,
            classification_time=tc.classification_time,
            timestamp=tc.timestamp,
        )
        db.add(obj)
        db.flush()
        return obj

    def get_by_reading_id(self, db: Session, reading_id: uuid.UUID) -> TrafficClassificationORM | None:
        return db.query(TrafficClassificationORM).filter_by(reading_id=reading_id).first()


class QoSMetricRepository:
    def save(self, db: Session, metric: QoSMetric) -> QoSMetricORM:
        obj = QoSMetricORM(
            id=metric.id,
            classification_id=metric.classification_id,
            latency=metric.latency,
            packet_loss=metric.packet_loss,
            throughput=metric.throughput,
            pdr=metric.pdr,
            jitter=metric.jitter,
            timestamp=metric.timestamp,
        )
        db.add(obj)
        db.flush()
        return obj


class AlertRepository:
    def save(self, db: Session, alert: Alert) -> AlertORM:
        obj = AlertORM(
            id=alert.id,
            device_id=alert.device_id,
            user_id=alert.user_id,
            type=alert.type,
            message=alert.message,
            criticality=alert.criticality,
            acknowledged=alert.acknowledged,
            created_at=alert.created_at,
        )
        db.add(obj)
        db.flush()
        return obj

    def save_many(self, db: Session, alerts: list[Alert]) -> list[AlertORM]:
        result = []
        for a in alerts:
            result.append(self.save(db, a))
        return result


class PredictionRepository:
    def save(self, db: Session, reading_id: uuid.UUID, predicted_alert: str, probability: float, model_version: str, prediction_time: datetime | None = None) -> PredictionORM:
        obj = PredictionORM(
            reading_id=reading_id,
            predicted_alert=predicted_alert,
            probability=probability,
            model_version=model_version,
            prediction_time=prediction_time or datetime.now(timezone.utc),
        )
        db.add(obj)
        db.flush()
        return obj


class SystemConfigRepository:
    """Reads the persisted system configuration used by application services."""

    def get_current(self, db: Session) -> SystemConfigORM | None:
        return (
            db.query(SystemConfigORM)
            .order_by(SystemConfigORM.id.asc())
            .first()
        )


# ---------------------------------------------------------------------------
# TSK-047.2 — Device / User repositories (no commit, UNIQUE as source of truth)
# ---------------------------------------------------------------------------

_ALLOWED_STATUSES = frozenset({"active", "inactive", "maintenance", "error"})
_ALLOWED_DEVICE_TYPES = frozenset({"cold_room", "refrigerated_showcase"})


class DeviceRepository:
    def get_by_id(self, db: Session, id: uuid.UUID) -> DeviceORM | None:
        return db.query(DeviceORM).filter_by(id=id).first()

    def get_by_code(self, db: Session, code: str) -> DeviceORM | None:
        if not isinstance(code, str):
            return None
        code = code.strip()
        if not code:
            return None
        return db.query(DeviceORM).filter_by(code=code).first()

    def exists(self, db: Session, code: str) -> bool:
        return self.get_by_code(db, code) is not None

    def list(
        self,
        db: Session,
        *,
        page: int = 1,
        per_page: int = 20,
        status: str | None = None,
        device_type: str | None = None,
        search: str | None = None,
    ) -> tuple[int, list[DeviceORM]]:
        q = db.query(DeviceORM)
        if status is not None:
            q = q.filter(DeviceORM.status == status)
        if device_type is not None:
            q = q.filter(DeviceORM.device_type == device_type)
        if search is not None:
            s = search.strip()
            if s:
                pattern = f"%{s}%"
                q = q.filter(
                    (DeviceORM.code.ilike(pattern))
                    | (DeviceORM.name.ilike(pattern))
                    | (DeviceORM.location.ilike(pattern))
                )
        q = q.order_by(DeviceORM.code.asc())
        total = q.count()
        items = q.offset((page - 1) * per_page).limit(per_page).all()
        return total, items

    def create(
        self,
        db: Session,
        *,
        code: str,
        name: str,
        location: str,
        device_type: str,
        status: str,
        registration_date: datetime | None = None,
    ) -> DeviceORM:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("code must be a non-empty string")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(location, str) or not location.strip():
            raise ValueError("location must be a non-empty string")
        if device_type not in _ALLOWED_DEVICE_TYPES:
            raise ValueError(f"device_type must be one of {sorted(_ALLOWED_DEVICE_TYPES)}")
        if status not in _ALLOWED_STATUSES:
            raise ValueError(f"status must be one of {sorted(_ALLOWED_STATUSES)}")
        obj = DeviceORM(
            code=code.strip(),
            name=name.strip(),
            location=location.strip(),
            device_type=device_type,
            status=status,
            registration_date=registration_date or datetime.now(timezone.utc),
        )
        db.add(obj)
        db.flush()
        return obj

    def update(self, db: Session, device: DeviceORM, **fields) -> DeviceORM:
        allowed = {"name", "location", "device_type", "status"}
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"field '{key}' is not updatable")
            if key in ("name", "location"):
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{key} must be a non-empty string")
                setattr(device, key, value.strip())
            elif key == "device_type":
                if value not in _ALLOWED_DEVICE_TYPES:
                    raise ValueError(f"device_type must be one of {sorted(_ALLOWED_DEVICE_TYPES)}")
                setattr(device, key, value)
            elif key == "status":
                if value not in _ALLOWED_STATUSES:
                    raise ValueError(f"status must be one of {sorted(_ALLOWED_STATUSES)}")
                setattr(device, key, value)
        db.flush()
        return device

    def update_status(self, db: Session, id: uuid.UUID, status: str) -> DeviceORM | None:
        if status not in _ALLOWED_STATUSES:
            raise ValueError(f"status must be one of {sorted(_ALLOWED_STATUSES)}")
        device = self.get_by_id(db, id)
        if device is None:
            return None
        device.status = status
        db.flush()
        return device


class UserRepository:
    def get_by_id(self, db: Session, id: uuid.UUID) -> UserORM | None:
        return db.query(UserORM).filter_by(id=id).first()

    def get_by_email(self, db: Session, email: str) -> UserORM | None:
        if not isinstance(email, str):
            return None
        email = email.strip().lower()
        if not email:
            return None
        return db.query(UserORM).filter_by(email=email).first()

    def get_system_user(self, db: Session) -> UserORM | None:
        return self.get_by_id(db, uuid.UUID(SYSTEM_USER_ID))

    def exists_email(self, db: Session, email: str) -> bool:
        return self.get_by_email(db, email) is not None

    def list(
        self,
        db: Session,
        *,
        page: int = 1,
        per_page: int = 20,
        role: str | None = None,
        search: str | None = None,
    ) -> tuple[int, list[UserORM]]:
        q = db.query(UserORM)
        if role is not None:
            q = q.filter(UserORM.role == role)
        if search is not None:
            s = search.strip()
            if s:
                pattern = f"%{s}%"
                q = q.filter(
                    (UserORM.name.ilike(pattern)) | (UserORM.email.ilike(pattern))
                )
        q = q.order_by(UserORM.email.asc())
        total = q.count()
        items = q.offset((page - 1) * per_page).limit(per_page).all()
        return total, items

    def create(
        self,
        db: Session,
        *,
        name: str,
        email: str,
        password_hash: str,
        role: str,
        is_active: bool = True,
        created_at: datetime | None = None,
    ) -> UserORM:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(email, str) or not email.strip():
            raise ValueError("email must be a non-empty string")
        if not isinstance(password_hash, str) or not password_hash:
            raise ValueError("password_hash must be a non-empty string")
        if not isinstance(role, str) or role.strip().lower() not in HUMAN_USER_ROLES:
            raise ValueError(
                f"role must be one of {sorted(HUMAN_USER_ROLES)} for human users"
            )
        if not isinstance(is_active, bool):
            raise ValueError("is_active must be a boolean")
        # Lower/strip normalization also delegated to @validates in UserORM, but done here
        # so exists_email / UNIQUE are consistent before flush.
        email = email.strip().lower()
        obj = UserORM(
            name=name.strip(),
            email=email,
            password_hash=password_hash,
            role=role.strip().lower(),
            is_active=is_active,
            created_at=created_at or datetime.now(timezone.utc),
        )
        db.add(obj)
        db.flush()
        return obj

    def update(self, db: Session, user: UserORM, **fields) -> UserORM:
        allowed = {"name", "email", "password_hash", "role", "is_active"}
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"field '{key}' is not updatable")
            if key == "email":
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("email must be a non-empty string")
                user.email = value.strip().lower()
            elif key in ("name", "role"):
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{key} must be a non-empty string")
                if key == "role":
                    normalized_role = value.strip().lower()
                    if normalized_role not in HUMAN_USER_ROLES:
                        raise ValueError(
                            f"role must be one of {sorted(HUMAN_USER_ROLES)} for human users"
                        )
                    if user.id == uuid.UUID(SYSTEM_USER_ID):
                        raise ValueError("the technical system user must keep role 'system'")
                    setattr(user, key, normalized_role)
                else:
                    setattr(user, key, value.strip())
            elif key == "password_hash":
                if not isinstance(value, str) or not value:
                    raise ValueError("password_hash must be a non-empty string")
                user.password_hash = value
            elif key == "is_active":
                if not isinstance(value, bool):
                    raise ValueError("is_active must be a boolean")
                user.is_active = value
        db.flush()
        return user
