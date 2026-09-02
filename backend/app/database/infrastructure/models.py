from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.infrastructure.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeviceORM(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str] = mapped_column(String, nullable=False)
    device_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    registration_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    sensor_readings: Mapped[list[SensorReadingORM]] = relationship(back_populates="device")
    alerts: Mapped[list[AlertORM]] = relationship(back_populates="device")


class SensorReadingORM(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    humidity: Mapped[float] = mapped_column(Float, nullable=False)
    energy: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    device: Mapped[DeviceORM] = relationship(back_populates="sensor_readings")
    traffic_classification: Mapped[TrafficClassificationORM | None] = relationship(
        back_populates="sensor_reading", uselist=False
    )
    predictions: Mapped[list[PredictionORM]] = relationship(back_populates="sensor_reading")


class TrafficClassificationORM(Base):
    __tablename__ = "traffic_classifications"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reading_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sensor_readings.id"), nullable=False, unique=True
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

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classification_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("traffic_classifications.id"), nullable=False
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

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    alerts: Mapped[list[AlertORM]] = relationship(back_populates="user")


class AlertORM(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    criticality: Mapped[float] = mapped_column(Float, nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    device: Mapped[DeviceORM] = relationship(back_populates="alerts")
    user: Mapped[UserORM] = relationship(back_populates="alerts")


class SystemConfigORM(Base):
    __tablename__ = "system_configs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    max_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    min_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    max_humidity: Mapped[float] = mapped_column(Float, nullable=False)
    min_humidity: Mapped[float] = mapped_column(Float, nullable=False)
    qos_algorithm: Mapped[str] = mapped_column(String, nullable=False)
    qos_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # No relationships per UML


class PredictionORM(Base):
    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reading_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sensor_readings.id"), nullable=False
    )
    predicted_alert: Mapped[str] = mapped_column(String, nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    prediction_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    sensor_reading: Mapped[SensorReadingORM] = relationship(back_populates="predictions")
