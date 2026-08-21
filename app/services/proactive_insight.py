"""Proactive insight delivery and connection hints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.repositories.event import EventRepository
from app.repositories.memory_connection import MemoryConnectionRepository
from app.repositories.user_longitudinal_state import UserLongitudinalStateRepository

INSIGHT_COOLDOWN_HOURS = 24


class ProactiveInsightService:
    """Surface useful insights without spamming users."""

    def __init__(
        self,
        state_repository: UserLongitudinalStateRepository,
        connection_repository: MemoryConnectionRepository,
        event_repository: EventRepository,
    ) -> None:
        self._state = state_repository
        self._connections = connection_repository
        self._events = event_repository

    async def get_connection_hint(self, user_id: uuid.UUID, event_id: uuid.UUID) -> str | None:
        """Return a short connection hint for a newly captured memory."""
        connections = await self._connections.find_for_event(user_id, event_id, limit=1)
        if connections:
            conn = connections[0]
            other_id = (
                conn.target_event_id
                if conn.source_event_id == event_id
                else conn.source_event_id
            )
            other = await self._events.get_by_id(other_id)
            if other and other.ai_analysis:
                topic = (other.ai_analysis.get("summary") or other.raw_text or "")[:60]
                return f"🔗 This connects with something you captured earlier: {topic}"
            return "🔗 This connects with an earlier memory."

        # Lightweight overlap check against recent events
        recent = await self._events.find_by_user_id(user_id, limit=10)
        current = await self._events.get_by_id(event_id)
        if not current:
            return None
        current_terms = self._extract_terms(current)
        for evt in recent:
            if evt.id == event_id:
                continue
            overlap = current_terms & self._extract_terms(evt)
            if len(overlap) >= 2:
                term = next(iter(overlap)).title()
                return (
                    f"🔗 This connects with something you captured earlier about {term}."
                )
        return None

    async def pop_pending_insight(self, user_id: uuid.UUID) -> dict | None:
        """Return and clear a pending proactive insight if cooldown allows."""
        state = await self._state.get_or_create(user_id)
        if not state.pending_proactive_insight:
            return None

        now = datetime.now(UTC)
        if state.last_proactive_insight_at:
            elapsed = now - state.last_proactive_insight_at
            if elapsed < timedelta(hours=INSIGHT_COOLDOWN_HOURS):
                return None

        insight = state.pending_proactive_insight
        await self._state.update(
            user_id,
            {
                "pending_proactive_insight": None,
                "last_proactive_insight_at": now,
            },
        )
        return insight

    @staticmethod
    def _extract_terms(event) -> set[str]:
        terms: set[str] = set()
        analysis = event.ai_analysis or {}
        for field in ("skills", "tools", "entities", "activities", "lessons"):
            for item in analysis.get(field) or []:
                if isinstance(item, str) and len(item) > 3:
                    terms.add(item.lower())
        if event.raw_text:
            for word in event.raw_text.split():
                if len(word) > 4:
                    terms.add(word.strip(".,!?").lower())
        return terms
