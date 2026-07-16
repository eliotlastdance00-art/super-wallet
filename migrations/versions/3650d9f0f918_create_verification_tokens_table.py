"""create_verification_tokens_table

Revision ID: 3650d9f0f918
Revises: 0c8b4bad93cb
Create Date: 2026-07-16 16:28:04.455397

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3650d9f0f918"
down_revision: Union[str, None] = "0c8b4bad93cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tablisany döretmek üçin Raw SQL
    op.execute("""
        CREATE TABLE verification_tokens (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash text NOT NULL UNIQUE,
            type text NOT NULL, -- 'email_verify' | 'password_reset'
            ip_address inet,
            expires_at timestamptz NOT NULL,
            used_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        );
    """)


def downgrade() -> None:
    # Tablisany öçürmek (yza gaýtarmak) üçin Raw SQL
    op.execute("DROP TABLE IF EXISTS verification_tokens;")
