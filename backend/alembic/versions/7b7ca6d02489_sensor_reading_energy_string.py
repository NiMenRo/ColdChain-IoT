"""sensor_reading_energy_string

Revision ID: 7b7ca6d02489
Revises: cff6c25b6661
Create Date: 2026-09-02 11:42:17.537846

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b7ca6d02489'
down_revision: Union[str, Sequence[str], None] = 'cff6c25b6661'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema, using batch mode for SQLite compatibility."""
    with op.batch_alter_table("sensor_readings") as batch_op:
        batch_op.alter_column(
            "energy",
            existing_type=sa.Boolean(),
            type_=sa.String(),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema, using batch mode for SQLite compatibility."""
    with op.batch_alter_table("sensor_readings") as batch_op:
        batch_op.alter_column(
            "energy",
            existing_type=sa.String(),
            type_=sa.Boolean(),
            existing_nullable=False,
        )
