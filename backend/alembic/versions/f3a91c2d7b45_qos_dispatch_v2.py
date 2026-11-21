"""qos_dispatch_v2

Additive dispatch-v2 traceability. Existing rows remain processing version 1;
new per-sensor metadata and timestamps are nullable so no legacy data is
invented. The downgrade is intentionally omitted from operational guidance:
it would discard v2 traceability.
"""

from alembic import op
import sqlalchemy as sa

revision = "f3a91c2d7b45"
down_revision = "e8b2c4d6a1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sensor_readings", sa.Column("source_message_id", sa.UUID(), nullable=True))
    op.add_column("sensor_readings", sa.Column("sensor_name", sa.String(), nullable=True))
    op.add_column("sensor_readings", sa.Column("processing_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("ix_sensor_readings_source_message_id", "sensor_readings", ["source_message_id"])
    op.create_index("ix_sensor_readings_sensor_name", "sensor_readings", ["sensor_name"])
    with op.batch_alter_table("alerts") as batch:
        batch.add_column(sa.Column("reading_id", sa.UUID(), nullable=True))
        batch.create_foreign_key(
            "fk_alerts_reading_id_sensor_readings", "sensor_readings", ["reading_id"], ["id"]
        )
    op.create_index("ix_alerts_reading_id", "alerts", ["reading_id"])
    with op.batch_alter_table("qos_metrics") as batch:
        for column in ("latency", "packet_loss", "throughput", "pdr", "jitter"):
            batch.alter_column(column, existing_type=sa.Float(), nullable=True)
        batch.add_column(sa.Column("processing_version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("persisted_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("queue_wait_ms", sa.Float(), nullable=True))
        batch.add_column(sa.Column("service_time_ms", sa.Float(), nullable=True))
    with op.batch_alter_table("experiment_metrics") as batch:
        batch.drop_constraint("ck_experiment_metrics_type", type_="check")
        batch.create_check_constraint(
            "ck_experiment_metrics_type",
            "metric_type IN ('messages_received','messages_invalid','readings_persisted',"
            "'alerts_generated','backlog','ingest_to_persist_ms','ingest_to_alert_ms',"
            "'readings_admitted','readings_rejected','readings_failed','queue_wait_ms','service_time_ms')",
        )
