"""Progress narrative service — evidence-based growth stories."""

from __future__ import annotations

import uuid

from app.ai.longitudinal_models import ProgressNarrative
from app.ai.provider import AIProvider
from app.repositories.event import EventRepository
from app.repositories.knowledge_topic import KnowledgeTopicRepository
from app.repositories.memory_connection import MemoryConnectionRepository
from app.services.memory_retrieval import MemoryRetrievalService


class ProgressNarrativeService:
    """Generate progress narratives from stored evidence."""

    def __init__(
        self,
        event_repository: EventRepository,
        topic_repository: KnowledgeTopicRepository,
        connection_repository: MemoryConnectionRepository,
        ai_provider: AIProvider | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        self._events = event_repository
        self._topics = topic_repository
        self._connections = connection_repository
        self._provider = ai_provider
        self._enabled = enabled and ai_provider is not None

    async def generate(self, user_id: uuid.UUID) -> ProgressNarrative:
        """Build a progress narrative for the user."""
        events = list(await self._events.find_by_user_id(user_id, limit=100))
        topics = list(await self._topics.find_by_user_id(user_id))
        connections = list(await self._connections.find_by_user_id(user_id, limit=20))

        if len(events) < 2:
            return ProgressNarrative(insufficient_evidence=True)

        evidence = {
            "memories": MemoryRetrievalService.events_to_evidence(events),
            "topics": [
                {
                    "topic": t.topic,
                    "status": t.status.value,
                    "trend": t.trend.value,
                    "evidence": t.evidence,
                    "progression": t.progression or [],
                }
                for t in topics
            ],
            "connections": [
                {
                    "type": c.connection_type.value,
                    "explanation": c.explanation,
                    "source_event_id": str(c.source_event_id),
                    "target_event_id": str(c.target_event_id),
                }
                for c in connections
            ],
        }

        if self._enabled and self._provider is not None:
            try:
                return await self._provider.generate_progress_narrative(evidence)
            except Exception:
                pass

        return self._rule_based_narrative(events, topics)

    @staticmethod
    def _rule_based_narrative(events: list, topics: list) -> ProgressNarrative:
        dated = sorted(events, key=lambda e: e.event_date)
        evidence_lines: list[str] = []
        learning_set: set[str] = set()
        activities: set[str] = set()
        for evt in dated:
            analysis = evt.ai_analysis or {}
            if analysis.get("summary"):
                evidence_lines.append(
                    f"[{evt.event_date}] {analysis['summary']}"
                )
            for lesson in analysis.get("lessons") or []:
                learning_set.add(str(lesson))
            for activity in analysis.get("activities") or []:
                activities.add(str(activity))

        overview = (
            f"You've captured {len(events)} memories"
            + (
                f" spanning {dated[0].event_date} to {dated[-1].event_date}."
                if len(dated) >= 2
                else "."
            )
        )
        if topics:
            top = topics[0]
            overview += f" A recurring focus has been {top.topic}."

        changes: list[str] = []
        if len(dated) >= 2 and topics and topics[0].progression:
            changes.append(" → ".join(topics[0].progression))

        return ProgressNarrative(
            overview=overview,
            learning=sorted(learning_set)[:8],
            activities=sorted(activities)[:8],
            changes=changes,
            recent_direction=(
                f"Recent memories suggest continued focus on {topics[0].topic}."
                if topics
                else None
            ),
            evidence=evidence_lines[:8],
            insufficient_evidence=len(evidence_lines) == 0,
        )
