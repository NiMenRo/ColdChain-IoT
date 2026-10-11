import logging
import uuid

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTClient:

    def __init__(
        self,
        host: str,
        port: int,
        client_id: str | None = None,
        username: str | None = None,
        password: str | None = None,
        tls_ca_cert: str | None = None,
    ):
        self._host = host
        self._port = port
        effective_client_id = client_id or f"coldchain-backend-{uuid.uuid4().hex[:8]}"
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=effective_client_id)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        # Suscripciones registradas: con sesiones limpias el broker las
        # olvida en cada reconexión y hay que renovarlas en on_connect.
        self._subscriptions: list[tuple[str, object, int]] = []
        if username:
            # TSK-056: broker credentials (never logged).
            self._client.username_pw_set(username, password or "")
        if tls_ca_cert:
            # TSK-056: strict server-certificate verification against
            # the configured CA. Never disable verification.
            self._client.tls_set(ca_certs=tls_ca_cert)

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

    def subscribe(self, topic: str, callback, qos: int = 0):
        self._client.on_message = callback
        self._subscriptions = [
            (t, cb, q) for (t, cb, q) in self._subscriptions if t != topic
        ] + [(topic, callback, qos)]
        rc, _ = self._client.subscribe(topic, qos=qos)
        if rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error("MQTT: suscripción a %s falló (rc=%s)", topic, rc)
        else:
            logger.info("MQTT suscrito a %s", topic)

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("MQTT conexión confirmada por el broker")
            # Renovar suscripciones: con sesión limpia el broker las olvida
            # en cada reconexión; sin esto el backend queda sordo en silencio.
            for topic, callback, qos in self._subscriptions:
                client.on_message = callback
                rc, _ = client.subscribe(topic, qos=qos)
                if rc != mqtt.MQTT_ERR_SUCCESS:
                    logger.error("MQTT: re-suscripción a %s falló (rc=%s)", topic, rc)
                else:
                    logger.info("MQTT re-suscrito a %s", topic)
        else:
            logger.error("MQTT: broker rechazó conexión (rc=%s)", reason_code)

    @staticmethod
    def _on_disconnect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("MQTT desconexión limpia")
        else:
            logger.warning("MQTT: desconexión inesperada (rc=%s)", reason_code)
