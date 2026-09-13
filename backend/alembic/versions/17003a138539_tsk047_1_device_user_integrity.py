"""tsk047_1_device_user_integrity

Revision ID: 17003a138539
Revises: 7b7ca6d02489
Create Date: 2026-09-13

TSK-047.1 — Device/User integrity fix:
- Device.code UNIQUE (uq_devices_code)
- User.email UNIQUE (uq_users_email) with lower/strip normalization in ORM
- Device.status CHECK active/inactive/maintenance/error
- Device.device_type CHECK cold_room/refrigerated_showcase
Before applying, detect duplicates and abort without silent dedup.
Reversible: upgrade -> downgrade -> upgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '17003a138539'
down_revision: Union[str, Sequence[str], None] = '7b7ca6d02489'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from alembic import context as alembic_context

    # — Duplicate detection (no auto-dedup) — online mode only
    if not alembic_context.is_offline_mode():
        bind = op.get_bind()
        if bind is not None:
            dup_devices = list(
                bind.execute(
                    sa.text("SELECT code, COUNT(*) as cnt FROM devices GROUP BY code HAVING COUNT(*) > 1")
                ).fetchall()
            )
            dup_users = list(
                bind.execute(
                    sa.text("SELECT email, COUNT(*) as cnt FROM users GROUP BY email HAVING COUNT(*) > 1")
                ).fetchall()
            )
            if dup_devices or dup_users:
                raise RuntimeError(
                    f"TSK-047.1 aborted: duplicates detected — devices={dup_devices} users={dup_users}. "
                    "Please fix manually before retrying."
                )

    # — Constraints (UNIQUE already creates btree index in PG, do not create extra index) —
    op.create_unique_constraint("uq_devices_code", "devices", ["code"])
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_check_constraint(
        "ck_devices_status",
        "devices",
        "status IN ('active','inactive','maintenance','error')",
    )
    op.create_check_constraint(
        "ck_devices_device_type",
        "devices",
        "device_type IN ('cold_room','refrigerated_showcase')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_devices_device_type", "devices", type_="check")
    op.drop_constraint("ck_devices_status", "devices", type_="check")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_constraint("uq_devices_code", "devices", type_="unique")
