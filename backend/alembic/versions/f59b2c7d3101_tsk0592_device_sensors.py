"""tsk0592_device_sensors

TSK-059.2 — persistent per-device sensor configuration (Device -> DeviceSensor).
SensorReading stays aggregated; TSK-059.3 adapts partial readings.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f59b2c7d3101"
down_revision: Union[str, Sequence[str], None] = "bb9f592aa101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "device_sensors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("sensor_type", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "sensor_type", name="uq_device_sensors_device_sensor"),
        sa.CheckConstraint(
            "sensor_type IN ('temperature','humidity','energy')",
            name="ck_device_sensors_type",
        ),
    )


def downgrade() -> None:
    op.drop_table("device_sensors")
