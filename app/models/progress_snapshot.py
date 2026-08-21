"""ProgressSnapshot ORM model — cached progress narratives (Sprint 4)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class SnapshotTrigger(str, enum.Enum):
    """What caused a progress snapshot to be generated."""

    manual = "manual"
    threshold = "threshold"
    scheduled = "scheduled"


class ProgressSnapshot(Base):
    """A point-in-time, evidence-based progress narrative."""

    __tablename__ = "progress_snapshots"

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
    narrative: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Structured narrative sections with evidence references.",
    )
    evidence_event_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    memory_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trigger: Mapped[SnapshotTrigger] = mapped_column(
        Enum(SnapshotTrigger, name="snapshot_trigger_enum", create_constraint=True),
        nullable=False,
        default=SnapshotTrigger.manual,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="progress_snapshots")
