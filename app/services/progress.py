"""Progress service — user statistics for the Telegram dashboard.

All metrics are computed from real stored data. Nothing is fabricated.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import structlog

from app.models.event import Event, PayloadType, ProcessingStatus
from app.repositories.event import EventRepository

logger = structlog.get_logger(__name__)

_TZ = UTC


class ProgressService:
    """Calculate progress metrics for a single user.

    Args:
        event_repository: Data access object for Event records.
    """

    def __init__(self, event_repository: EventRepository) -> None:
        self._repo = event_repository

    async def get_progress(self, user_id: uuid.UUID) -> ProgressSummary:
        """Compute all progress metrics for the given user.

        Args:
            user_id: The internal UUID of the user.

        Returns:
            A :class:`ProgressSummary` with aggregate statistics.
        """
        events = await self._repo.list_by_user(user_id, limit=10_000)

        total_memories = len(events)
        payload_counts: Counter[str] = Counter()
        processed_count = 0
        active_days: set[date] = set()

        now = datetime.now(_TZ)
        today = now.date()
        week_ago = today - timedelta(days=6)

        memories_today = 0
        memories_this_week = 0

        for ev in events:
            if ev.payload_type:
                payload_counts[ev.payload_type.value] += 1

            if ev.status == ProcessingStatus.processed and ev.ai_analysis:
                processed_count += 1

            created_dt = ev.created_at
            if isinstance(created_dt, datetime):
                created_date = created_dt.astimezone(_TZ).date()
            else:
                created_date = created_dt

            if created_date == today:
                memories_today += 1
            if created_date >= week_ago:
                memories_this_week += 1
            active_days.add(created_date)

        streak = self._calculate_streak(events)

        return ProgressSummary(
            total_memories=total_memories,
            memories_today=memories_today,
            memories_this_week=memories_this_week,
            active_days=len(active_days),
            ai_processed=processed_count,
            documents=payload_counts.get(PayloadType.document.value, 0),
            photos=payload_counts.get(PayloadType.photo.value, 0),
            voices=payload_counts.get(PayloadType.voice.value, 0),
            texts=payload_counts.get(PayloadType.text.value, 0),
            streak_days=streak,
        )

    @staticmethod
    def _calculate_streak(events: Sequence[Event]) -> int:
        """Calculate the current capture streak (consecutive days ending at today).

        A streak counts any day (including today) on which the user captured
        at least one memory.
        """
        if not events:
            return 0

        now = datetime.now(_TZ)
        today = now.date()

        active_dates: set[date] = set()
        for ev in events:
            created_dt = ev.created_at
            if isinstance(created_dt, datetime):
                created_d = created_dt.astimezone(_TZ).date()
            else:
                created_d = created_dt
            active_dates.add(created_d)

        streak = 0
        current = today
        while current in active_dates:
            streak += 1
            current -= timedelta(days=1)

        return streak


class ProgressSummary:
    """Plain data container for user progress metrics."""

    def __init__(
        self,
        total_memories: int,
        memories_today: int,
        memories_this_week: int,
        active_days: int,
        ai_processed: int,
        documents: int,
        photos: int,
        voices: int,
        texts: int,
        streak_days: int,
    ) -> None:
        self.total_memories = total_memories
        self.memories_today = memories_today
        self.memories_this_week = memories_this_week
        self.active_days = active_days
        self.ai_processed = ai_processed
        self.documents = documents
        self.photos = photos
        self.voices = voices
        self.texts = texts
        self.streak_days = streak_days
