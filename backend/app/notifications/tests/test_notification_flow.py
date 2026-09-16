"""Integration and flow tests for the Notification module (TSK-040).

Validates the complete lifecycle:
Alert simulation -> NotificationService -> NotificationManager -> Channel execution ->
Delivery result -> Status recording -> API query & Alert acknowledgment.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.acquisition.normalizer import TelemetryNormalizer
from app.classification.application.classification_service import ClassificationService
from app.classification.application.criticality_calculator import CriticalityCalculator
from app.classification.application.priority_assigner import PriorityAssigner
from app.classification.application.risk_matrix_evaluator import RiskMatrixEvaluator
from app.events.application.event_processing_service import EventProcessingService
from app.events.domain import Alert, ThresholdConfig
from app.notifications.api import router as notifications_router
from app.notifications.application import (
    AlertAcknowledgementService,
    DashboardNotificationChannel,
    EmailNotificationChannel,
    NotificationChannelRegistry,
    NotificationChannelSender,
    NotificationManager,
    NotificationSendRequest,
    NotificationSendResult,
    NotificationService,
    PushNotificationChannel,
    SMSNotificationChannel,
)
from app.notifications.domain import (
    Notification,
    NotificationChannel,
    NotificationStatus,
)


class FailingChannel(NotificationChannelSender):
    """Test channel that simulates network or service failures."""

    def __init__(self, channel: NotificationChannel = NotificationChannel.EMAIL) -> None:
        self.channel = channel

    def _deliver(self, request: NotificationSendRequest) -> str:
        raise ConnectionError("SMTP gateway unreachable: connection timed out")


class NotificationModuleFlowTests(unittest.TestCase):
    """Comprehensive flow and integration tests for the notification subsystem."""

    def setUp(self) -> None:
        # 1. Channels with delivery logs
        self.dashboard_deliveries: list[dict] = []
        self.email_deliveries: list[dict] = []
        self.sms_deliveries: list[dict] = []
        self.push_deliveries: list[dict] = []

        self.dashboard_channel = DashboardNotificationChannel(deliveries=self.dashboard_deliveries)
        self.email_channel = EmailNotificationChannel(deliveries=self.email_deliveries)
        self.sms_channel = SMSNotificationChannel(deliveries=self.sms_deliveries)
        self.push_channel = PushNotificationChannel(deliveries=self.push_deliveries)

        self.registry = NotificationChannelRegistry(
            channels=[
                self.dashboard_channel,
                self.email_channel,
                self.sms_channel,
                self.push_channel,
            ]
        )

        # 2. NotificationManager configured with channel routing by alert type
        self.manager = NotificationManager(
            default_channel=NotificationChannel.DASHBOARD,
            channel_by_alert_type={
                "TEMPERATURE_EXCEEDED": NotificationChannel.EMAIL,
                "ENERGY_STATE_ANOMALY": NotificationChannel.SMS,
                "HUMIDITY_ABOVE_MAX": NotificationChannel.PUSH,
            },
        )

        # 3. NotificationService and AcknowledgementService
        self.notification_service = NotificationService(
            manager=self.manager,
            channel_registry=self.registry,
            recipient_resolver=lambda alert: f"user-{alert.user_id}@coldchain.internal",
        )
        self.ack_service = AlertAcknowledgementService()

        # 4. FastAPI test app with shared state
        self.app = FastAPI(title="ColdChain Notifications Test App")
        self.app.state.notifications = []
        self.app.state.alerts = []
        self.app.state.notification_service = self.notification_service
        self.app.state.alert_acknowledgement_service = self.ack_service
        self.app.include_router(notifications_router)

        self.client = TestClient(self.app)

        # 5. Shared IDs
        self.device_id = uuid4()
        self.operator_user_id = uuid4()

    def _create_sample_alert(
        self,
        alert_type: str = "TEMPERATURE_EXCEEDED",
        criticality: float = 8.0,
        message: str = "Temperature threshold breached: 8.5C (max 4.0C)",
    ) -> Alert:
        alert = Alert(
            id=uuid4(),
            device_id=self.device_id,
            user_id=self.operator_user_id,
            type=alert_type,
            message=message,
            criticality=criticality,
            acknowledged=False,
            created_at=datetime.now(timezone.utc),
        )
        self.app.state.alerts.append(alert)
        return alert

    # -----------------------------------------------------------------------
    # Test 1: Complete End-to-End Lifecycle Flow
    # -----------------------------------------------------------------------
    def test_complete_notification_lifecycle_flow(self):
        """Validates:
        Alert simulation -> NotificationService -> Manager routes to EMAIL ->
        Channel delivery -> Result recording (SENT) -> Query via API ->
        Alert acknowledgement via API -> State update verified.
        """
        # Step 1: Simulate Alert
        alert = self._create_sample_alert(
            alert_type="TEMPERATURE_EXCEEDED",
            criticality=8.5,
            message="Chamber 1 temperature critical: 9.0C",
        )
        self.assertFalse(alert.acknowledged)

        # Step 2: NotificationService processes the alert
        result = self.notification_service.process(alert)

        # Step 3: Verify notification generation and routing
        self.assertTrue(result.succeeded)
        self.assertIsNone(result.error)
        self.assertEqual(result.alert_id, alert.id)

        notification = result.notification
        self.assertIsNotNone(notification)
        self.assertEqual(notification.alert_id, alert.id)
        self.assertEqual(notification.channel, NotificationChannel.EMAIL)
        self.assertEqual(notification.status, NotificationStatus.SENT)
        self.assertIs(notification.alert, alert)

        # Step 4: Verify channel execution
        self.assertIsNotNone(result.send_result)
        self.assertEqual(result.send_result.status, NotificationStatus.SENT)
        self.assertEqual(len(self.email_deliveries), 1)
        self.assertEqual(self.email_deliveries[0]["recipient"], f"user-{alert.user_id}@coldchain.internal")
        self.assertEqual(self.email_deliveries[0]["message"], alert.message)

        # Register notification into state (as runtime pipeline does)
        self.app.state.notifications.append(notification)

        # Step 5: Query notifications via REST API
        resp = self.client.get("/notifications")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        notif_data = data["notifications"][0]
        self.assertEqual(notif_data["id"], str(notification.id))
        self.assertEqual(notif_data["alert_id"], str(alert.id))
        self.assertEqual(notif_data["channel"], "email")
        self.assertEqual(notif_data["status"], "sent")
        self.assertIn("alert", notif_data)
        self.assertEqual(notif_data["alert"]["id"], str(alert.id))
        self.assertFalse(notif_data["alert"]["acknowledged"])

        # Step 6: Query single notification by ID
        resp_single = self.client.get(f"/notifications/{notification.id}")
        self.assertEqual(resp_single.status_code, 200)
        self.assertEqual(resp_single.json()["id"], str(notification.id))

        # Step 7: Acknowledge the alert via REST API
        ack_resp = self.client.post(
            f"/notifications/alerts/{alert.id}/acknowledge",
            json={"user_id": str(self.operator_user_id)},
        )
        self.assertEqual(ack_resp.status_code, 200)
        ack_data = ack_resp.json()
        self.assertTrue(ack_data["acknowledged"])
        self.assertEqual(ack_data["alert_id"], str(alert.id))

        # Step 8: Verify state updates across alert and notification
        self.assertTrue(alert.acknowledged)
        self.assertTrue(notification.alert.acknowledged)

        # Verify status endpoint reflects acknowledgment
        status_resp = self.client.get(f"/notifications/alerts/{alert.id}/status")
        self.assertEqual(status_resp.status_code, 200)
        self.assertTrue(status_resp.json()["acknowledged"])
        self.assertEqual(len(status_resp.json()["notifications"]), 1)

    # -----------------------------------------------------------------------
    # Test 2: Dynamic Channel Routing for all Channel Types
    # -----------------------------------------------------------------------
    def test_multi_channel_routing_and_execution(self):
        """Validates that each alert type routes to its designated channel:
        - TEMPERATURE_EXCEEDED -> EMAIL
        - ENERGY_STATE_ANOMALY -> SMS
        - HUMIDITY_ABOVE_MAX   -> PUSH
        - UNKNOWN_ALERT        -> DASHBOARD (default)
        """
        cases = [
            ("TEMPERATURE_EXCEEDED", NotificationChannel.EMAIL, self.email_deliveries),
            ("ENERGY_STATE_ANOMALY", NotificationChannel.SMS, self.sms_deliveries),
            ("HUMIDITY_ABOVE_MAX", NotificationChannel.PUSH, self.push_deliveries),
            ("DOOR_LEFT_OPEN", NotificationChannel.DASHBOARD, self.dashboard_deliveries),
        ]

        for alert_type, expected_channel, delivery_list in cases:
            with self.subTest(alert_type=alert_type):
                alert = self._create_sample_alert(
                    alert_type=alert_type,
                    criticality=7.5,
                    message=f"Alert for {alert_type}",
                )

                result = self.notification_service.notify(alert)

                self.assertTrue(result.succeeded)
                self.assertEqual(result.notification.channel, expected_channel)
                self.assertEqual(result.notification.status, NotificationStatus.SENT)
                self.assertEqual(result.send_result.channel, expected_channel)
                self.assertEqual(len(delivery_list), 1)
                self.assertEqual(delivery_list[0]["notification_id"], result.notification.id)

                # Add to app state and verify via API filter
                self.app.state.notifications.append(result.notification)
                resp = self.client.get(f"/notifications?channel={expected_channel.value}")
                self.assertEqual(resp.status_code, 200)
                matching = [n for n in resp.json()["notifications"] if n["id"] == str(result.notification.id)]
                self.assertEqual(len(matching), 1)

    # -----------------------------------------------------------------------
    # Test 3: Failed Delivery Handling and Status Recovery Flow
    # -----------------------------------------------------------------------
    def test_failed_delivery_recording_and_manual_status_update(self):
        """Validates that channel transport failures are recorded as FAILED,
        traceability is preserved, and the API allows querying and updating status.
        """
        # Register a failing email channel
        failing_registry = NotificationChannelRegistry(
            channels=[FailingChannel(NotificationChannel.EMAIL)]
        )
        failing_service = NotificationService(
            manager=self.manager,
            channel_registry=failing_registry,
        )

        alert = self._create_sample_alert(
            alert_type="TEMPERATURE_EXCEEDED",
            message="Critical high temperature",
        )

        # Process with failing transport
        result = failing_service.process(alert)

        self.assertFalse(result.succeeded)
        self.assertIsNotNone(result.notification)
        self.assertEqual(result.notification.status, NotificationStatus.FAILED)
        self.assertIsNotNone(result.send_result)
        self.assertEqual(result.send_result.status, NotificationStatus.FAILED)
        self.assertIn("SMTP gateway unreachable", result.send_result.detail)

        # Traceability remains intact
        self.assertEqual(result.notification.alert_id, alert.id)
        self.assertIs(result.notification.alert, alert)

        # Add to state and query via API
        self.app.state.notifications.append(result.notification)

        resp_failed = self.client.get("/notifications?status=failed")
        self.assertEqual(resp_failed.status_code, 200)
        self.assertEqual(resp_failed.json()["count"], 1)
        self.assertEqual(resp_failed.json()["notifications"][0]["status"], "failed")

        # Status check endpoint
        resp_status = self.client.get(f"/notifications/{result.notification.id}/status")
        self.assertEqual(resp_status.status_code, 200)
        self.assertEqual(resp_status.json()["status"], "failed")

        # Operator retries or resolves issue manually and updates status to 'sent'
        patch_resp = self.client.patch(
            f"/notifications/{result.notification.id}/status",
            json={"status": "sent"},
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.json()["notification"]["status"], "sent")
        self.assertEqual(result.notification.status, NotificationStatus.SENT)

    # -----------------------------------------------------------------------
    # Test 4: End-to-End from Telemetry Readings to Notification Dispatch
    # -----------------------------------------------------------------------
    def test_full_pipeline_from_telemetry_to_notification(self):
        """Simulates the entire ColdChain pipeline:
        TelemetryNormalizer -> ClassificationService -> EventProcessingService ->
        NotificationService (via POST /notifications/process) -> Acknowledge Alert.
        """
        # 1. Telemetry input (abnormal temperature in cold room)
        telemetry_message = {
            "topic": "devices/CHAMBER-01/telemetry",
            "payload": {
                "temperature": 11.5,  # Exceeds max 4.0C
                "humidity": 88.0,
                "energy": "on",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "device_origin": {
                "device_code": "CHAMBER-01",
                "device_type": "cold_room",
            },
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

        # 2. Normalize telemetry
        normalizer = TelemetryNormalizer()
        readings = normalizer.normalize(telemetry_message)
        temp_reading = next(r for r in readings if r.sensor_name == "temperature")

        # 3. Classify reading
        risk_evaluator = RiskMatrixEvaluator()
        criteria = risk_evaluator.evaluate(temp_reading)
        classification = ClassificationService(
            calculator=CriticalityCalculator(),
            assigner=PriorityAssigner(),
        ).classify(
            reading=temp_reading,
            impact=criteria.impact,
            urgency=criteria.urgency,
            risk=criteria.risk,
        )
        self.assertEqual(classification.priority, "high")

        # 4. Event processing creates Alert
        threshold_config = ThresholdConfig(
            min_temperature=0.0,
            max_temperature=4.0,
            min_humidity=85.0,
            max_humidity=95.0,
            allowed_energy_states=frozenset({"on"}),
        )
        event_service = EventProcessingService(threshold_config=threshold_config)
        event_service.set_device_mapping({"CHAMBER-01": self.device_id})
        event_service.set_user_id(self.operator_user_id)

        process_result = event_service.process([temp_reading], classification)
        self.assertEqual(process_result["alert_count"], 1)
        generated_alert = process_result["alerts"][0]
        self.app.state.alerts.append(generated_alert)

        # 5. Dispatch notification via REST API endpoint (POST /notifications/process)
        api_dispatch_resp = self.client.post(
            "/notifications/process",
            json={
                "alert_id": str(generated_alert.id),
                "recipient": "ops-manager@coldchain.com",
                "message": f"CRITICAL: {generated_alert.message}",
            },
        )
        self.assertEqual(api_dispatch_resp.status_code, 201)
        dispatch_data = api_dispatch_resp.json()
        self.assertTrue(dispatch_data["success"])
        self.assertEqual(dispatch_data["alert_id"], str(generated_alert.id))
        self.assertEqual(dispatch_data["notification"]["channel"], "email")
        self.assertEqual(dispatch_data["notification"]["status"], "sent")

        # 6. Verify delivery recorded
        self.assertEqual(len(self.email_deliveries), 1)
        self.assertEqual(self.email_deliveries[0]["recipient"], "ops-manager@coldchain.com")

        # 7. Acknowledge via notification ID
        notif_id = dispatch_data["notification"]["id"]
        ack_resp = self.client.post(
            f"/notifications/{notif_id}/acknowledge",
            json={"user_id": str(self.operator_user_id)},
        )
        self.assertEqual(ack_resp.status_code, 200)
        self.assertTrue(generated_alert.acknowledged)
        self.assertTrue(ack_resp.json()["notification"]["alert"]["acknowledged"])

    # -----------------------------------------------------------------------
    # Test 5: Error Handling, Non-Existent Resources & Input Validation
    # -----------------------------------------------------------------------
    def test_error_handling_and_validation(self):
        """Verifies robust handling of invalid inputs, malformed UUIDs,
        non-existent resources, and rejection of invalid states.
        """
        # Non-existent alert acknowledgement -> 404
        missing_alert_id = uuid4()
        resp = self.client.post(f"/notifications/alerts/{missing_alert_id}/acknowledge")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())

        # Non-existent notification -> 404
        missing_notif_id = uuid4()
        resp = self.client.get(f"/notifications/{missing_notif_id}")
        self.assertEqual(resp.status_code, 404)

        # Malformed UUID in route -> 400
        resp = self.client.get("/notifications/invalid-uuid-format")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("must be a valid UUID", resp.json()["detail"])

        # Invalid notification status in update -> 400
        alert = self._create_sample_alert()
        notif = self.notification_service.process(alert).notification
        self.app.state.notifications.append(notif)

        resp = self.client.patch(
            f"/notifications/{notif.id}/status",
            json={"status": "invalid_lifecycle_state"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid status", resp.json()["detail"])

        # Invalid channel filter in listing -> 400
        resp = self.client.get("/notifications?channel=carrier_pigeon")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid channel", resp.json()["detail"])

        # Negative limit in listing -> 400
        resp = self.client.get("/notifications?limit=-10")
        self.assertEqual(resp.status_code, 400)

        # NotificationService rejects invalid alert input with TypeError
        with self.assertRaises(TypeError):
            self.notification_service.process("not-an-alert-object")

        # AlertAcknowledgementService rejects invalid inputs
        with self.assertRaises(TypeError):
            self.ack_service.acknowledge("invalid-alert")
        with self.assertRaises(TypeError):
            self.ack_service.acknowledge(alert, user_id="not-a-uuid-object")


if __name__ == "__main__":
    unittest.main()

