"""Add durable webhook delivery and PostgreSQL Telegram persistence.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "memo_telegram_state",
        sa.Column("namespace", sa.String(150), primary_key=True),
        sa.Column("key", sa.String(200), primary_key=True),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_memo_telegram_state_expires_at", "memo_telegram_state", ["expires_at"]
    )
    op.create_table(
        "memo_telegram_inbox",
        sa.Column("update_id", sa.BigInteger(), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_type", sa.String(100)),
    )
    op.create_index("ix_memo_telegram_inbox_state", "memo_telegram_inbox", ["state"])
    op.create_index(
        "ix_memo_telegram_inbox_pending",
        "memo_telegram_inbox",
        ["state", "available_at"],
    )
    op.create_table(
        "memo_telegram_lease",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("owner", sa.String(50), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    raise RuntimeError(
        "Restore a reviewed backup; do not silently discard Telegram state or queued updates."
    )
