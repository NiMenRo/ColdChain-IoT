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


@router.get("/enriched")
def get_enriched_events(request: Request, limit: Optional[int] = None):
    """Get all enriched events with full contextual information.
    
    An enriched event combines:
    - The alert that was generated
    - Device information (code, type, location)
    - Traffic classification (priority, queue, criticality)
    - QoS metrics (latency, jitter, throughput, PDR, packet loss)
    - Complete timestamp chain for traceability
    
    Query Parameters:
    - limit: Maximum number of recent enriched events to return (optional)
    """
    enriched_events_list = getattr(request.app.state, "enriched_events", [])
    
    # If limit is specified, return the last N events
    if limit is not None and limit > 0:
        enriched_events_list = enriched_events_list[-limit:]
    
    result = []
    for enriched in enriched_events_list:
        result.append({
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
        })
    
    return {
        "count": len(result),
        "enriched_events": result,
    }
