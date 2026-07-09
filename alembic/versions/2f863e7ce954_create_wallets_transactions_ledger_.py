"""create wallets, transactions, ledger_entries

Revision ID: 2f863e7ce954
Revises: 
Create Date: 2026-07-09 11:45:48.728604

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f863e7ce954'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
