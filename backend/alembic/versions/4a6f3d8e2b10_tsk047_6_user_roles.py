"""tsk047_6_user_roles

Add the supported human roles while preserving the technical system identity.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4a6f3d8e2b10"
down_revision: Union[str, Sequence[str], None] = "17003a138539"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    invalid_roles = list(
        bind.execute(
            sa.text(
                "SELECT role, COUNT(*) AS count FROM users "
                "WHERE role NOT IN ('admin','supervisor','operador','auditor','system') "
                "GROUP BY role"
            )
        ).fetchall()
    )
    if invalid_roles:
        raise RuntimeError(
            "TSK-047.6 aborted: unsupported user roles exist. "
            "Update them manually before applying this migration: "
            f"{invalid_roles}"
        )

    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin','supervisor','operador','auditor','system')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
