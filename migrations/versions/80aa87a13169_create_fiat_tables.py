"""create_fiat_tables

Revision ID: 80aa87a13169
Revises: 7d6ecb555e4c
Create Date: 2026-07-23 19:02:29.946356

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '80aa87a13169'
down_revision: Union[str, None] = '7d6ecb555e4c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE wallets (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id),
        currency VARCHAR(3) NOT NULL DEFAULT 'USD',
        balance_minor BIGINT NOT NULL DEFAULT 0,
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_wallets_user_currency UNIQUE (user_id, currency),
        CONSTRAINT chk_balance_non_negative CHECK (balance_minor >= 0)
    )
    """)

    op.execute("""
    CREATE TABLE transactions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        idempotency_key VARCHAR(255) NOT NULL UNIQUE,
        type VARCHAR(20) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'completed',
        amount_minor BIGINT NOT NULL,
        currency VARCHAR(3) NOT NULL,
        metadata JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("""
    CREATE TABLE ledger_entries (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        transaction_id UUID NOT NULL REFERENCES transactions(id),
        wallet_id UUID NOT NULL REFERENCES wallets(id),
        amount_minor BIGINT NOT NULL,
        direction VARCHAR(6) NOT NULL,
        balance_after BIGINT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("CREATE INDEX ix_ledger_wallet_id ON ledger_entries(wallet_id)")
    op.execute("CREATE INDEX ix_ledger_transaction_id ON ledger_entries(transaction_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ledger_transaction_id")
    op.execute("DROP INDEX IF EXISTS ix_ledger_wallet_id")
    op.execute("DROP TABLE IF EXISTS ledger_entries")
    op.execute("DROP TABLE IF EXISTS transactions")
    op.execute("DROP TABLE IF EXISTS wallets")
