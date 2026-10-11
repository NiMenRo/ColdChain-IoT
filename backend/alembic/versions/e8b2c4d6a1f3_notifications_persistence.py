"""notifications_persistence

Persistent notification delivery records + user contact phone.

Fully additive: new ``notifications`` table and nullable ``users.phone``.
No backfill (no notification rows existed; notifications lived only in
``app.state``). Read state (``is_read``/``read_at``) defaults to unread
and is independent from ``alerts.acknowledged``. Downgrade drops the new
table/column.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8b2c4d6a1f3"
down_revision: Union[str, Sequence[str], None] = "d94e3f5a6605"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(), nullable=True))
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("alert_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recipient", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("notification_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "alert_id", "channel", "recipient",
            name="uq_notifications_alert_channel_recipient",
        ),
        sa.CheckConstraint(
            "channel IN ('email','sms','push','dashboard')",
            name="ck_notifications_channel",
        ),
        sa.CheckConstraint(
            "status IN ('pending','sent','failed','simulated','disabled')",
            name="ck_notifications_status",
        ),
    )
    op.create_index("ix_notifications_alert_id", "notifications", ["alert_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])


def downgrade() -> None:
    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_index("ix_notifications_alert_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_column("users", "phone")
