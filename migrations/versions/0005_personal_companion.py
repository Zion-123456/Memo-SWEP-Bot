"""Add personal projects/drafts without replacing legacy records.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = depends_on = None


def upgrade():
    for name in (
        "university",
        "department",
        "programme",
        "company",
        "start_date",
        "end_date",
    ):
        op.alter_column("users", name, nullable=True)

    def timestamps():
        return [
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        ]

    op.create_table(
        "memo_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_key", sa.String(100), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default="false", nullable=False),
        *timestamps(),
        sa.UniqueConstraint("user_id", "name_key"),
    )
    op.create_index("ix_memo_projects_user_id", "memo_projects", ["user_id"])
    op.add_column(
        "events", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_events_memo_project", "events", "memo_projects", ["project_id"], ["id"]
    )
    op.create_index("ix_events_project_id", "events", ["project_id"])
    op.create_table(
        "memo_capture_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_key", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("original_text", sa.Text()),
        sa.Column("text", sa.Text()),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("answers", postgresql.JSONB(), nullable=False),
        sa.Column("media", postgresql.JSONB(), nullable=False),
        sa.Column("processing_error", sa.String(100)),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memo_projects.id"),
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id"),
            unique=True,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.UniqueConstraint("user_id", "source_key"),
    )
    op.create_index(
        "ix_memo_capture_drafts_user_id", "memo_capture_drafts", ["user_id"]
    )
    op.create_index("ix_memo_capture_drafts_state", "memo_capture_drafts", ["state"])


def downgrade():
    # Do not silently destroy drafts, projects or personal profiles on rollback.
    raise RuntimeError(
        "0005 rollback requires a reviewed data-preserving restore plan."
    )
