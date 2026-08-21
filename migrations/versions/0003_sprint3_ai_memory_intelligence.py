"""sprint3_ai_memory_intelligence

Adds the AI Memory Intelligence Layer storage: a ``processing`` status, a JSONB
``ai_analysis`` column holding the structured extraction, and a
``processing_retry_count`` column for retry/observability.

The raw memory (``raw_text``) column is intentionally untouched — AI analysis is
a derived layer stored separately, preserving the source of truth.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the 'processing' state to the processing_status_enum.
    # Idempotent so re-runs don't fail on an already-present value.
    op.execute("ALTER TYPE processing_status_enum ADD VALUE IF NOT EXISTS 'processing'")

    # Structured AI analysis (summary, skills, tools, problems, solutions, ...).
    op.add_column(
        "events",
        sa.Column(
            "ai_analysis",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # Operational metadata: how many AI processing attempts have been made.
    op.add_column(
        "events",
        sa.Column(
            "processing_retry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    # PostgreSQL cannot remove enum values, so 'processing' is intentionally left
    # on the type when downgrading.
    op.drop_column("events", "processing_retry_count")
    op.drop_column("events", "ai_analysis")
