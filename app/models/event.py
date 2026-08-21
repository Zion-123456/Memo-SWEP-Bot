"""Event ORM model — expanded for Sprint 2 Memory Capture Engine."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.attachment import Attachment
    from app.models.user import User


class SourceType(str, enum.Enum):
    """Channel through which an Event was captured."""
    telegram = "telegram"
    api = "api"


class PayloadType(str, enum.Enum):
    """The type of raw payload captured."""
    text = "text"
    voice = "voice"
    photo = "photo"
    document = "document"
    multimodal = "multimodal"


class ProcessingStatus(str, enum.Enum):
    """The processing lifecycle stage of an Event."""

    pending = "pending"
    processing = "processing"
    draft = "draft"
    processed = "processed"
    exported = "exported"
    failed = "failed"


# Retain EventStatus as alias for backward compatibility
EventStatus = ProcessingStatus
EventSource = SourceType


class Event(TimestampMixin, Base):
    """A discrete captured experience within a student's SWEP placement."""

    __tablename__ = "events"

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
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Exact timestamp when the event was recorded by the user.",
    )
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type_enum", create_constraint=True),
        nullable=False,
        default=SourceType.telegram,
    )
    payload_type: Mapped[PayloadType] = mapped_column(
        Enum(PayloadType, name="payload_type_enum", create_constraint=True),
        nullable=False,
        default=PayloadType.text,
        server_default="text",
    )
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="processing_status_enum", create_constraint=True),
        nullable=False,
        default=ProcessingStatus.pending,
        server_default="pending",
    )
    payload_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Schema-less metadata for AI-extracted fields (Sprint 2+).",
    )
    ai_analysis: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Sprint 3 structured AI analysis. The raw memory (raw_text) is "
        "the source of truth; this field is derived and never replaces it.",
    )
    processing_retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Number of AI processing attempts made for this event.",
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Soft-delete flag for user deletion.",
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="events")
    attachments: Mapped[list[Attachment]] = relationship(
        "Attachment",
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="select",
    )

    @property
    def raw_content(self) -> str | None:
        """Backward-compatible alias for the planned Sprint 2 naming."""
        return self.raw_text

    @raw_content.setter
    def raw_content(self, value: str | None) -> None:
        self.raw_text = value

    @property
    def processing_status(self) -> ProcessingStatus:
        """Backward-compatible alias for the planned Sprint 2 naming."""
        return self.status

    @processing_status.setter
    def processing_status(self, value: ProcessingStatus) -> None:
        self.status = value

    def __repr__(self) -> str:
        return (
            f"<Event id={self.id} user_id={self.user_id} "
            f"payload_type={self.payload_type.value!r} date={self.event_date}>"
        )
