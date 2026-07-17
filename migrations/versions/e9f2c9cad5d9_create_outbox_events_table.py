"""create_outbox_events_table

Revision ID: e9f2c9cad5d9
Revises: 3650d9f0f918
Create Date: 2026-07-17 15:00:25.336918

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9f2c9cad5d9"
down_revision: Union[str, None] = "3650d9f0f918"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Outbox tablisasyny doretmek
    op.execute("""
        CREATE TABLE outbox_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            event_type text NOT NULL,
            payload jsonb NOT NULL,
            status text NOT NULL DEFAULT 'pending',
            attempts int NOT NULL DEFAULT 0,
            last_error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            processed_at timestamptz
        );
    """)

    # Partial index doretmek
    op.execute("""
        CREATE INDEX ix_outbox_events_pending
            ON outbox_events (created_at)
            WHERE status = 'pending';
    """)


def downgrade() -> None:
    # Index awtomatiki ocya, yone tablisany pozmak yeterlikdir
    op.execute("DROP TABLE IF EXISTS outbox_events CASCADE;")
