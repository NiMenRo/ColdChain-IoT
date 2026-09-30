from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: str
    actor_user_id: str
    action: str
    resource: str
    outcome: str
    created_at: datetime


class AuditLogListResponse(BaseModel):
    total: int
    page: int
    per_page: int
    count: int
    results: list[AuditLogResponse]
