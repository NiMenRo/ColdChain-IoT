"""tsk054_user_is_active

Add explicit activity state to users for TSK-054 authentication.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9e2b7c4a1f30"
down_revision: Union[str, Sequence[str], None] = "4a6f3d8e2b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
