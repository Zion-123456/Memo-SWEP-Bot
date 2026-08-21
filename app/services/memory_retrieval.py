"""Memory retrieval service — scoped search before NL query synthesis."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from app.models.event import Event
from app.repositories.event import EventRepository


class MemoryRetrievalService:
    """Retrieve relevant memories for a user query."""

    _STOP_WORDS = frozenset(
        {
            "a",
            "an",
            "the",
            "i",
            "my",
            "me",
            "what",
            "how",
            "when",
            "did",
            "do",
            "have",
            "has",
            "been",
            "about",
            "learned",
            "learning",
            "worked",
            "working",
            "show",
            "tell",
            "memo",
            "memories",
            "memory",
        }
    )

    def __init__(self, event_repository: EventRepository) -> None:
        self._repo = event_repository

    async def retrieve(
        self,
        user_id: uuid.UUID,
        *,
        query: str,
        time_range: str | None = None,
        topic: str | None = None,
        limit: int = 30,
    ) -> Sequence[Event]:
        """Retrieve memories scoped to user with optional filters."""
        if time_range:
            dated = await self._retrieve_by_time_range(user_id, time_range, limit)
            if dated:
                return dated

        if topic:
            return await self._repo.search_by_topic(user_id, topic, limit=limit)

        keywords = self.extract_keywords(query)
        if keywords:
            matches: list[Event] = []
            seen: set[uuid.UUID] = set()
            for keyword in keywords[:5]:
                for event in await self._repo.search_by_topic(user_id, keyword, limit=limit):
                    if event.id not in seen:
                        seen.add(event.id)
                        matches.append(event)
            if matches:
                return sorted(
                    matches,
                    key=lambda e: (e.event_date, e.captured_at),
                    reverse=True,
                )[:limit]

        return await self._repo.find_by_user_id(user_id, limit=limit)

    async def _retrieve_by_time_range(
        self,
        user_id: uuid.UUID,
        time_range: str,
        limit: int,
    ) -> Sequence[Event]:
        today = datetime.now(UTC).date()
        tr = time_range.lower()
        if "today" in tr:
            return list(await self._repo.find_by_user_and_date(user_id, today))[:limit]
        if "yesterday" in tr:
            return list(
                await self._repo.find_by_user_and_date(user_id, today - timedelta(days=1))
            )[:limit]
        if "week" in tr or "last week" in tr:
            if "last week" in tr:
                start = today - timedelta(days=today.weekday() + 7)
                end = start + timedelta(days=6)
            else:
                start = today - timedelta(days=today.weekday())
                end = today
            return list(await self._repo.find_by_user_date_range(user_id, start, end))[
                :limit
            ]
        if "month" in tr:
            start = today.replace(day=1)
            return list(await self._repo.find_by_user_date_range(user_id, start, today))[
                :limit
            ]
        return []

    @classmethod
    def extract_keywords(cls, query: str) -> list[str]:
        """Extract meaningful keywords from a natural-language query."""
        tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
        return [token for token in tokens if len(token) > 2 and token not in cls._STOP_WORDS]

    @staticmethod
    def events_to_evidence(events: Sequence[Event]) -> list[dict[str, object]]:
        """Convert events to a compact evidence pack for AI prompts."""
        pack: list[dict[str, object]] = []
        for event in sorted(events, key=lambda e: (e.event_date, e.captured_at)):
            analysis = event.ai_analysis or {}
            pack.append(
                {
                    "event_id": str(event.id),
                    "event_date": event.event_date.isoformat() if event.event_date else None,
                    "raw_text": event.raw_text,
                    "summary": analysis.get("summary"),
                    "skills": analysis.get("skills") or [],
                    "tools": analysis.get("tools") or [],
                    "problems": analysis.get("problems") or [],
                    "solutions": analysis.get("solutions") or [],
                    "lessons": analysis.get("lessons") or [],
                    "activities": analysis.get("activities") or [],
                    "entities": analysis.get("entities") or [],
                }
            )
        return pack

    @staticmethod
    def infer_time_range(query: str) -> str | None:
        lower = query.lower()
        if "today" in lower:
            return "today"
        if "yesterday" in lower:
            return "yesterday"
        if "last week" in lower:
            return "last week"
        if "this week" in lower or "week" in lower:
            return "this week"
        if "this month" in lower or "month" in lower:
            return "this month"
        return None

    @staticmethod
    def infer_topic(query: str) -> str | None:
        """Extract topic after 'about' or 'regarding'."""
        match = re.search(
            r"\b(?:about|regarding|on|related to)\s+(.+?)(?:\?|$)",
            query,
            re.IGNORECASE,
        )
        if match:
            topic = match.group(1).strip().rstrip("?.!")
            return topic if len(topic) > 2 else None
        return None
