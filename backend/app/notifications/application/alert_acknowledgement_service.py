from __future__ import annotations

from uuid import UUID

from app.events.domain import Alert


class AlertAcknowledgementService:
    """Updates acknowledgement state without containing notification logic."""

    def acknowledge(self, alert: Alert, user_id: UUID | None = None) -> Alert:
        if not isinstance(alert, Alert):
            raise TypeError("'alert' must be an Alert instance")
        if user_id is not None and not isinstance(user_id, UUID):
            raise TypeError("'user_id' must be a UUID instance")
        alert.acknowledged = True
        return alert


__all__ = ["AlertAcknowledgementService"]
