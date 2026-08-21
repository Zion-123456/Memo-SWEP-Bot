"""KnowledgeTopic ORM model — evolving user knowledge profile (Sprint 4)."""

from __future__ import annotations

import enum
import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class TopicTrend(str, enum.Enum):
    """Evidence-based trend label for a knowledge topic."""

    new = "new"
    growing = "growing"
    stable = "stable"
    declining = "declining"


class TopicStatus(str, enum.Enum):
    """Descriptive status — not a numeric score."""

    emerging = "emerging"
    developing = "developing"
    established = "established"


class KnowledgeTopic(TimestampMixin, Base):
    """A topic the user has explored across multiple memories."""

    __tablename__ = "knowledge_topics"
    __table_args__ = (
        UniqueConstraint("user_id", "topic", name="uq_knowledge_topics_user_topic"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_seen: Mapped[date] = mapped_column(Date, nullable=False)
    last_seen: Mapped[date] = mapped_column(Date, nullable=False)
    memory_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[TopicStatus] = mapped_column(
        Enum(TopicStatus, name="topic_status_enum", create_constraint=True),
        nullable=False,
        default=TopicStatus.emerging,
    )
    trend: Mapped[TopicTrend] = mapped_column(
        Enum(TopicTrend, name="topic_trend_enum", create_constraint=True),
        nullable=False,
        default=TopicTrend.new,
    )
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="List of {event_id, event_date, summary} traceable to memories.",
    )
    progression: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Ordered progression steps derived from evidence, if any.",
    )

    user: Mapped[User] = relationship("User", back_populates="knowledge_topics")
