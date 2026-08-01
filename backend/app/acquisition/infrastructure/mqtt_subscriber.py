import json
import logging
from datetime import datetime

from ..message_queue import MessageQueue

logger = logging.getLogger(__name__)


class MQTTSubscriber:

    def __init__(self, message_queue: MessageQueue):
        self._queue = message_queue

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            self._queue.append({
                "topic": msg.topic,
                "payload": payload,
                "received_at": datetime.now().isoformat(timespec="seconds"),
            })
            logger.info("Mensaje recibido de %s", payload.get("device_code", "unknown"))
        except json.JSONDecodeError:
            logger.warning("Payload JSON malformado: %s", msg.payload)
