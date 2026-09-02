import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import BackendConfig
from app.acquisition import MessageQueue
from app.acquisition.infrastructure import MQTTClient, MQTTSubscriber
try:
    from app.database.application.persistence_service import PersistenceService
except ImportError:
    PersistenceService = None  # type: ignore
from app.events.domain import ThresholdConfig
from app.events.application.event_processing_service import EventProcessingService
from app.qos.application.qos_metrics_service import QoSMetricsService
from app.qos.application.traffic_planning_service import TrafficPlanningService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = BackendConfig()

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    mqtt_client = MQTTClient(config.mqtt_host, config.mqtt_port)
    mqtt_client.start()

    message_queue = MessageQueue(config.max_queue_size)
    subscriber = MQTTSubscriber(message_queue)
    mqtt_client.subscribe(config.mqtt_topic, subscriber.on_message, config.mqtt_qos)

    app.state.mqtt_client = mqtt_client
    app.state.message_queue = message_queue
    # Prepare a place to store classification results produced by the integration pipeline
    app.state.classifications = []
    app.state.qos_service = TrafficPlanningService()
    app.state.qos_metrics_service = QoSMetricsService()
    app.state.qos_records = []

    # Initialize event processing service with cold-storage thresholds
    threshold_config = ThresholdConfig(
        min_temperature=0.0,
        max_temperature=4.0,
        min_humidity=85.0,
        max_humidity=90.0,
        allowed_energy_states=frozenset({"on"}),
    )
    app.state.event_processing_service = EventProcessingService(
        threshold_config=threshold_config
    )
    try:
        app.state.persistence_service = PersistenceService() if PersistenceService else None
    except Exception:
        logger.exception("PersistenceService no disponible")
        app.state.persistence_service = None
    # TSK-042A/B: seed Device + User before pipeline can persist (FKs)
    try:
        if app.state.persistence_service is not None:
            from app.database.infrastructure.session import SessionLocal
            from app.database.seed import seed_all

            with SessionLocal() as db:
                seed_all(db)
    except Exception:
        logger.exception("Seed devices/users failed")
    app.state.events = []
    app.state.alerts = []
    app.state.enriched_events = []

    # Start acquisition -> classification pipeline worker
    try:
        from app.acquisition.pipeline import AcquisitionPipeline

        app.state._acq_pipeline = AcquisitionPipeline(message_queue, app.state)
        app.state._acq_pipeline.start()
    except Exception:
        # If pipeline import or start fails in test environments, log and continue.
        # Avoid raising to keep test environments lightweight.
        logger.exception("Failed to start acquisition pipeline")

    # Include API routers
    try:
        from app.classification.api import router as classification_router

        app.include_router(classification_router)
    except Exception:
        # router import may fail in some test environments; ignore to keep backwards compatibility
        pass

    try:
        from app.qos.api import router as qos_router

        app.include_router(qos_router)
    except Exception:
        logger.exception("Failed to register QoS API router")

    try:
        from app.events.api import router as events_router

        app.include_router(events_router)
    except Exception:
        logger.exception("Failed to register Events API router")

    try:
        from app.history.api.router import router as history_router

        app.include_router(history_router)
    except Exception:
        logger.exception("Failed to register History API router")

    yield

    # Shutdown pipeline and MQTT client
    try:
        if hasattr(app.state, "_acq_pipeline"):
            app.state._acq_pipeline.stop()
    except Exception:
        logging.getLogger(__name__).exception("Error stopping acquisition pipeline")

    mqtt_client.stop()


app = FastAPI(title="ColdChain API", lifespan=lifespan)


@app.get("/acquisition/messages")
def get_messages():
    # TODO: eliminar cuando exista el pipeline completo de adquisición (TSK-010+)
    return {
        "connected": app.state.mqtt_client.is_connected,
        "count": len(app.state.message_queue.get_all()),
        "messages": app.state.message_queue.get_all(),
    }


@app.get("/classification/results")
def get_classification_results():
    """Return recent classification results produced by the acquisition->classification pipeline.

    This endpoint is intended for local testing and debugging: it exposes the in-memory
    list of classification entries produced by the integration pipeline. Each entry
    contains the TrafficClassification object and a reference to the normalized reading.
    """
    results = []
    for entry in getattr(app.state, "classifications", []):
        classification = entry.get("classification")
        reading = entry.get("reading")
        results.append(
            {
                "id": str(classification.id),
                "reading_id": str(classification.reading_id),
                "criticality": classification.criticality,
                "priority": classification.priority,
                "queue": classification.queue,
                "classification_time": classification.classification_time.isoformat(timespec="seconds"),
                "timestamp": classification.timestamp.isoformat(timespec="seconds"),
                "device_code": entry.get("device_code"),
                "sensor_name": getattr(reading, "sensor_name", None),
                "value": getattr(reading, "value", None),
                "raw_value": getattr(reading, "raw_value", None),
                "received_at": entry.get("received_at"),
                "topic": entry.get("topic"),
            }
        )
    return {"count": len(results), "results": results}
