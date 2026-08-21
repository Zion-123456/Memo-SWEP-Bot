"""User ORM model."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.event import Event
    from app.models.knowledge_topic import KnowledgeTopic
    from app.models.memory_connection import MemoryConnection
    from app.models.progress_snapshot import ProgressSnapshot
    from app.models.user_longitudinal_state import UserLongitudinalState
    from app.models.weekly_reflection import WeeklyReflection


class User(TimestampMixin, Base):
    """Represents a student registered with Memo.

    A ``User`` is created during the /start onboarding flow and holds the
    student's academic and SWEP placement details. The ``telegram_id`` is the
    stable, external identifier used to correlate Telegram messages with the
    corresponding user record.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    university: Mapped[str] = mapped_column(String(500), nullable=False)
    department: Mapped[str] = mapped_column(String(500), nullable=False)
    programme: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(500), nullable=False)
    supervisor: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Relationships
    events: Mapped[list[Event]] = relationship(
        "Event",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )
    conversation: Mapped[Conversation | None] = relationship(
        "Conversation",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="select",
    )
    knowledge_topics: Mapped[list[KnowledgeTopic]] = relationship(
        "KnowledgeTopic",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )
    memory_connections: Mapped[list[MemoryConnection]] = relationship(
        "MemoryConnection",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )
    progress_snapshots: Mapped[list[ProgressSnapshot]] = relationship(
        "ProgressSnapshot",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )
    weekly_reflections: Mapped[list[WeeklyReflection]] = relationship(
        "WeeklyReflection",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )
    longitudinal_state: Mapped[UserLongitudinalState | None] = relationship(
        "UserLongitudinalState",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<User id={self.id} telegram_id={self.telegram_id} "
            f"name={self.first_name!r}>"
        )
