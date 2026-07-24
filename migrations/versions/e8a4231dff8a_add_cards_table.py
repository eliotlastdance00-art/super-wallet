"""add_cards_table

Revision ID: e8a4231dff8a
Revises: 80aa87a13169
Create Date: 2026-07-24 17:44:10.756913

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8a4231dff8a'
down_revision: Union[str, None] = '80aa87a13169'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
