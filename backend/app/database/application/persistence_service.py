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
from app.database.infrastructure.models import (
    AlertORM,
    QoSMetricORM,
    SensorReadingORM,
    TrafficClassificationORM,
)
from app.events.domain import Alert
from app.qos.domain import QoSMetric
from app.qos.domain.work_item import WorkItem


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
        classification: TrafficClassification | None,
        qos_metric: QoSMetric | None = None,
        alerts: list[Alert] | None = None,
        predictions: list[dict] | None = None,
        run_id: uuid.UUID | None = None,
        reading_id: uuid.UUID | None = None,
        source_message_id: uuid.UUID | None = None,
        sensor_name: str | None = None,
        processing_version: int = 1,
    ) -> dict:
        """Persiste un bundle coherente SensorReading [1:1 TrafficClassification -> QoSMetric]/Alert/Prediction.

        TSK-059.7 — classification=None (WITHOUT_QOS) skips TrafficClassification
        and QoSMetric; run_id links rows to the experiment run (None = legacy).
        """
        was_in_transaction = db.in_transaction()
        try:
            sensor_row = self.sensor_repo.save(
                db,
                readings,
                device_id,
                run_id=run_id,
                reading_id=reading_id,
                source_message_id=source_message_id,
                sensor_name=sensor_name,
                processing_version=processing_version,
            )
            tc_row = None
            if classification is not None:
                tc_row = self.tc_repo.save(db, classification, sensor_row.id)
            qos_row = None
            if qos_metric is not None:
                if tc_row is None:
                    raise ValueError("qos_metric requires a classification")
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
                    alert_rows.append(
                        self.alert_repo.save(
                            db,
                            remapped,
                            run_id=run_id,
                            reading_id=(
                                sensor_row.id if processing_version >= 2 else None
                            ),
                        )
                    )
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
            if not was_in_transaction:
                db.commit()
        except Exception:
            if not was_in_transaction:
                db.rollback()
            raise
        return {
            "sensor_reading": sensor_row,
            "traffic_classification": tc_row,
            "qos_metric": qos_row,
            "alerts": alert_rows,
            "predictions": pred_rows,
        }

    def persist_work_item(
        self,
        db: Session,
        *,
        work_item: WorkItem,
        device_id: uuid.UUID,
        qos_metric: QoSMetric | None = None,
        alerts: list[Alert] | None = None,
        predictions: list[dict] | None = None,
    ) -> dict:
        """Persist one dispatched sensor reading with stable v2 traceability.

        Replaying a completed work item returns its already committed rows and
        does not create a second reading, classification, or alert.  A caller
        must use the same work UUID for a retry; unrelated readings are never
        collapsed by device/timestamp.
        """
        existing = db.get(SensorReadingORM, work_item.id)
        if existing is not None:
            if (
                existing.device_id != device_id
                or existing.sensor_name != work_item.sensor_name
                or existing.source_message_id != work_item.source_message_id
            ):
                raise ValueError("work item UUID conflicts with persisted reading context")
            classification = (
                db.query(TrafficClassificationORM)
                .filter_by(reading_id=existing.id)
                .first()
            )
            qos = (
                db.query(QoSMetricORM)
                .filter_by(classification_id=classification.id)
                .first()
                if classification is not None
                else None
            )
            return {
                "sensor_reading": existing,
                "traffic_classification": classification,
                "qos_metric": qos,
                "alerts": db.query(AlertORM).filter_by(reading_id=existing.id).all(),
                "predictions": list(existing.predictions),
            }

        classification = (
            work_item.classification.to_classification()
            if work_item.classification is not None
            else None
        )
        return self.persist_bundle(
            db,
            readings=[work_item.to_reading()],
            device_id=device_id,
            classification=classification,
            qos_metric=qos_metric,
            alerts=alerts,
            predictions=predictions,
            run_id=work_item.run_id,
            reading_id=work_item.id,
            source_message_id=work_item.source_message_id,
            sensor_name=work_item.sensor_name,
            processing_version=2,
        )
