"""create users table

Revision ID: 72f842f79d39
Revises: 
Create Date: 2026-07-10 18:03:23.092597

"""
from typing import Sequence, Union

from alembic import op



# revision identifiers, used by Alembic.
revision: str = '72f842f79d39'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS "pgcrypto";""")
    op.execute("""
            CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username VARCHAR(50) NOT NULL UNIQUE,
            email VARCHAR(100) NOT NULL UNIQUE,
            hashed_password VARCHAR(255) NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now());   """)
    op.execute("""
        CREATE INDEX idx_users_email ON users(email);               
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS users;")
