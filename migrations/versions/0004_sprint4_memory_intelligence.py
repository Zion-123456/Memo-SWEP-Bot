"""sprint4_memory_intelligence

Adds longitudinal memory intelligence tables:
- knowledge_topics
- memory_connections
- progress_snapshots
- weekly_reflections
- user_longitudinal_states

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    topic_status_enum = sa.Enum(
        "emerging",
        "developing",
        "established",
        name="topic_status_enum",
        create_constraint=True,
    )
    topic_trend_enum = sa.Enum(
        "new",
        "growing",
        "stable",
        "declining",
        name="topic_trend_enum",
        create_constraint=True,
    )
    connection_type_enum = sa.Enum(
        "CONTINUES",
        "EXPANDS",
        "REFLECTS",
        "SOLVES",
        "FOLLOWS_FROM",
        "RELATES_TO",
        name="connection_type_enum",
        create_constraint=True,
    )
    snapshot_trigger_enum = sa.Enum(
        "manual",
        "threshold",
        "scheduled",
        name="snapshot_trigger_enum",
        create_constraint=True,
    )

    # topic_status_enum.create(op.get_bind(), checkfirst=True)
    # topic_trend_enum.create(op.get_bind(), checkfirst=True)
    # connection_type_enum.create(op.get_bind(), checkfirst=True)
    # snapshot_trigger_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "knowledge_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic", sa.String(length=500), nullable=False),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("first_seen", sa.Date(), nullable=False),
        sa.Column("last_seen", sa.Date(), nullable=False),
        sa.Column("memory_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            topic_status_enum,
            nullable=False,
            server_default="emerging",
        ),
        sa.Column(
            "trend",
            topic_trend_enum,
            nullable=False,
            server_default="new",
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("progression", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "topic", name="uq_knowledge_topics_user_topic"),
    )
    op.create_index("ix_knowledge_topics_user_id", "knowledge_topics", ["user_id"])

    op.create_table(
        "memory_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_type", connection_type_enum, nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_event_id",
            "target_event_id",
            "connection_type",
            name="uq_memory_connections_pair_type",
        ),
    )
    op.create_index("ix_memory_connections_user_id", "memory_connections", ["user_id"])
    op.create_index(
        "ix_memory_connections_source_event_id",
        "memory_connections",
        ["source_event_id"],
    )
    op.create_index(
        "ix_memory_connections_target_event_id",
        "memory_connections",
        ["target_event_id"],
    )

    op.create_table(
        "progress_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("narrative", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "evidence_event_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("memory_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "trigger",
            snapshot_trigger_enum,
            nullable=False,
            server_default="manual",
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_progress_snapshots_user_id", "progress_snapshots", ["user_id"])

    op.create_table(
        "weekly_reflections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("week_end", sa.Date(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("memory_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "insufficient_evidence",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_weekly_reflections_user_id", "weekly_reflections", ["user_id"])

    op.create_table(
        "user_longitudinal_states",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_analysis_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "events_since_last_analysis",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "last_analyzed_memory_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_proactive_insight_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "pending_proactive_insight",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_longitudinal_states")
    op.drop_table("weekly_reflections")
    op.drop_table("progress_snapshots")
    op.drop_table("memory_connections")
    op.drop_table("knowledge_topics")

    sa.Enum(name="snapshot_trigger_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="connection_type_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="topic_trend_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="topic_status_enum").drop(op.get_bind(), checkfirst=True)
