import json
import logging

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTClient:

    def __init__(self, host: str, port: int, client_id: str = "coldchain-simulator"):
        self._host = host
        self._port = port
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    def start(self):
        try:
            self._client.connect(self._host, self._port)
            self._client.loop_start()
            logger.info("MQTT conectado a %s:%s", self._host, self._port)
        except Exception as e:
            logger.error("MQTT: error de conexión - %s", e)
            raise

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()
        logger.info("MQTT desconectado")

    def publish(self, topic: str, payload: dict, qos: int = 0) -> bool:
        try:
            info = self._client.publish(topic, json.dumps(payload), qos=qos)
            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug("MQTT publicado en %s", topic)
                return True
            logger.warning("MQTT: error al publicar en %s (rc=%d)", topic, info.rc)
            return False
        except Exception as e:
            logger.error("MQTT: excepción al publicar - %s", e)
            return False

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected()

    @staticmethod
    def _on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("MQTT conexión confirmada por el broker")
        else:
            logger.error("MQTT: broker rechazó conexión (rc=%s)", reason_code)

    @staticmethod
    def _on_disconnect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("MQTT desconexión limpia")
        else:
            logger.warning("MQTT: desconexión inesperada (rc=%s)", reason_code)
