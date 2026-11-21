"""Allow alerts without a QoS criticality (WITHOUT_QOS).

Revision ID: a7c1e9d4b260
Revises: c5e7a9d1f203
Create Date: 2026-11-21

WITHOUT_QOS does not run the classification subsystem, so no C = I + U + R
score exists. Storing a fabricated 5 was misleading; NULL means "not
calculated" and must stay distinct from a measured value.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c1e9d4b260"
down_revision: Union[str, Sequence[str], None] = "c5e7a9d1f203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("alerts") as batch_op:
        batch_op.alter_column(
            "criticality",
            existing_type=sa.Float(),
            nullable=True,
        )


def downgrade() -> None:
    # Deliberately fails if unscored rows remain: a downgrade must not
    # silently invent 0/5 or delete valid alerts to satisfy NOT NULL.
    with op.batch_alter_table("alerts") as batch_op:
        batch_op.alter_column(
            "criticality",
            existing_type=sa.Float(),
            nullable=False,
        )
