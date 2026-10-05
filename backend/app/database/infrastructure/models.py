from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database.infrastructure.base import Base

HUMAN_USER_ROLES = frozenset({"admin", "supervisor", "operador", "auditor"})
TECHNICAL_USER_ROLE = "system"
EXPERIMENT_SCENARIOS = frozenset({"WITH_QOS", "WITHOUT_QOS"})
EXPERIMENT_METRIC_TYPES = frozenset(
    {
        "messages_received",
        "messages_invalid",
        "readings_persisted",
        "alerts_generated",
        "backlog",
        "ingest_to_persist_ms",
        "ingest_to_alert_ms",
    }
)
VALID_USER_ROLES = HUMAN_USER_ROLES | {TECHNICAL_USER_ROLE}
USER_ROLE_RESPONSIBILITIES = {
    "admin": "Administracion general del sistema",
    "supervisor": "Supervision, configuracion y gestion de alertas",
    "operador": "Operacion diaria y atencion de alertas",
    "auditor": "Consulta de informacion historica y trazabilidad",
    "system": "Identidad tecnica para procesos internos",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeviceORM(Base):
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("code", name="uq_devices_code"),
        CheckConstraint(
            "status IN ('active','inactive','maintenance','error')",
            name="ck_devices_status",
        ),
        CheckConstraint(
            "device_type IN ('cold_room','refrigerated_showcase')",
            name="ck_devices_device_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str] = mapped_column(String, nullable=False)
    device_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    registration_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    sensor_readings: Mapped[list[SensorReadingORM]] = relationship(back_populates="device")
    alerts: Mapped[list[AlertORM]] = relationship(back_populates="device")
    device_sensors: Mapped[list[DeviceSensorORM]] = relationship(back_populates="device")


class DeviceSensorORM(Base):
    """TSK-059.2 — persistent per-device sensor configuration.

    One row per enabled sensor; SensorReading stays aggregated (TSK-059.3).
    """

    __tablename__ = "device_sensors"
    __table_args__ = (
        UniqueConstraint("device_id", "sensor_type", name="uq_device_sensors_device_sensor"),
        CheckConstraint(
            "sensor_type IN ('temperature','humidity','energy')",
            name="ck_device_sensors_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("devices.id"), nullable=False)
    sensor_type: Mapped[str] = mapped_column(String, nullable=False)

    device: Mapped[DeviceORM] = relationship(back_populates="device_sensors")


class SensorReadingORM(Base):
    __tablename__ = "sensor_readings"

    __table_args__ = (
        CheckConstraint(
            "energy IS NULL OR energy IN ('on','off')",
            name="ck_readings_energy",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("devices.id"), nullable=False)
    # TSK-059.3 — NULL means the sensor is not enabled for the device
    # (DeviceSensor configuration), not a sensor failure.
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    # TSK-059.6 — NULL means legacy reading outside any experiment run.
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("experiment_runs.id"), nullable=True, index=True
    )

    device: Mapped[DeviceORM] = relationship(back_populates="sensor_readings")
    traffic_classification: Mapped[TrafficClassificationORM | None] = relationship(
        back_populates="sensor_reading", uselist=False
    )
    predictions: Mapped[list[PredictionORM]] = relationship(back_populates="sensor_reading")
    experiment_run: Mapped[ExperimentRunORM | None] = relationship(back_populates="sensor_readings")


class TrafficClassificationORM(Base):
    __tablename__ = "traffic_classifications"
    __table_args__ = (
        CheckConstraint(
            "criticality >= 3 AND criticality <= 9",
            name="ck_tc_criticality",
        ),
        CheckConstraint(
            "priority IN ('low','medium','high')",
            name="ck_tc_priority",
        ),
        CheckConstraint(
            "queue IN ('FIFO','Round Robin','WFQ')",
            name="ck_tc_queue",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reading_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sensor_readings.id"), nullable=False, unique=True
    )
    criticality: Mapped[float] = mapped_column(Float, nullable=False)
    priority: Mapped[str] = mapped_column(String, nullable=False)
    queue: Mapped[str] = mapped_column(String, nullable=False)
    classification_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    sensor_reading: Mapped[SensorReadingORM] = relationship(back_populates="traffic_classification")
    qos_metrics: Mapped[list[QoSMetricORM]] = relationship(back_populates="classification")


class QoSMetricORM(Base):
    __tablename__ = "qos_metrics"
    __table_args__ = (
        CheckConstraint("latency >= 0", name="ck_qos_latency"),
        CheckConstraint(
            "packet_loss >= 0 AND packet_loss <= 100",
            name="ck_qos_packet_loss",
        ),
        CheckConstraint("throughput >= 0", name="ck_qos_throughput"),
        CheckConstraint("pdr >= 0 AND pdr <= 100", name="ck_qos_pdr"),
        CheckConstraint("jitter >= 0", name="ck_qos_jitter"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    classification_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("traffic_classifications.id"), nullable=False
    )
    latency: Mapped[float] = mapped_column(Float, nullable=False)
    packet_loss: Mapped[float] = mapped_column(Float, nullable=False)
    throughput: Mapped[float] = mapped_column(Float, nullable=False)
    pdr: Mapped[float] = mapped_column(Float, nullable=False)
    jitter: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    classification: Mapped[TrafficClassificationORM] = relationship(back_populates="qos_metrics")


class UserORM(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "role IN ('admin','supervisor','operador','auditor','system')",
            name="ck_users_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    alerts: Mapped[list[AlertORM]] = relationship(back_populates="user")

    @validates("email")
    def _normalize_email(self, key: str, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("email must be a string")
        return value.strip().lower()

    @validates("role")
    def _validate_role(self, key: str, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("role must be a string")
        normalized = value.strip().lower()
        if normalized not in VALID_USER_ROLES:
            raise ValueError(
                "role must be one of admin, supervisor, operador, auditor, or system"
            )
        return normalized


class AuditLogORM(Base):
    """Immutable record of an action performed by a human user.

    The application never exposes write endpoints for this entity.  Rows are
    created only by application services in the transaction of the audited
    operation, preserving a reliable actor/action/result relationship.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    resource: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False, default="success")
    # TSK-059.5 — JSON-serialized old/new values (NULL when not applicable).
    # Never passwords, hashes, tokens or secrets.
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )


class AlertORM(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("devices.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    criticality: Mapped[float] = mapped_column(Float, nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    # TSK-059.6 — NULL means legacy alert outside any experiment run.
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("experiment_runs.id"), nullable=True, index=True
    )

    device: Mapped[DeviceORM] = relationship(back_populates="alerts")
    user: Mapped[UserORM] = relationship(back_populates="alerts")
    experiment_run: Mapped[ExperimentRunORM | None] = relationship(back_populates="alerts")


class SystemConfigORM(Base):
    __tablename__ = "system_configs"
    __table_args__ = (
        CheckConstraint(
            "min_temperature <= max_temperature",
            name="ck_system_config_temp_range",
        ),
        CheckConstraint(
            "min_humidity <= max_humidity",
            name="ck_system_config_hum_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    max_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    min_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    max_humidity: Mapped[float] = mapped_column(Float, nullable=False)
    min_humidity: Mapped[float] = mapped_column(Float, nullable=False)
    qos_algorithm: Mapped[str] = mapped_column(String, nullable=False)
    qos_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # No relationships per UML


class PredictionORM(Base):
    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reading_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sensor_readings.id"), nullable=False
    )
    predicted_alert: Mapped[str] = mapped_column(String, nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    prediction_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    sensor_reading: Mapped[SensorReadingORM] = relationship(back_populates="predictions")


class ExperimentRunORM(Base):
    """TSK-059.6 — one comparable experiment execution (WITH_QOS/WITHOUT_QOS).

    Common metrics live in ExperimentMetric; QoS-specific data stays in
    TrafficClassification/QoSMetric (WITH_QOS only).
    """

    __tablename__ = "experiment_runs"
    __table_args__ = (
        CheckConstraint(
            "scenario IN ('WITH_QOS','WITHOUT_QOS')",
            name="ck_experiment_runs_scenario",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scenario: Mapped[str] = mapped_column(String, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    metrics: Mapped[list[ExperimentMetricORM]] = relationship(back_populates="run")
    sensor_readings: Mapped[list[SensorReadingORM]] = relationship(back_populates="experiment_run")
    alerts: Mapped[list[AlertORM]] = relationship(back_populates="experiment_run")

    @validates("scenario")
    def _validate_scenario(self, key: str, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("scenario must be a string")
        normalized = value.strip()
        if normalized not in EXPERIMENT_SCENARIOS:
            raise ValueError("scenario must be one of WITH_QOS, WITHOUT_QOS")
        return normalized


class ExperimentMetricORM(Base):
    """TSK-059.6 — one comparable measurement of an experiment run."""

    __tablename__ = "experiment_metrics"
    __table_args__ = (
        CheckConstraint(
            "metric_type IN ('messages_received','messages_invalid','readings_persisted',"
            "'alerts_generated','backlog','ingest_to_persist_ms','ingest_to_alert_ms')",
            name="ck_experiment_metrics_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("experiment_runs.id"), nullable=False, index=True
    )
    metric_type: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )

    run: Mapped[ExperimentRunORM] = relationship(back_populates="metrics")

    @validates("metric_type")
    def _validate_metric_type(self, key: str, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("metric_type must be a string")
        normalized = value.strip()
        if normalized not in EXPERIMENT_METRIC_TYPES:
            raise ValueError(
                "metric_type must be one of messages_received, messages_invalid, "
                "readings_persisted, alerts_generated, backlog, ingest_to_persist_ms, "
                "ingest_to_alert_ms"
            )
        return normalized
