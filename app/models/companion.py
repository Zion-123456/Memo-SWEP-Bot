"""Owner-scoped personal projects and persistent, reviewable capture drafts."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Project(TimestampMixin, Base):
    __tablename__ = "memo_projects"
    __table_args__ = (UniqueConstraint("user_id", "name_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    name_key: Mapped[str] = mapped_column(String(100))
    archived: Mapped[bool] = mapped_column(default=False, server_default="false")


class CaptureDraft(TimestampMixin, Base):
    __tablename__ = "memo_capture_drafts"
    __table_args__ = (UniqueConstraint("user_id", "source_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_key: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="capture")
    state: Mapped[str] = mapped_column(String(20), default="open", index=True)
    original_text: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    step: Mapped[int] = mapped_column(Integer, default=0)
    answers: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)
    media: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    processing_error: Mapped[str | None] = mapped_column(String(100))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("memo_projects.id"))
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id"), unique=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
