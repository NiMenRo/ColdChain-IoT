import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import BackendConfig
from app.acquisition import MessageQueue
from app.acquisition.infrastructure import MQTTClient, MQTTSubscriber

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

    # Start acquisition -> classification pipeline worker
    try:
        from app.acquisition.pipeline import AcquisitionPipeline

        app.state._acq_pipeline = AcquisitionPipeline(message_queue, app.state)
        app.state._acq_pipeline.start()
    except Exception:
        # If pipeline import or start fails in test environments, log and continue.
        # Avoid raising to keep test environments lightweight.
        logger.exception("Failed to start acquisition pipeline")

    # Include classification API router
    try:
        from app.classification.api import router as classification_router

        app.include_router(classification_router)
    except Exception:
        # router import may fail in some test environments; ignore to keep backwards compatibility
        pass

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
                "received_at": entry.get("received_at"),
                "topic": entry.get("topic"),
            }
        )
    return {"count": len(results), "results": results}
