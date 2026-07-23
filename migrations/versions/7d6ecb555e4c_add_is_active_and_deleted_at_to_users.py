"""add_is_active_and_deleted_at_to_users

Revision ID: 7d6ecb555e4c
Revises: 2f7aa7f357e9
Create Date: 2026-07-23 14:14:49.372047

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d6ecb555e4c"
down_revision: Union[str, None] = "2f7aa7f357e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    op.add_column(
        "users", sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "is_active")
