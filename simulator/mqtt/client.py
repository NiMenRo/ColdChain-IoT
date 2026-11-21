import json
import logging
import os
import threading
import time
import uuid

import paho.mqtt.client as mqtt
from .trace import record_trace

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
        effective_client_id = client_id or f"coldchain-simulator-{uuid.uuid4().hex[:8]}"
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=effective_client_id)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_publish = self._on_publish
        self._publication_lock = threading.RLock()
        self._pending_publications = {}
        self._current_publication = None
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
            if os.getenv("COLDCHAIN_MANAGED_EVIDENCE") == "true":
                record_trace("producer_opened", run_id=os.getenv("COLDCHAIN_RUN_ID"))
            logger.info("MQTT conectado a %s:%s", self._host, self._port)
        except Exception as e:
            logger.error("MQTT: error de conexión - %s", e)
            raise

    def stop(self):
        managed = os.getenv("COLDCHAIN_MANAGED_EVIDENCE") == "true"
        if managed:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with self._publication_lock:
                    if not self._pending_publications:
                        break
                time.sleep(0.01)
        self._client.disconnect()
        self._client.loop_stop()
        if managed:
            with self._publication_lock:
                pending = len(self._pending_publications)
            record_trace("producer_closed", run_id=os.getenv("COLDCHAIN_RUN_ID"),
                         pending_publications=pending)
        logger.info("MQTT desconectado")

    def publish(self, topic: str, payload: dict, qos: int = 0) -> bool:
        # Serialize once: byte count is exactly the MQTT application payload,
        # excluding topic, MQTT headers and TLS/TCP overhead.
        try:
            wire_payload = json.dumps(payload, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError):
            logger.exception("MQTT: payload is not valid JSON; nothing was published")
            return False
        context = {
            "trace": payload.get("trace"),
            "device_code": payload.get("device_code"),
            "generated_at": payload.get("timestamp"),
            "size_bytes": len(wire_payload), "qos": qos,
        }
        record_trace("publish_attempt", **context)
        try:
            with self._publication_lock:
                self._current_publication = context
                try:
                    info = self._client.publish(topic, wire_payload, qos=qos)
                    if info.rc == mqtt.MQTT_ERR_SUCCESS:
                        record_trace("publish_accepted", **context)
                        if not context.get("completed"):
                            self._pending_publications[info.mid] = context
                finally:
                    self._current_publication = None
            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug("MQTT publicado en %s", topic)
                return True
            logger.warning("MQTT: error al publicar en %s (rc=%d)", topic, info.rc)
            record_trace("publish_error", **context)
            return False
        except Exception as e:
            record_trace("publish_error", **context)
            logger.error("MQTT: excepción al publicar - %s", e)
            return False

    def _on_publish(self, client, userdata, mid, reason_code, properties):
        # RLock also covers synchronous QoS-0 completion inside publish().
        with self._publication_lock:
            context = self._pending_publications.pop(mid, None)
            if context is None:
                context = self._current_publication
            if context is None:
                logger.warning("Unmatched publication completion; trace is incomplete")
                record_trace("publication_unmatched", mqtt_mid=mid)
                return
            context["completed"] = True
            failed = bool(getattr(reason_code, "is_failure", False))
            record_trace("publish_error" if failed else "publish_complete", **context)

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
