from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.database.infrastructure.models import (
    AlertORM,
    PredictionORM,
    QoSMetricORM,
    SensorReadingORM,
    TrafficClassificationORM,
)
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
        # Group by same device_code + timestamp (agrupación documentada, no mapper genérico)
        # Se asume que readings pertenecen al mismo bundle (mismo mensaje MQTT)
        by_key: dict[tuple[str, str], list[NormalizedReading]] = {}
        for r in readings:
            by_key.setdefault((r.device_code, r.timestamp), []).append(r)
        # Para TSK-042 se persiste 1 SensorReading por bundle; si hay múltiples keys, se usa la primera
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
