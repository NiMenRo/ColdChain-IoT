"""tsk0593_nullable_readings

TSK-059.3 — partial readings: NULL means the sensor is not enabled
for the device (DeviceSensor configuration), not a sensor failure.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a41c8e9d3202"
down_revision: Union[str, Sequence[str], None] = "f59b2c7d3101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "sensor_readings",
        "temperature",
        existing_type=sa.Float(),
        type_=sa.Float(),
        existing_nullable=False,
        nullable=True,
    )
    op.alter_column(
        "sensor_readings",
        "humidity",
        existing_type=sa.Float(),
        type_=sa.Float(),
        existing_nullable=False,
        nullable=True,
    )
    op.alter_column(
        "sensor_readings",
        "energy",
        existing_type=sa.String(),
        type_=sa.String(),
        existing_nullable=False,
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "sensor_readings",
        "energy",
        existing_type=sa.String(),
        type_=sa.String(),
        existing_nullable=True,
        nullable=False,
    )
    op.alter_column(
        "sensor_readings",
        "humidity",
        existing_type=sa.Float(),
        type_=sa.Float(),
        existing_nullable=True,
        nullable=False,
    )
    op.alter_column(
        "sensor_readings",
        "temperature",
        existing_type=sa.Float(),
        type_=sa.Float(),
        existing_nullable=True,
        nullable=False,
    )
