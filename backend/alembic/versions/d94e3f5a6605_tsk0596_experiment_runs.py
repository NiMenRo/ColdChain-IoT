"""tsk0596_experiment_runs

TSK-059.6 — experiment runs and comparable common metrics.
Fully additive: no backfill, legacy rows keep run_id NULL.
Downgrade drops the new tables/columns (experimental data is lost).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d94e3f5a6605"
down_revision: Union[str, Sequence[str], None] = "c83e2a5d5504"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "experiment_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scenario", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_snapshot", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "scenario IN ('WITH_QOS','WITHOUT_QOS')",
            name="ck_experiment_runs_scenario",
        ),
    )
    op.create_index("ix_experiment_runs_scenario", "experiment_runs", ["scenario"])
    op.create_table(
        "experiment_metrics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("metric_type", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["experiment_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "metric_type IN ('messages_received','messages_invalid','readings_persisted',"
            "'alerts_generated','backlog','ingest_to_persist_ms','ingest_to_alert_ms')",
            name="ck_experiment_metrics_type",
        ),
    )
    op.create_index("ix_experiment_metrics_run_id", "experiment_metrics", ["run_id"])
    op.create_index("ix_experiment_metrics_timestamp", "experiment_metrics", ["timestamp"])
    op.add_column("sensor_readings", sa.Column("run_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_sensor_readings_run_id", "sensor_readings", "experiment_runs", ["run_id"], ["id"])
    op.create_index("ix_sensor_readings_run_id", "sensor_readings", ["run_id"])
    op.add_column("alerts", sa.Column("run_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_alerts_run_id", "alerts", "experiment_runs", ["run_id"], ["id"])
    op.create_index("ix_alerts_run_id", "alerts", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_alerts_run_id", table_name="alerts")
    op.drop_constraint("fk_alerts_run_id", "alerts", type_="foreignkey")
    op.drop_column("alerts", "run_id")
    op.drop_index("ix_sensor_readings_run_id", table_name="sensor_readings")
    op.drop_constraint("fk_sensor_readings_run_id", "sensor_readings", type_="foreignkey")
    op.drop_column("sensor_readings", "run_id")
    op.drop_index("ix_experiment_metrics_timestamp", table_name="experiment_metrics")
    op.drop_index("ix_experiment_metrics_run_id", table_name="experiment_metrics")
    op.drop_table("experiment_metrics")
    op.drop_index("ix_experiment_runs_scenario", table_name="experiment_runs")
    op.drop_table("experiment_runs")
