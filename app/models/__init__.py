"""Models package.

Importing all model modules here ensures that their table definitions are
registered on ``Base.metadata`` before Alembic or SQLAlchemy inspects it.
"""

from app.models.attachment import Attachment, FileType
from app.models.base import Base, TimestampMixin
from app.models.conversation import Conversation
from app.models.event import (
    Event,
    EventSource,
    EventStatus,
    PayloadType,
    ProcessingStatus,
    SourceType,
)
from app.models.knowledge_topic import KnowledgeTopic, TopicStatus, TopicTrend
from app.models.memory_connection import ConnectionType, MemoryConnection
from app.models.progress_snapshot import ProgressSnapshot, SnapshotTrigger
from app.models.user import User
from app.models.user_longitudinal_state import UserLongitudinalState
from app.models.weekly_reflection import WeeklyReflection

__all__ = [
    "Attachment",
    "Base",
    "Conversation",
    "Event",
    "ConnectionType",
    "EventSource",
    "EventStatus",
    "FileType",
    "KnowledgeTopic",
    "MemoryConnection",
    "PayloadType",
    "ProcessingStatus",
    "ProgressSnapshot",
    "SnapshotTrigger",
    "SourceType",
    "TimestampMixin",
    "TopicStatus",
    "TopicTrend",
    "User",
    "UserLongitudinalState",
    "WeeklyReflection",
]
