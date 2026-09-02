"""REST API endpoints for events and alerts."""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
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


class EnrichedEventResponse(BaseModel):
    """Enriched event with full contextual information."""

    alert_id: str
    alert_type: str
    alert_message: str
    alert_criticality: float
    alert_acknowledged: bool
    alert_created_at: str
    device_id: str
    device_code: str
    device_type: str
    device_location: Optional[str]
    classification_id: str
    reading_id: str
    traffic_priority: str
    traffic_queue: str
    classification_time: str
    sensor_timestamp: str
    enrichment_timestamp: str
    qos_latency: float
    qos_jitter: float
    qos_throughput: float
    qos_pdr: float
    qos_packet_loss: float
    user_id: str


class EventProcessingResponse(BaseModel):
    """Full response from event processing."""

    event_count: int
    alert_count: int
    events: list[DetectedEventResponse]
    alerts: list[AlertResponse]
    classification_id: str
    processed_at: str


def _validated_limit(limit: Optional[int]) -> Optional[int]:
    """Validate a query limit and return a normalized positive integer."""
    if limit is None:
        return None
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'limit' must be a positive integer.",
        )
    if limit <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'limit' must be greater than zero.",
        )
    return limit


def _serialize_alert(alert: Any) -> dict[str, Any]:
    return {
        "id": str(alert.id),
        "device_id": str(alert.device_id),
        "user_id": str(alert.user_id),
        "type": alert.type,
        "message": alert.message,
        "criticality": alert.criticality,
        "acknowledged": alert.acknowledged,
        "created_at": alert.created_at.isoformat(timespec="seconds"),
    }


def _serialize_event(event: Any) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "device_code": event.device_code,
        "variable": event.variable,
        "event_type": event.event_type,
        "message": event.message,
        "observed_value": event.observed_value,
        "threshold": event.threshold,
        "detected_at": event.detected_at.isoformat(timespec="seconds"),
    }


def _serialize_enriched_event(enriched: Any) -> dict[str, Any]:
    return {
        "alert_id": str(enriched.alert_id),
        "alert_type": enriched.alert_type,
        "alert_message": enriched.alert_message,
        "alert_criticality": enriched.alert_criticality,
        "alert_acknowledged": enriched.alert_acknowledged,
        "alert_created_at": enriched.alert_created_at.isoformat(timespec="seconds"),
        "device_id": str(enriched.device_id),
        "device_code": enriched.device_code,
        "device_type": enriched.device_type,
        "device_location": enriched.device_location,
        "classification_id": str(enriched.classification_id),
        "reading_id": str(enriched.reading_id),
        "traffic_priority": enriched.traffic_priority,
        "traffic_queue": enriched.traffic_queue,
        "classification_time": enriched.classification_time.isoformat(timespec="seconds"),
        "sensor_timestamp": enriched.sensor_timestamp.isoformat(timespec="seconds"),
        "enrichment_timestamp": enriched.enrichment_timestamp.isoformat(timespec="seconds"),
        "qos_latency": enriched.qos_latency,
        "qos_jitter": enriched.qos_jitter,
        "qos_throughput": enriched.qos_throughput,
        "qos_pdr": enriched.qos_pdr,
        "qos_packet_loss": enriched.qos_packet_loss,
        "user_id": str(enriched.user_id),
    }


@router.get("/alerts")
def get_alerts(request: Request, limit: Optional[int] = None):
    """Get all alerts generated during the session."""
    try:
        normalized_limit = _validated_limit(limit)
    except HTTPException:
        raise

    alerts_list = list(getattr(request.app.state, "alerts", []))
    if normalized_limit is not None:
        alerts_list = alerts_list[-normalized_limit:]

    return {"count": len(alerts_list), "alerts": [_serialize_alert(alert) for alert in alerts_list]}


@router.get("/alerts/critical")
def get_critical_alerts(request: Request, limit: Optional[int] = None):
    """Get only high-criticality alerts (criticality >= 7)."""
    try:
        normalized_limit = _validated_limit(limit)
    except HTTPException:
        raise

    alerts_list = [alert for alert in getattr(request.app.state, "alerts", []) if alert.criticality >= 7.0]
    if normalized_limit is not None:
        alerts_list = alerts_list[-normalized_limit:]

    return {"count": len(alerts_list), "alerts": [_serialize_alert(alert) for alert in alerts_list]}


@router.get("/alerts/{alert_id}")
def get_alert_by_id(request: Request, alert_id: str):
    """Return a single alert by its identifier."""
    try:
        UUID(alert_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="alert_id must be a valid UUID.") from exc

    alerts_list = list(getattr(request.app.state, "alerts", []))
    for alert in alerts_list:
        if str(alert.id) == alert_id:
            return {"alert": _serialize_alert(alert)}

    raise HTTPException(status_code=404, detail="Alert not found.")


@router.get("/events")
def get_events(request: Request, limit: Optional[int] = None):
    """Get all detected events for the current session."""
    try:
        normalized_limit = _validated_limit(limit)
    except HTTPException:
        raise

    events_list = list(getattr(request.app.state, "events", []))
    if normalized_limit is not None:
        events_list = events_list[-normalized_limit:]

    return {"count": len(events_list), "events": [_serialize_event(event) for event in events_list]}


@router.get("/events/{event_id}")
def get_event_by_id(request: Request, event_id: str):
    """Return a single detected event by its identifier."""
    try:
        UUID(event_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="event_id must be a valid UUID.") from exc

    events_list = list(getattr(request.app.state, "events", []))
    for event in events_list:
        if str(event.id) == event_id:
            return {"event": _serialize_event(event)}

    raise HTTPException(status_code=404, detail="Event not found.")


@router.get("/summary")
def get_event_summary(request: Request):
    """Get summary statistics of events and alerts."""
    alerts_list = list(getattr(request.app.state, "alerts", []))
    events_list = list(getattr(request.app.state, "events", []))

    alert_types: dict[str, int] = {}
    for alert in alerts_list:
        alert_types[alert.type] = alert_types.get(alert.type, 0) + 1

    event_types: dict[str, int] = {}
    for event in events_list:
        event_types[event.event_type] = event_types.get(event.event_type, 0) + 1

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


@router.get("/health")
def health_check():
    """Health check endpoint for the events subsystem."""
    return {"status": "ok", "subsystem": "events"}


@router.get("/enriched")
def get_enriched_events(request: Request, limit: Optional[int] = None):
    """Get all enriched events with full contextual information."""
    try:
        normalized_limit = _validated_limit(limit)
    except HTTPException:
        raise

    enriched_events_list = list(getattr(request.app.state, "enriched_events", []))
    if normalized_limit is not None:
        enriched_events_list = enriched_events_list[-normalized_limit:]

    return {
        "count": len(enriched_events_list),
        "enriched_events": [_serialize_enriched_event(enriched) for enriched in enriched_events_list],
    }


@router.get("/enriched/{alert_id}")
def get_enriched_event_by_alert_id(request: Request, alert_id: str):
    """Return the enriched event associated with a specific alert id."""
    try:
        UUID(alert_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="alert_id must be a valid UUID.") from exc

    enriched_events_list = list(getattr(request.app.state, "enriched_events", []))
    for enriched in enriched_events_list:
        if str(enriched.alert_id) == alert_id:
            return {"enriched_event": _serialize_enriched_event(enriched)}

    raise HTTPException(status_code=404, detail="Enriched event not found.")
