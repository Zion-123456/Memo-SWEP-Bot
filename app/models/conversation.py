"""Conversation ORM model.

Tracks the active dialogue state for a given user. This record is the
source of truth for where in an onboarding or future multi-turn flow a user
currently is. It is updated by ``ConversationService`` as state transitions
occur, providing both crash-recovery semantics and an admin-visible audit of
conversation progress.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class Conversation(Base):
    """The current dialogue state for a single user.

    One-to-one with ``User`` — enforced at the database level via a unique
    constraint. The ``state`` field holds a string representation of the
    current ``ConversationHandler`` state so that the record is human-readable
    in the database console.
    """

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_conversations_user_id"),
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
    )
    state: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Current ConversationHandler state name for observability.",
    )
    last_message_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Telegram message_id of the most recent bot reply.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="conversation")

    def __repr__(self) -> str:
        return (
            f"<Conversation id={self.id} user_id={self.user_id} "
            f"state={self.state!r}>"
        )
