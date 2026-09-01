"""REST API endpoints for events and alerts."""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field, validator

router = APIRouter(prefix="/events", tags=["events"])

__all__ = ["router"]


class AlertResponse(BaseModel):
    """Alert object serialized for REST response."""
    id: str
    device_id: str
    user_id: str
    type: str
    message: str
    criticality: float
    acknowledged: bool
    created_at: str


class DetectedEventResponse(BaseModel):
    """Detected event object serialized for REST response."""
    id: str
    device_code: str
    variable: str
    event_type: str
    message: str
    observed_value: float | str
    detected_at: str


class EventProcessingResponse(BaseModel):
    """Full response from event processing."""
    event_count: int
    alert_count: int
    events: list[DetectedEventResponse]
    alerts: list[AlertResponse]
    classification_id: str
    processed_at: str


@router.get("/alerts")
def get_alerts(request: Request, limit: Optional[int] = None):
    """Get all alerts generated during the session.
    
    Query Parameters:
    - limit: Maximum number of recent alerts to return (optional)
    """
    alerts_list = getattr(request.app.state, "alerts", [])
    
    # If limit is specified, return the last N alerts
    if limit is not None and limit > 0:
        alerts_list = alerts_list[-limit:]
    
    result = []
    for alert in alerts_list:
        result.append({
            "id": str(alert.id),
            "device_id": str(alert.device_id),
            "user_id": str(alert.user_id),
            "type": alert.type,
            "message": alert.message,
            "criticality": alert.criticality,
            "acknowledged": alert.acknowledged,
            "created_at": alert.created_at.isoformat(timespec="seconds"),
        })
    
    return {
        "count": len(result),
        "alerts": result,
    }


@router.get("/events")
def get_events(request: Request, limit: Optional[int] = None):
    """Get all events detected during the session.
    
    Query Parameters:
    - limit: Maximum number of recent events to return (optional)
    """
    events_list = getattr(request.app.state, "events", [])
    
    # If limit is specified, return the last N events
    if limit is not None and limit > 0:
        events_list = events_list[-limit:]
    
    result = []
    for event in events_list:
        result.append({
            "id": str(event.id),
            "device_code": event.device_code,
            "variable": event.variable,
            "event_type": event.event_type,
            "message": event.message,
            "observed_value": event.observed_value,
            "threshold": event.threshold,
            "detected_at": event.detected_at.isoformat(timespec="seconds"),
        })
    
    return {
        "count": len(result),
        "events": result,
    }


@router.get("/summary")
def get_event_summary(request: Request):
    """Get summary statistics of events and alerts."""
    alerts_list = getattr(request.app.state, "alerts", [])
    events_list = getattr(request.app.state, "events", [])
    
    # Count alerts by type
    alert_types = {}
    for alert in alerts_list:
        alert_types[alert.type] = alert_types.get(alert.type, 0) + 1
    
    # Count events by type
    event_types = {}
    for event in events_list:
        event_types[event.event_type] = event_types.get(event.event_type, 0) + 1
    
    # Count acknowledged vs unacknowledged alerts
    acknowledged_count = sum(1 for alert in alerts_list if alert.acknowledged)
    unacknowledged_count = len(alerts_list) - acknowledged_count
    
    return {
        "total_alerts": len(alerts_list),
        "total_events": len(events_list),
        "acknowledged_alerts": acknowledged_count,
        "unacknowledged_alerts": unacknowledged_count,
        "alert_types": alert_types,
        "event_types": event_types,
    }


@router.get("/alerts/critical")
def get_critical_alerts(request: Request):
    """Get only high-criticality alerts (criticality >= 7)."""
    alerts_list = getattr(request.app.state, "alerts", [])
    critical_alerts = [alert for alert in alerts_list if alert.criticality >= 7.0]
    
    result = []
    for alert in critical_alerts:
        result.append({
            "id": str(alert.id),
            "device_id": str(alert.device_id),
            "user_id": str(alert.user_id),
            "type": alert.type,
            "message": alert.message,
            "criticality": alert.criticality,
            "acknowledged": alert.acknowledged,
            "created_at": alert.created_at.isoformat(timespec="seconds"),
        })
    
    return {
        "count": len(result),
        "alerts": result,
    }


@router.get("/health")
def health_check():
    """Health check endpoint for the events subsystem."""
    return {"status": "ok", "subsystem": "events"}
