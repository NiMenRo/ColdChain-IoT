"""Admin-only threshold configuration API (TSK-059.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.infrastructure.repositories import SystemConfigRepository
from app.database.infrastructure.session import get_db
from app.security.dependencies import require_admin
from app.system_config.schemas import SystemConfigResponse, SystemConfigUpdate

router = APIRouter(prefix="/system-config", tags=["system-config"])
_repository = SystemConfigRepository()


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
    try:
        updated = _repository.update(db, config, **fields)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    return _to_response(updated)
