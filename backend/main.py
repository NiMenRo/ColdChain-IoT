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

    yield

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
