"""Admin-only threshold configuration API (TSK-059.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.database.infrastructure.repositories import SystemConfigRepository
from app.database.infrastructure.session import get_db
from app.security.dependencies import require_admin
from app.system_config.schemas import SystemConfigResponse, SystemConfigUpdate

router = APIRouter(prefix="/system-config", tags=["system-config"])
_repository = SystemConfigRepository()
_audit = AuditService()

_MANAGED_FIELDS = ("min_temperature", "max_temperature", "min_humidity", "max_humidity")


def _to_response(config) -> SystemConfigResponse:
    return SystemConfigResponse(
        id=str(config.id),
        min_temperature=config.min_temperature,
        max_temperature=config.max_temperature,
        min_humidity=config.min_humidity,
        max_humidity=config.max_humidity,
    )


@router.put(
    "",
    response_model=SystemConfigResponse,
    summary="Update system thresholds",
    description="Admin-only update of cold-chain thresholds. qos_* fields are read-only.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Admin permission required"},
        404: {"description": "System configuration not seeded"},
    },
)
def update_system_config(
    body: SystemConfigUpdate,
    db: Session = Depends(get_db),
    _current=Depends(require_admin),
):
    config = _repository.get_current(db)
    if config is None:
        raise HTTPException(404, "System configuration not seeded")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "At least one threshold field must be provided")
    # TSK-059.5 — snapshot administrable fields before mutating.
    old_values = {k: getattr(config, k) for k in _MANAGED_FIELDS}
    try:
        updated = _repository.update(db, config, **fields)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    new_values = {k: getattr(updated, k) for k in _MANAGED_FIELDS}
    _audit.record(
        db,
        actor_user_id=_current.id,
        action="system_config.update",
        resource=f"system_configs/{updated.id}",
        old_value=old_values,
        new_value=new_values,
    )
    db.commit()
    return _to_response(updated)
