"""add auth session tables

Revision ID: 3f90933d8b8e
Revises: 78e1d7555d97
Create Date: 2026-07-14 19:02:22.809502

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f90933d8b8e"
down_revision: Union[str, None] = "78e1d7555d97"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE sessions (
    id UUID PRIMARY KEY,

    user_id UUID NOT NULL REFERENCES users(id),

    refresh_token_hash TEXT NOT NULL,

    device_info TEXT,
    ip_address INET,

    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,

    revoked_at TIMESTAMPTZ,
    revoked_reason TEXT,

    replaced_by_session_id UUID REFERENCES sessions(id)
);
""")
    op.execute("""
        CREATE UNIQUE INDEX ix_sessions_refresh_token_hash
ON sessions(refresh_token_hash);            
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sessions;")
