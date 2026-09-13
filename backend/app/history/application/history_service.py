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
    def summary(self, db: Session):
        return {
            "total_devices": db.query(DeviceORM).count(),
            "total_readings": db.query(SensorReadingORM).count(),
            "total_classifications": db.query(TrafficClassificationORM).count(),
            "total_qos_metrics": db.query(QoSMetricORM).count(),
            "total_alerts": db.query(AlertORM).count(),
            "total_predictions": db.query(PredictionORM).count(),
            "alerts_by_type": dict(db.query(AlertORM.type, func.count()).group_by(AlertORM.type).all()),
            "readings_by_device": dict(db.query(DeviceORM.code, func.count(SensorReadingORM.id)).join(SensorReadingORM, DeviceORM.id==SensorReadingORM.device_id).group_by(DeviceORM.code).all()),
            "traffic_by_priority": dict(db.query(TrafficClassificationORM.priority, func.count()).group_by(TrafficClassificationORM.priority).all()),
            "qos_by_queue": dict(db.query(TrafficClassificationORM.queue, func.count(QoSMetricORM.id)).join(QoSMetricORM, QoSMetricORM.classification_id==TrafficClassificationORM.id).group_by(TrafficClassificationORM.queue).all()),
        }
