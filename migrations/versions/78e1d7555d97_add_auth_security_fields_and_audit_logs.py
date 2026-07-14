"""add auth security fields and audit logs

Revision ID: 78e1d7555d97
Revises: 72f842f79d39
Create Date: 2026-07-13 18:14:22.930461

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '78e1d7555d97'
down_revision: Union[str, None] = '72f842f79d39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users tablisasyna auth-security sütünleri ---
    op.add_column("users", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))

    op.add_column("users", sa.Column("totp_secret_encrypted", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column(
        "users",
        sa.Column("totp_backup_codes", postgresql.ARRAY(sa.Text()), nullable=True),
    )

    # --- audit_logs tablisasy ---
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # sorag: "bu user-iň soňky loginleri" ýaly query-ler üçin
    op.create_index("ix_audit_logs_user_id_created_at", "audit_logs", ["user_id", "created_at"])
    # sorag: "login_failed event-leri soňky 15 minutda" ýaly rate-limit/monitoring query-leri üçin
    op.create_index("ix_audit_logs_event_type_created_at", "audit_logs", ["event_type", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_event_type_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_column("users", "totp_backup_codes")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret_encrypted")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")