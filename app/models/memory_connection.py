"""MemoryConnection ORM model — relationships between events (Sprint 4)."""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class ConnectionType(str, enum.Enum):
    """Type of relationship between two memories."""

    continues = "CONTINUES"
    expands = "EXPANDS"
    reflects = "REFLECTS"
    solves = "SOLVES"
    follows_from = "FOLLOWS_FROM"
    relates_to = "RELATES_TO"


class MemoryConnection(TimestampMixin, Base):
    """A meaningful, explainable link between two user memories."""

    __tablename__ = "memory_connections"
    __table_args__ = (
        UniqueConstraint(
            "source_event_id",
            "target_event_id",
            "connection_type",
            name="uq_memory_connections_pair_type",
        ),
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
    source_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_type: Mapped[ConnectionType] = mapped_column(
        Enum(ConnectionType, name="connection_type_enum", create_constraint=True),
        nullable=False,
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="memory_connections")
    source_event: Mapped[Event] = relationship(
        "Event",
        foreign_keys=[source_event_id],
    )
    target_event: Mapped[Event] = relationship(
        "Event",
        foreign_keys=[target_event_id],
    )
