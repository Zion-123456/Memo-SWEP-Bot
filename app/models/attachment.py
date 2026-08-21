"""Attachment ORM model — expanded for Sprint 2 media metadata."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.event import Event


class FileType(str, enum.Enum):
    """The media type of an attachment as categorised by Telegram."""

    photo = "photo"
    document = "document"
    audio = "audio"
    video = "video"
    voice = "voice"


class Attachment(Base):
    """A media file attached to an Event with comprehensive file metadata."""

    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_type: Mapped[FileType] = mapped_column(
        Enum(FileType, name="file_type_enum", create_constraint=True),
        nullable=False,
    )
    telegram_file_id: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Local or cloud storage URL/path reference.",
    )
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="SHA-256 hex digest.")
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    event: Mapped[Event] = relationship("Event", back_populates="attachments")

    def __repr__(self) -> str:
        return (
            f"<Attachment id={self.id} event_id={self.event_id} "
            f"type={self.file_type.value!r} filename={self.original_filename!r}>"
        )
