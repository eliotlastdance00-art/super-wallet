"""add_email_verified_to_users

Revision ID: 0c8b4bad93cb
Revises: 3f90933d8b8e
Create Date: 2026-07-16 16:20:41.942209

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0c8b4bad93cb"
down_revision: Union[str, None] = "3f90933d8b8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQL-yňyzy göni şu taýda işlediň:
    op.execute(
        "ALTER TABLE users ADD COLUMN email_verified boolean NOT NULL DEFAULT false;"
    )


def downgrade() -> None:
    # Yza gaýtarmak (rollback) zerur bolsa, sütüni aýyrmak üçin:
    op.execute("ALTER TABLE users DROP COLUMN email_verified;")
