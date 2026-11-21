"""Allow the per-experiment transport rejection counter.

Revision ID: b4d6e8a2c901
Revises: f3a91c2d7b45
"""
from alembic import op

revision = "b4d6e8a2c901"
down_revision = "f3a91c2d7b45"
branch_labels = None
depends_on = None

_BASE = (
    "'messages_received','messages_invalid','readings_persisted',"
    "'alerts_generated','backlog','ingest_to_persist_ms','ingest_to_alert_ms',"
    "'readings_admitted','readings_rejected','readings_failed',"
    "'queue_wait_ms','service_time_ms'"
)


def upgrade() -> None:
    with op.batch_alter_table("experiment_metrics") as batch:
        batch.drop_constraint("ck_experiment_metrics_type", type_="check")
        batch.create_check_constraint(
            "ck_experiment_metrics_type",
            f"metric_type IN ({_BASE},'messages_rejected_transport')",
        )


def downgrade() -> None:
    raise RuntimeError("Downgrade could discard or invalidate transport rejection metrics")
