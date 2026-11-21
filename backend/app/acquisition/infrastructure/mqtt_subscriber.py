import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from ..device_origin_identifier import DeviceOriginIdentifier
from ..message_queue import MessageQueue
from .mqtt_message_validator import MQTTMessageValidator, MessageValidationError

logger = logging.getLogger(__name__)


class MQTTSubscriber:

    def __init__(self, message_queue: MessageQueue):
        self._queue = message_queue
        self._validator = MQTTMessageValidator()
        self._origin_identifier = DeviceOriginIdentifier()

    @property
    def validator(self) -> MQTTMessageValidator:
        return self._validator

    @property
    def origin_identifier(self) -> DeviceOriginIdentifier:
        return self._origin_identifier

    def on_message(self, client, userdata, msg):
        payload_data = None

        try:
            payload_data = json.loads(msg.payload.decode())
            validated_payload = self._validator.validate(payload_data)
            device_origin = self._origin_identifier.identify(validated_payload)
            # Seal the experimental context at reception.  A message that is
            # still in transit when a run finishes keeps the context it was
            # received under; downstream stages never re-resolve the scenario.
            message = {
                "topic": msg.topic,
                "payload": validated_payload,
                "device_origin": {
                    "device_code": device_origin.device_code,
                    "device_type": device_origin.device_type,
                },
            }
            if not self._queue.append_received(message):
                logger.warning(
                    "Mensaje de dispositivo %s rechazado: cola llena o ejecución en drenaje "
                    "(capacidad %s)",
                    device_origin.device_code,
                    getattr(self._queue, "capacity", "?"),
                )
                self._record_rejected_metric(message.get("run_id"))
                return
            logger.info(
                "Mensaje recibido de dispositivo %s (%s)",
                device_origin.device_code,
                device_origin.device_type,
            )
        except json.JSONDecodeError:
            self._validator.register_invalid(msg.payload, "Payload JSON malformado", getattr(msg, "topic", None))
            logger.warning("Payload JSON malformado: %s", msg.payload)
            self._record_invalid_metric()
        except MessageValidationError as exc:
            self._validator.register_invalid(payload_data or msg.payload, str(exc), getattr(msg, "topic", None))
            logger.warning("Mensaje MQTT inválido: %s", exc)
            self._record_invalid_metric()
        except ValueError as exc:
            self._validator.register_invalid(payload_data or msg.payload, str(exc), getattr(msg, "topic", None))
            logger.warning("Mensaje MQTT sin dispositivo identificado: %s", exc)
            self._record_invalid_metric()

    @staticmethod
    def _record_invalid_metric() -> None:
        """TSK-059.7 — count real register_invalid events for the active run.

        No-op without an active run, so legacy behavior is untouched.
        """
        MQTTSubscriber._record_run_metric("messages_invalid")

    @staticmethod
    def _record_rejected_metric(run_id: str | None) -> None:
        """Attribute the rejection to the context sealed with this message."""
        if run_id is None:
            return
        from app.experiments.metrics import record_metrics

        record_metrics(UUID(run_id), [
            ("messages_rejected_transport", 1.0, datetime.now(timezone.utc)),
        ])

    @staticmethod
    def _record_run_metric(metric_type: str) -> None:
        from app.experiments.active import get_active_run
        from app.experiments.metrics import record_metrics

        active = get_active_run()
        if active is None:
            return
        record_metrics(
            active[0],
            [(metric_type, 1.0, datetime.now(timezone.utc))],
        )
