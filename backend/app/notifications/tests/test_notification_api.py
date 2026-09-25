import unittest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.events.domain import Alert
from app.notifications.api import router
from app.notifications.application import (
    AlertAcknowledgementService,
    DashboardNotificationChannel,
    NotificationChannelRegistry,
    NotificationManager,
    NotificationService,
)
from app.notifications.domain import (
    Notification,
    NotificationChannel,
    NotificationStatus,
)


class NotificationAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.state.notifications = []
        self.app.state.alerts = []

        self.deliveries = []
        registry = NotificationChannelRegistry(
            channels=[DashboardNotificationChannel(deliveries=self.deliveries)]
        )
        self.manager = NotificationManager(default_channel=NotificationChannel.DASHBOARD)
        self.notification_service = NotificationService(
            manager=self.manager,
            channel_registry=registry,
        )
        self.ack_service = AlertAcknowledgementService()

        self.app.state.notification_service = self.notification_service
        self.app.state.alert_acknowledgement_service = self.ack_service

        self.app.include_router(router)
        # TSK-055: endpoints require auth; act as admin in legacy suites.
        self.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=uuid4(),
            email="admin@example.com",
            name="Admin",
            role="admin",
            is_active=True,
        )
        self.client = TestClient(self.app)

        self.user_id = uuid4()
        self.device_id = uuid4()
        self.alert = Alert(
            id=uuid4(),
            device_id=self.device_id,
            user_id=self.user_id,
            type="TEMPERATURE_EXCEEDED",
            message="Cold room temperature reached 9.5C",
            criticality=8.5,
            acknowledged=False,
            created_at=datetime.now(timezone.utc),
        )
        self.app.state.alerts.append(self.alert)

        self.notification = Notification.from_alert(
            alert=self.alert,
            channel=NotificationChannel.DASHBOARD,
            status=NotificationStatus.SENT,
        )
        self.app.state.notifications.append(self.notification)

    # -----------------------------------------------------------------------
    # History & Listing Tests
    # -----------------------------------------------------------------------

    def test_get_notifications_history_returns_list(self):
        response = self.client.get("/notifications")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["notifications"][0]["id"], str(self.notification.id))
        self.assertEqual(data["notifications"][0]["alert_id"], str(self.alert.id))
        self.assertEqual(data["notifications"][0]["channel"], "dashboard")
        self.assertEqual(data["notifications"][0]["status"], "sent")
        # Verify Alert-Notification traceability in response
        self.assertIn("alert", data["notifications"][0])
        self.assertEqual(data["notifications"][0]["alert"]["id"], str(self.alert.id))
        self.assertEqual(data["notifications"][0]["alert"]["type"], "TEMPERATURE_EXCEEDED")

    def test_get_notifications_alias_history_returns_same(self):
        response = self.client.get("/notifications/history")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)

    def test_get_notifications_filter_by_status(self):
        # Add another pending notification
        pending_notif = Notification.from_alert(
            alert=self.alert,
            channel=NotificationChannel.EMAIL,
            status=NotificationStatus.PENDING,
        )
        self.app.state.notifications.append(pending_notif)

        response = self.client.get("/notifications?status=sent")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["notifications"][0]["status"], "sent")

        response_pending = self.client.get("/notifications?status=pending")
        self.assertEqual(response_pending.status_code, 200)
        data_pending = response_pending.json()
        self.assertEqual(data_pending["count"], 1)
        self.assertEqual(data_pending["notifications"][0]["status"], "pending")

    def test_get_notifications_filter_by_channel(self):
        response = self.client.get("/notifications?channel=dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

        response_email = self.client.get("/notifications?channel=email")
        self.assertEqual(response_email.status_code, 200)
        self.assertEqual(response_email.json()["count"], 0)

    def test_get_notifications_filter_by_alert_id(self):
        response = self.client.get(f"/notifications?alert_id={self.alert.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

        other_uuid = uuid4()
        response_other = self.client.get(f"/notifications?alert_id={other_uuid}")
        self.assertEqual(response_other.status_code, 200)
        self.assertEqual(response_other.json()["count"], 0)

    def test_get_notifications_with_limit(self):
        # Add a second notification
        notif2 = Notification.from_alert(
            alert=self.alert,
            channel=NotificationChannel.PUSH,
            status=NotificationStatus.PENDING,
        )
        self.app.state.notifications.append(notif2)

        response = self.client.get("/notifications?limit=1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["notifications"][0]["id"], str(notif2.id))

    def test_invalid_limit_rejected(self):
        response = self.client.get("/notifications?limit=0")
        self.assertEqual(response.status_code, 400)
        self.assertIn("greater than zero", response.json()["detail"])

        response_neg = self.client.get("/notifications?limit=-5")
        self.assertEqual(response_neg.status_code, 400)

    def test_invalid_status_filter_rejected(self):
        response = self.client.get("/notifications?status=unknown_status")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid status", response.json()["detail"])

    def test_invalid_channel_filter_rejected(self):
        response = self.client.get("/notifications?channel=fax")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid channel", response.json()["detail"])

    # -----------------------------------------------------------------------
    # Single Notification Tests
    # -----------------------------------------------------------------------

    def test_get_notification_by_id_success(self):
        response = self.client.get(f"/notifications/{self.notification.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], str(self.notification.id))
        self.assertEqual(data["alert_id"], str(self.alert.id))
        self.assertEqual(data["channel"], "dashboard")
        self.assertEqual(data["status"], "sent")
        self.assertIn("alert", data)
        self.assertEqual(data["alert"]["id"], str(self.alert.id))

    def test_get_notification_by_id_not_found(self):
        random_id = uuid4()
        response = self.client.get(f"/notifications/{random_id}")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

    def test_get_notification_by_invalid_uuid(self):
        response = self.client.get("/notifications/not-a-valid-uuid")
        self.assertEqual(response.status_code, 400)
        self.assertIn("must be a valid UUID", response.json()["detail"])

    def test_get_notification_status(self):
        response = self.client.get(f"/notifications/{self.notification.id}/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], str(self.notification.id))
        self.assertEqual(data["status"], "sent")

    # -----------------------------------------------------------------------
    # Status Update Tests
    # -----------------------------------------------------------------------

    def test_update_notification_status_success(self):
        response = self.client.patch(
            f"/notifications/{self.notification.id}/status",
            json={"status": "failed"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["notification"]["status"], "failed")
        self.assertEqual(self.notification.status, NotificationStatus.FAILED)

    def test_update_notification_status_invalid_status(self):
        response = self.client.patch(
            f"/notifications/{self.notification.id}/status",
            json={"status": "invalid_status"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid status", response.json()["detail"])

    def test_update_notification_status_not_found(self):
        response = self.client.patch(
            f"/notifications/{uuid4()}/status",
            json={"status": "failed"},
        )
        self.assertEqual(response.status_code, 404)

    # -----------------------------------------------------------------------
    # Alert Acknowledgement Tests
    # -----------------------------------------------------------------------

    def test_acknowledge_alert_by_alert_id(self):
        self.assertFalse(self.alert.acknowledged)

        operator_user_id = uuid4()
        response = self.client.post(
            f"/notifications/alerts/{self.alert.id}/acknowledge",
            json={"user_id": str(operator_user_id)},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["acknowledged"])
        self.assertEqual(data["alert_id"], str(self.alert.id))
        self.assertTrue(self.alert.acknowledged)

        # Traceability check: notification pointing to alert reflects acknowledged state
        self.assertTrue(self.notification.alert.acknowledged)

    def test_acknowledge_alert_alias_endpoints(self):
        # Reset alert state
        self.alert.acknowledged = False

        # Alias: /notifications/alerts/{id}/ack
        response = self.client.post(f"/notifications/alerts/{self.alert.id}/ack")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.alert.acknowledged)

        # Reset again
        self.alert.acknowledged = False

        # Alias: /notifications/acknowledge (body with alert_id)
        response = self.client.post(
            "/notifications/acknowledge",
            json={"alert_id": str(self.alert.id)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.alert.acknowledged)

    def test_acknowledge_alert_via_notification_id(self):
        self.alert.acknowledged = False
        response = self.client.post(f"/notifications/{self.notification.id}/acknowledge")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["acknowledged"])
        self.assertTrue(self.alert.acknowledged)
        self.assertIn("notification", data)

    def test_acknowledge_alert_not_found(self):
        response = self.client.post(f"/notifications/alerts/{uuid4()}/acknowledge")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

    def test_acknowledge_alert_invalid_uuid(self):
        response = self.client.post("/notifications/alerts/invalid-uuid/acknowledge")
        self.assertEqual(response.status_code, 400)

    def test_get_alert_status_endpoint(self):
        response = self.client.get(f"/notifications/alerts/{self.alert.id}/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["alert_id"], str(self.alert.id))
        self.assertFalse(data["acknowledged"])
        self.assertEqual(len(data["notifications"]), 1)
        self.assertEqual(data["notifications"][0]["id"], str(self.notification.id))

    # -----------------------------------------------------------------------
    # Notification Processing Tests
    # -----------------------------------------------------------------------

    def test_process_notification_for_existing_alert(self):
        # Create a new alert
        new_alert = Alert(
            id=uuid4(),
            device_id=self.device_id,
            user_id=self.user_id,
            type="HUMIDITY_ABOVE_MAX",
            message="Humidity exceeded 80%",
            criticality=7.0,
            acknowledged=False,
            created_at=datetime.now(timezone.utc),
        )
        self.app.state.alerts.append(new_alert)

        response = self.client.post(
            "/notifications/process",
            json={
                "alert_id": str(new_alert.id),
                "recipient": "operator-dashboard",
                "message": "Custom alert dispatch",
            },
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["alert_id"], str(new_alert.id))
        self.assertIsNotNone(data["notification"])
        self.assertEqual(data["notification"]["status"], "sent")
        self.assertEqual(data["send_result"]["channel"], "dashboard")

        # Verify added to history
        self.assertIn(
            UUID(data["notification"]["id"]),
            [n.id for n in self.app.state.notifications],
        )

    def test_process_notification_not_found_alert_id(self):
        response = self.client.post(
            "/notifications/process",
            json={"alert_id": str(uuid4())},
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

    def test_process_notification_empty_body_rejected(self):
        response = self.client.post("/notifications/process", json={})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()

