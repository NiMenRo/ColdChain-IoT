"""tsk0595_audit_old_new

TSK-059.5 — old/new values for critical-action audit trail.
No backfill: NULL means "no values recorded".
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c83e2a5d5504"
down_revision: Union[str, Sequence[str], None] = "b72d1f4c4403"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("old_value", sa.Text(), nullable=True))
    op.add_column("audit_logs", sa.Column("new_value", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_logs", "new_value")
    op.drop_column("audit_logs", "old_value")
