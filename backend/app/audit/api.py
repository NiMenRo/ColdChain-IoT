"""Read-only REST query API for the basic audit trail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.audit.schemas import AuditLogListResponse, AuditLogResponse
from app.audit.service import AuditService
from app.database.infrastructure.session import get_db
from app.security.dependencies import require_roles

router = APIRouter(prefix="/audit-logs", tags=["audit"])
_service = AuditService()
_require_audit_read = require_roles("admin", "auditor")


@router.get(
    "",
    response_model=AuditLogListResponse,
    summary="List audit records",
    description="Read-only audit trail. Available only to administrators and auditors.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Audit read permission required"}},
)
def list_audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current=Depends(_require_audit_read),
):
    total, entries = _service.list(db, page=page, per_page=per_page)
    return AuditLogListResponse(
        total=total,
        page=page,
        per_page=per_page,
        count=len(entries),
        results=[
            AuditLogResponse(
                id=str(entry.id),
                actor_user_id=str(entry.actor_user_id),
                action=entry.action,
                resource=entry.resource,
                outcome=entry.outcome,
                old_value=entry.old_value,
                new_value=entry.new_value,
                created_at=entry.created_at,
            )
            for entry in entries
        ],
    )
