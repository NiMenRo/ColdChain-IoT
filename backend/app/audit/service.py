"""Application service for recording successful auditable operations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.database.infrastructure.models import AuditLogORM
from app.database.infrastructure.repositories import AuditLogRepository


class AuditService:
    def __init__(self, repository: AuditLogRepository | None = None) -> None:
        self._repository = repository or AuditLogRepository()

    def record(
        self,
        db: Session,
        *,
        actor_user_id: UUID,
        action: str,
        resource: str,
        outcome: str = "success",
        old_value: str | dict | None = None,
        new_value: str | dict | None = None,
    ) -> AuditLogORM:
        """Stage an entry in the caller's transaction; does not commit."""
        return self._repository.create(
            db,
            actor_user_id=actor_user_id,
            action=action,
            resource=resource,
            outcome=outcome,
            old_value=old_value,
            new_value=new_value,
        )

    def list(self, db: Session, *, page: int, per_page: int):
        return self._repository.list(db, page=page, per_page=per_page)
