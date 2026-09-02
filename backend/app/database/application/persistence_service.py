from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.database.infrastructure.repositories import (
    AlertRepository,
    PredictionRepository,
    QoSMetricRepository,
    SensorReadingRepository,
    TrafficClassificationRepository,
)
from app.events.domain import Alert
from app.qos.domain import QoSMetric


class PersistenceService:
    """Orquestador transaccional. No calcula QoS ni fabrica Device/User."""

    def __init__(
        self,
        sensor_repo: SensorReadingRepository | None = None,
        tc_repo: TrafficClassificationRepository | None = None,
        qos_repo: QoSMetricRepository | None = None,
        alert_repo: AlertRepository | None = None,
        prediction_repo: PredictionRepository | None = None,
    ) -> None:
        self.sensor_repo = sensor_repo or SensorReadingRepository()
        self.tc_repo = tc_repo or TrafficClassificationRepository()
        self.qos_repo = qos_repo or QoSMetricRepository()
        self.alert_repo = alert_repo or AlertRepository()
        self.prediction_repo = prediction_repo or PredictionRepository()

    def persist_bundle(
        self,
        db: Session,
        *,
        readings: list[NormalizedReading],
        device_id: uuid.UUID,
        classification: TrafficClassification,
        qos_metric: QoSMetric | None = None,
        alerts: list[Alert] | None = None,
        predictions: list[dict] | None = None,
    ) -> dict:
        """Persiste un bundle coherente SensorReading 1:1 TrafficClassification -> QoSMetric/Alert/Prediction."""
        # Atomic bundle: SensorReading -> TC -> QoS -> Alert/Prediction
        ctx = db.begin_nested() if db.in_transaction() else db.begin()
        with ctx:
            sensor_row = self.sensor_repo.save(db, readings, device_id)
            tc_row = self.tc_repo.save(db, classification, sensor_row.id)
            qos_row = None
            if qos_metric is not None:
                # Re-asociar classification_id al TC persistido si difiere
                if qos_metric.classification_id != tc_row.id:
                    qos_metric = QoSMetric(
                        id=qos_metric.id,
                        classification_id=tc_row.id,
                        latency=qos_metric.latency,
                        packet_loss=qos_metric.packet_loss,
                        throughput=qos_metric.throughput,
                        pdr=qos_metric.pdr,
                        jitter=qos_metric.jitter,
                        timestamp=qos_metric.timestamp,
                    )
                qos_row = self.qos_repo.save(db, qos_metric)
            alert_rows = []
            if alerts:
                for a in alerts:
                    # Remap to real DeviceORM.id of bundle (same as SensorReading.device_id)
                    remapped = Alert(
                        id=a.id,
                        device_id=sensor_row.device_id,
                        user_id=a.user_id,
                        type=a.type,
                        message=a.message,
                        criticality=a.criticality,
                        acknowledged=a.acknowledged,
                        created_at=a.created_at,
                    )
                    alert_rows.append(self.alert_repo.save(db, remapped))
            pred_rows = []
            if predictions:
                for p in predictions:
                    pred_rows.append(
                        self.prediction_repo.save(
                            db,
                            reading_id=sensor_row.id,
                            predicted_alert=p["predicted_alert"],
                            probability=p["probability"],
                            model_version=p["model_version"],
                            prediction_time=p.get("prediction_time"),
                        )
                    )
        return {
            "sensor_reading": sensor_row,
            "traffic_classification": tc_row,
            "qos_metric": qos_row,
            "alerts": alert_rows,
            "predictions": pred_rows,
        }
