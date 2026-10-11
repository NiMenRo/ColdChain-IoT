from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.database.infrastructure.models import (
    NOTIFICATION_CHANNELS,
    NOTIFICATION_STATUSES,
    AlertORM,
    AuditLogORM,
    DeviceORM,
    DeviceSensorORM,
    ExperimentMetricORM,
    ExperimentRunORM,
    NotificationORM,
    PredictionORM,
    QoSMetricORM,
    SensorReadingORM,
    SystemConfigORM,
    TrafficClassificationORM,
    UserORM,
)
from app.database.infrastructure.models import (
    EXPERIMENT_METRIC_TYPES,
    EXPERIMENT_SCENARIOS,
    HUMAN_USER_ROLES,
)
from app.database.seed import SYSTEM_USER_ID
from app.events.domain import Alert
from app.qos.domain import QoSMetric


def _parse_timestamp(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class SensorReadingRepository:
    def save(
        self,
        db: Session,
        readings: list[NormalizedReading],
        device_id: uuid.UUID,
        run_id: uuid.UUID | None = None,
    ) -> SensorReadingORM:
        """TSK-059.3 — persist 1 SensorReading per bundle honoring DeviceSensor.

        Absent sensors persist as NULL (not enabled, not a failure). Any
        received sensor that is not configured rejects the whole bundle.
        """
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
        enabled = {
            row.sensor_type
            for row in db.query(DeviceSensorORM).filter_by(device_id=device_id).all()
        }
        for r in readings:
            if r.sensor_name not in enabled:
                raise ValueError(
                    f"sensor '{r.sensor_name}' is not configured for device '{device.code}'"
                )
        # Group by same device_code + timestamp (documented grouping, no generic mapper)
        # Assume readings belong to the same bundle (same MQTT message)
        by_key: dict[tuple[str, str], list[NormalizedReading]] = {}
        for r in readings:
            by_key.setdefault((r.device_code, r.timestamp), []).append(r)
        # For TSK-042, persist 1 SensorReading per bundle; if multiple keys, use the first
        # (normalizer guarantees a single timestamp per MQTT message)
        first_key = next(iter(by_key))
        group = by_key[first_key]
        values: dict[str, object] = {}
        for r in group:
            if r.sensor_name == "temperature":
                values["temperature"] = float(r.value)
            elif r.sensor_name == "humidity":
                values["humidity"] = float(r.value)
            elif r.sensor_name == "energy":
                # TSK-059.4 — canonical energy is on/off; numeric raw values
                # are rejected (no producer sends them).
                normalized_energy = str(r.raw_value).strip().lower()
                if normalized_energy not in ("on", "off"):
                    raise ValueError(
                        f"energy must be 'on' or 'off', got {r.raw_value!r}"
                    )
                values["energy"] = normalized_energy
        if not values:
            raise ValueError("readings group has no valid sensor measurements")
        ts = _parse_timestamp(group[0].timestamp)
        obj = SensorReadingORM(
            device_id=device_id,
            temperature=values.get("temperature"),
            humidity=values.get("humidity"),
            energy=values.get("energy"),
            timestamp=ts,
            run_id=run_id,
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
    def save(
        self, db: Session, alert: Alert, run_id: uuid.UUID | None = None
    ) -> AlertORM:
        obj = AlertORM(
            id=alert.id,
            device_id=alert.device_id,
            user_id=alert.user_id,
            type=alert.type,
            message=alert.message,
            criticality=alert.criticality,
            acknowledged=alert.acknowledged,
            created_at=alert.created_at,
            run_id=run_id,
        )
        db.add(obj)
        db.flush()
        return obj

    def save_many(self, db: Session, alerts: list[Alert]) -> list[AlertORM]:
        result = []
        for a in alerts:
            result.append(self.save(db, a))
        return result

    def get_by_id(self, db: Session, id: uuid.UUID) -> AlertORM | None:
        return db.query(AlertORM).filter_by(id=id).first()

    def acknowledge(self, db: Session, id: uuid.UUID) -> AlertORM | None:
        """TSK-059.5 — persist acknowledged=True. Idempotent; flush, no commit."""
        row = self.get_by_id(db, id)
        if row is None:
            return None
        row.acknowledged = True
        db.flush()
        return row


class NotificationRepository:
    """Persistence for notification delivery records.

    Flush only; commit is the caller's responsibility. Read state
    (``is_read``/``read_at``) is independent from ``AlertORM.acknowledged``.
    ``UNIQUE(alert_id, channel, recipient)`` is the source of truth for
    idempotency: callers must check ``find_duplicate`` before ``create``
    when reprocessing the same alert.
    """

    def create(
        self,
        db: Session,
        *,
        alert_id: uuid.UUID,
        user_id: uuid.UUID,
        channel: str,
        status: str,
        recipient: str,
        message: str,
        detail: str | None = None,
        notification_date: datetime | None = None,
        notification_id: uuid.UUID | None = None,
    ) -> NotificationORM:
        if not isinstance(alert_id, uuid.UUID):
            raise ValueError("alert_id must be a UUID")
        if not isinstance(user_id, uuid.UUID):
            raise ValueError("user_id must be a UUID")
        if not isinstance(channel, str) or not channel.strip():
            raise ValueError("channel must be a non-empty string")
        normalized_channel = channel.strip().lower()
        if normalized_channel not in NOTIFICATION_CHANNELS:
            raise ValueError(
                "channel must be one of email, sms, push, dashboard"
            )
        if not isinstance(status, str) or not status.strip():
            raise ValueError("status must be a non-empty string")
        normalized_status = status.strip().lower()
        if normalized_status not in NOTIFICATION_STATUSES:
            raise ValueError(
                "status must be one of pending, sent, failed, simulated, disabled"
            )
        if not isinstance(recipient, str) or not recipient.strip():
            raise ValueError("recipient must be a non-empty string")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string")
        obj = NotificationORM(
            id=notification_id or uuid.uuid4(),
            alert_id=alert_id,
            user_id=user_id,
            channel=normalized_channel,
            status=normalized_status,
            is_read=False,
            read_at=None,
            recipient=recipient.strip(),
            message=message,
            detail=detail,
            notification_date=notification_date or datetime.now(timezone.utc),
        )
        db.add(obj)
        db.flush()
        return obj

    def find_duplicate(
        self,
        db: Session,
        alert_id: uuid.UUID,
        channel: str,
        recipient: str,
    ) -> NotificationORM | None:
        return (
            db.query(NotificationORM)
            .filter_by(
                alert_id=alert_id,
                channel=channel.strip().lower(),
                recipient=recipient.strip(),
            )
            .first()
        )

    def get_by_id(self, db: Session, id: uuid.UUID) -> NotificationORM | None:
        return db.query(NotificationORM).filter_by(id=id).first()

    def count_unread(self, db: Session, user_id: uuid.UUID) -> int:
        return (
            db.query(NotificationORM)
            .filter_by(user_id=user_id, is_read=False)
            .count()
        )

    def mark_read(
        self, db: Session, id: uuid.UUID, user_id: uuid.UUID
    ) -> NotificationORM | None:
        """Mark one owned notification as read. Idempotent; flush, no commit."""
        row = (
            db.query(NotificationORM)
            .filter_by(id=id, user_id=user_id)
            .first()
        )
        if row is None:
            return None
        if not row.is_read:
            row.is_read = True
            row.read_at = datetime.now(timezone.utc)
            db.flush()
        return row

    def mark_all_read(self, db: Session, user_id: uuid.UUID) -> int:
        """Mark all owned unread notifications as read. Returns rows updated."""
        rows = (
            db.query(NotificationORM)
            .filter_by(user_id=user_id, is_read=False)
            .all()
        )
        now = datetime.now(timezone.utc)
        for row in rows:
            row.is_read = True
            row.read_at = now
        if rows:
            db.flush()
        return len(rows)

    def list_by_owner(
        self,
        db: Session,
        user_id: uuid.UUID,
        *,
        status: str | None = None,
        channel: str | None = None,
        alert_id: uuid.UUID | None = None,
        is_read: bool | None = None,
        limit: int | None = None,
    ) -> list[NotificationORM]:
        """Owner-scoped history, newest first. Flush-free read."""
        query = db.query(NotificationORM).filter_by(user_id=user_id)
        if status is not None:
            query = query.filter_by(status=status.strip().lower())
        if channel is not None:
            query = query.filter_by(channel=channel.strip().lower())
        if alert_id is not None:
            query = query.filter_by(alert_id=alert_id)
        if is_read is not None:
            query = query.filter_by(is_read=is_read)
        query = query.order_by(NotificationORM.notification_date.desc())
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def update_status(
        self,
        db: Session,
        row: NotificationORM,
        status: str,
        detail: str | None = None,
    ) -> NotificationORM:
        """Record a new delivery outcome on an existing row (manual
        redispatch). Flush only; the caller commits. Callers must only
        transition failed/disabled/pending rows — sent/simulated rows are
        never rewritten."""
        if not isinstance(status, str) or not status.strip():
            raise ValueError("status must be a non-empty string")
        normalized = status.strip().lower()
        if normalized not in NOTIFICATION_STATUSES:
            raise ValueError(
                "status must be one of pending, sent, failed, simulated, disabled"
            )
        row.status = normalized
        row.detail = detail
        db.flush()
        return row


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

    _UPDATABLE_FIELDS = frozenset(
        {"min_temperature", "max_temperature", "min_humidity", "max_humidity"}
    )

    def get_current(self, db: Session) -> SystemConfigORM | None:
        return (
            db.query(SystemConfigORM)
            .order_by(SystemConfigORM.id.asc())
            .first()
        )

    def update(self, db: Session, config: SystemConfigORM, **fields) -> SystemConfigORM:
        """TSK-059.4 — admin-only threshold update (qos_* are read-only)."""
        for key, value in fields.items():
            if key not in self._UPDATABLE_FIELDS:
                raise ValueError(f"field '{key}' is not updatable")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be numeric")
        # Validate prospective values before setattr: reading expired
        # attributes would trigger autoflush and surface IntegrityError first.
        with db.no_autoflush:
            prospective = {
                "min_temperature": fields.get("min_temperature", config.min_temperature),
                "max_temperature": fields.get("max_temperature", config.max_temperature),
                "min_humidity": fields.get("min_humidity", config.min_humidity),
                "max_humidity": fields.get("max_humidity", config.max_humidity),
            }
        if prospective["min_temperature"] > prospective["max_temperature"]:
            raise ValueError("min_temperature must be <= max_temperature")
        if prospective["min_humidity"] > prospective["max_humidity"]:
            raise ValueError("min_humidity must be <= max_humidity")
        for key, value in fields.items():
            setattr(config, key, value)
        db.flush()
        return config


# ---------------------------------------------------------------------------
# TSK-047.2 — Device / User repositories (no commit, UNIQUE as source of truth)
# ---------------------------------------------------------------------------

_ALLOWED_STATUSES = frozenset({"active", "inactive", "maintenance", "error"})
_ALLOWED_DEVICE_TYPES = frozenset({"cold_room", "refrigerated_showcase"})
_ALLOWED_SENSOR_TYPES = frozenset({"temperature", "humidity", "energy"})


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


class DeviceSensorRepository:
    """TSK-059.2 — persistent Device -> DeviceSensor configuration.

    Repositories use flush only; commit is caller's responsibility.
    Deleting a sensor never touches sensor_readings history.
    """

    def list_by_device(self, db: Session, device_id: uuid.UUID) -> list[DeviceSensorORM]:
        return (
            db.query(DeviceSensorORM)
            .filter_by(device_id=device_id)
            .order_by(DeviceSensorORM.sensor_type.asc())
            .all()
        )

    def get(self, db: Session, device_id: uuid.UUID, sensor_type: str) -> DeviceSensorORM | None:
        if not isinstance(sensor_type, str):
            return None
        sensor_type = sensor_type.strip().lower()
        if not sensor_type:
            return None
        return (
            db.query(DeviceSensorORM)
            .filter_by(device_id=device_id, sensor_type=sensor_type)
            .first()
        )

    def create(self, db: Session, *, device_id: uuid.UUID, sensor_type: str) -> DeviceSensorORM:
        if not isinstance(sensor_type, str) or not sensor_type.strip():
            raise ValueError("sensor_type must be a non-empty string")
        normalized = sensor_type.strip().lower()
        if normalized not in _ALLOWED_SENSOR_TYPES:
            raise ValueError(f"sensor_type must be one of {sorted(_ALLOWED_SENSOR_TYPES)}")
        device = db.query(DeviceORM).filter_by(id=device_id).first()
        if device is None:
            raise ValueError(f"device_id {device_id} is not registered")
        obj = DeviceSensorORM(device_id=device_id, sensor_type=normalized)
        db.add(obj)
        db.flush()
        return obj

    def delete(self, db: Session, sensor: DeviceSensorORM) -> None:
        remaining = (
            db.query(DeviceSensorORM)
            .filter_by(device_id=sensor.device_id)
            .count()
        )
        if remaining <= 1:
            raise ValueError("device must keep at least one sensor configured")
        db.delete(sensor)
        db.flush()


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


class AuditLogRepository:
    """Persistence for immutable audit entries; intentionally no update/delete."""

    # TSK-059.5 — keys that must never reach audit_logs, even nested.
    _FORBIDDEN_VALUE_KEYS = frozenset(
        {"password", "new_password", "password_hash", "hash", "token", "secret"}
    )

    def create(
        self,
        db: Session,
        *,
        actor_user_id: uuid.UUID,
        action: str,
        resource: str,
        outcome: str = "success",
        old_value: str | dict | None = None,
        new_value: str | dict | None = None,
    ) -> AuditLogORM:
        if not isinstance(action, str) or not action.strip():
            raise ValueError("action must be a non-empty string")
        if not isinstance(resource, str) or not resource.strip():
            raise ValueError("resource must be a non-empty string")
        if not isinstance(outcome, str) or not outcome.strip():
            raise ValueError("outcome must be a non-empty string")
        entry = AuditLogORM(
            actor_user_id=actor_user_id,
            action=action.strip(),
            resource=resource.strip(),
            outcome=outcome.strip(),
            old_value=self._serialize_value(old_value, "old_value"),
            new_value=self._serialize_value(new_value, "new_value"),
        )
        db.add(entry)
        db.flush()
        return entry

    @classmethod
    def _serialize_value(cls, value: str | dict | None, field: str) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            cls._reject_forbidden_keys(value)
            return json.dumps(value, sort_keys=True, default=str)
        raise ValueError(f"{field} must be a str, dict or None")

    @classmethod
    def _reject_forbidden_keys(cls, payload: dict) -> None:
        for key, nested in payload.items():
            if str(key).strip().lower() in cls._FORBIDDEN_VALUE_KEYS:
                raise ValueError(
                    f"audit value key '{key}' is forbidden (secret material)"
                )
            if isinstance(nested, dict):
                cls._reject_forbidden_keys(nested)

    def list(
        self, db: Session, *, page: int = 1, per_page: int = 20
    ) -> tuple[int, list[AuditLogORM]]:
        query = db.query(AuditLogORM).order_by(AuditLogORM.created_at.desc())
        total = query.count()
        items = query.offset((page - 1) * per_page).limit(per_page).all()
        return total, items


class ExperimentRunRepository:
    """TSK-059.6 — experiment runs. Flush only; commit is caller's responsibility."""

    def create(
        self,
        db: Session,
        *,
        scenario: str,
        config_snapshot: str | dict | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> ExperimentRunORM:
        if not isinstance(scenario, str) or scenario.strip() not in EXPERIMENT_SCENARIOS:
            raise ValueError(
                f"scenario must be one of {sorted(EXPERIMENT_SCENARIOS)}"
            )
        snapshot = self._serialize_snapshot(config_snapshot)
        obj = ExperimentRunORM(
            scenario=scenario.strip(),
            config_snapshot=snapshot,
            started_at=started_at or datetime.now(timezone.utc),
            finished_at=finished_at,
        )
        db.add(obj)
        db.flush()
        return obj

    def get_by_id(self, db: Session, id: uuid.UUID) -> ExperimentRunORM | None:
        return db.query(ExperimentRunORM).filter_by(id=id).first()

    def list(
        self,
        db: Session,
        *,
        scenario: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[int, list[ExperimentRunORM]]:
        q = db.query(ExperimentRunORM)
        if scenario is not None:
            if scenario not in EXPERIMENT_SCENARIOS:
                raise ValueError(
                    f"scenario must be one of {sorted(EXPERIMENT_SCENARIOS)}"
                )
            q = q.filter(ExperimentRunORM.scenario == scenario)
        q = q.order_by(ExperimentRunORM.started_at.desc())
        total = q.count()
        items = q.offset((page - 1) * per_page).limit(per_page).all()
        return total, items

    @staticmethod
    def _serialize_snapshot(value: str | dict | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            parsed = json.loads(value)  # must be valid JSON
            return json.dumps(parsed, sort_keys=True, default=str)
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True, default=str)
        raise ValueError("config_snapshot must be a JSON str, dict or None")


class ExperimentMetricRepository:
    """TSK-059.6 — common comparable metrics. Flush only; no commit."""

    def append(
        self,
        db: Session,
        *,
        run_id: uuid.UUID,
        metric_type: str,
        value: float,
        timestamp: datetime | None = None,
    ) -> ExperimentMetricORM:
        if not isinstance(metric_type, str) or metric_type.strip() not in EXPERIMENT_METRIC_TYPES:
            raise ValueError(
                f"metric_type must be one of {sorted(EXPERIMENT_METRIC_TYPES)}"
            )
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("value must be numeric")
        obj = ExperimentMetricORM(
            run_id=run_id,
            metric_type=metric_type.strip(),
            value=value,
            timestamp=timestamp or datetime.now(timezone.utc),
        )
        db.add(obj)
        db.flush()
        return obj

    def bulk(
        self,
        db: Session,
        *,
        run_id: uuid.UUID,
        metrics: list[dict],
    ) -> list[ExperimentMetricORM]:
        result = []
        for m in metrics:
            result.append(
                self.append(
                    db,
                    run_id=run_id,
                    metric_type=m["metric_type"],
                    value=m["value"],
                    timestamp=m.get("timestamp"),
                )
            )
        return result

    def list(
        self,
        db: Session,
        *,
        run_id: uuid.UUID,
        metric_type: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[int, list[ExperimentMetricORM]]:
        q = db.query(ExperimentMetricORM).filter_by(run_id=run_id)
        if metric_type is not None:
            if metric_type not in EXPERIMENT_METRIC_TYPES:
                raise ValueError(
                    f"metric_type must be one of {sorted(EXPERIMENT_METRIC_TYPES)}"
                )
            q = q.filter(ExperimentMetricORM.metric_type == metric_type)
        q = q.order_by(ExperimentMetricORM.timestamp.asc())
        total = q.count()
        items = q.offset((page - 1) * per_page).limit(per_page).all()
        return total, items
