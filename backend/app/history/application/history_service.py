from __future__ import annotations
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.infrastructure.models import DeviceORM, SensorReadingORM, TrafficClassificationORM, QoSMetricORM, AlertORM, PredictionORM
from app.history.infrastructure.reading_history_repository import ReadingHistoryRepository
from app.history.infrastructure.classification_history_repository import ClassificationHistoryRepository
from app.history.infrastructure.qos_history_repository import QoSHistoryRepository
from app.history.infrastructure.alert_history_repository import AlertHistoryRepository
from app.history.infrastructure.prediction_history_repository import PredictionHistoryRepository
from app.history.infrastructure.device_history_repository import DeviceHistoryRepository

class HistoryService:
    def __init__(self):
        self.readings = ReadingHistoryRepository()
        self.classifications = ClassificationHistoryRepository()
        self.qos = QoSHistoryRepository()
        self.alerts = AlertHistoryRepository()
        self.predictions = PredictionHistoryRepository()
        self.devices = DeviceHistoryRepository()
    def summary(self, db: Session, run_id=None):
        """Global summary, or scoped to one experiment run.

        TC/QoS rows carry no run_id (UML 1:1 via SensorReading); the run
        linkage resolves through SensorReading.run_id (and Alert.run_id
        directly). Legacy NULL rows only appear in unfiltered mode.
        `total_devices` is never run-scoped (devices are not per-run).
        """
        from uuid import UUID as _UUID
        scoped = run_id is not None
        if scoped and not isinstance(run_id, _UUID):
            raise ValueError("run_id must be a UUID")
        readings = db.query(SensorReadingORM)
        alerts = db.query(AlertORM)
        if scoped:
            readings = readings.filter(SensorReadingORM.run_id == run_id)
            alerts = alerts.filter(AlertORM.run_id == run_id)
        tc = (
            db.query(TrafficClassificationORM)
            .join(SensorReadingORM, TrafficClassificationORM.reading_id == SensorReadingORM.id)
        )
        preds = (
            db.query(PredictionORM)
            .join(SensorReadingORM, PredictionORM.reading_id == SensorReadingORM.id)
        )
        if scoped:
            preds = preds.filter(SensorReadingORM.run_id == run_id)
        qos = (
            db.query(TrafficClassificationORM.queue, func.count(QoSMetricORM.id))
            .join(QoSMetricORM, QoSMetricORM.classification_id == TrafficClassificationORM.id)
            .join(SensorReadingORM, TrafficClassificationORM.reading_id == SensorReadingORM.id)
        )
        # NOTE: total_qos_metrics uses a plain count query, NOT qos.count():
        # qos selects (queue, count(...)) without GROUP BY and .count() over
        # it is invalid SQL on Postgres (GroupingError). Same run filter.
        qos_total = db.query(QoSMetricORM)
        if scoped:
            tc = tc.filter(SensorReadingORM.run_id == run_id)
            qos = qos.filter(SensorReadingORM.run_id == run_id)
            qos_total = (
                qos_total
                .join(TrafficClassificationORM, QoSMetricORM.classification_id == TrafficClassificationORM.id)
                .join(SensorReadingORM, TrafficClassificationORM.reading_id == SensorReadingORM.id)
                .filter(SensorReadingORM.run_id == run_id)
            )
        return {
            "total_devices": db.query(DeviceORM).count(),
            "run_id": str(run_id) if scoped else None,
            "total_readings": readings.count(),
            "total_classifications": tc.count(),
            "total_qos_metrics": qos_total.count(),
            "total_alerts": alerts.count(),
            "total_predictions": preds.count(),
            "alerts_by_type": dict(alerts.with_entities(AlertORM.type, func.count()).group_by(AlertORM.type).all()),
            "readings_by_device": dict(db.query(DeviceORM.code, func.count(SensorReadingORM.id)).join(SensorReadingORM, DeviceORM.id==SensorReadingORM.device_id).filter(SensorReadingORM.run_id == run_id if scoped else True).group_by(DeviceORM.code).all()),
            "traffic_by_priority": dict(tc.with_entities(TrafficClassificationORM.priority, func.count()).group_by(TrafficClassificationORM.priority).all()),
            "qos_by_queue": dict(qos.group_by(TrafficClassificationORM.queue).all()),
            # Conteo de lecturas por estado energético ('on'/'off'). Los nulos se
            # excluyen: null significa sensor de energía no habilitado, no apagado.
            "energy_by_state": dict(readings.with_entities(SensorReadingORM.energy, func.count()).filter(SensorReadingORM.energy.isnot(None)).group_by(SensorReadingORM.energy).all()),
        }
