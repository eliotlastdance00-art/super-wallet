"""set_verification_tokens_id_default

Revision ID: 2f7aa7f357e9
Revises: e9f2c9cad5d9
Create Date: 2026-07-18 13:54:14.519507

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2f7aa7f357e9"
down_revision: Union[str, None] = "e9f2c9cad5d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # id sütununa default UUID atama SQL'i
    op.execute(
        """
        ALTER TABLE verification_tokens 
        ALTER COLUMN id SET DEFAULT gen_random_uuid();
        """
    )


def downgrade() -> None:
    # Geri alma (rollback) senaryosu: Default değeri kaldırır
    op.execute(
        """
        ALTER TABLE verification_tokens 
        ALTER COLUMN id DROP DEFAULT;
        """
    )
