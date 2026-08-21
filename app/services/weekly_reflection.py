"""Weekly reflection service."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.ai.longitudinal_models import WeeklyReflectionContent
from app.ai.provider import AIProvider
from app.ai.provider import AIProvider
from app.repositories.event import EventRepository
from app.repositories.weekly_reflection import WeeklyReflectionRepository
from app.services.memory_retrieval import MemoryRetrievalService

from dataclasses import dataclass

MIN_WEEKLY_MEMORIES = 2


@dataclass
class WeeklyReflectionResult:
    """Weekly reflection with display metadata."""

    content: WeeklyReflectionContent
    memory_count: int = 0
    active_days: int = 0
    document_count: int = 0
    week_start: date | None = None
    week_end: date | None = None


class WeeklyReflectionService:
    """Generate and persist weekly reflections."""

    def __init__(
        self,
        event_repository: EventRepository,
        reflection_repository: WeeklyReflectionRepository,
        ai_provider: AIProvider | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        self._events = event_repository
        self._reflections = reflection_repository
        self._provider = ai_provider
        self._enabled = enabled and ai_provider is not None

    async def get_or_generate(
        self,
        user_id: uuid.UUID,
        *,
        reference_date: date | None = None,
    ) -> WeeklyReflectionResult:
        """Return reflection for the current week, generating if needed."""
        today = reference_date or datetime.now(UTC).date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        existing = await self._reflections.find_for_week(user_id, week_start)
        if existing and not existing.insufficient_evidence:
            return WeeklyReflectionResult(
                content=WeeklyReflectionContent.from_dict(existing.content),
                memory_count=existing.memory_count,
                active_days=existing.active_days,
                week_start=week_start,
                week_end=week_end,
            )

        events = list(
            await self._events.find_by_user_date_range(user_id, week_start, week_end)
        )
        active_days = len({e.event_date for e in events})
        doc_count = sum(1 for e in events if e.payload_type.value == "document")

        if len(events) < MIN_WEEKLY_MEMORIES:
            content = WeeklyReflectionContent(insufficient_evidence=True)
            await self._persist(
                user_id,
                week_start,
                week_end,
                content,
                memory_count=len(events),
                active_days=active_days,
            )
            return WeeklyReflectionResult(
                content=content,
                memory_count=len(events),
                active_days=active_days,
                document_count=doc_count,
                week_start=week_start,
                week_end=week_end,
            )

        evidence = {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "memories": MemoryRetrievalService.events_to_evidence(events),
        }

        if self._enabled and self._provider is not None:
            try:
                content = await self._provider.generate_weekly_reflection(evidence)
            except Exception:
                content = self._rule_based(events)
        else:
            content = self._rule_based(events)

        await self._persist(
            user_id,
            week_start,
            week_end,
            content,
            memory_count=len(events),
            active_days=active_days,
        )
        return WeeklyReflectionResult(
            content=content,
            memory_count=len(events),
            active_days=active_days,
            document_count=doc_count,
            week_start=week_start,
            week_end=week_end,
        )

    async def _persist(
        self,
        user_id: uuid.UUID,
        week_start: date,
        week_end: date,
        content: WeeklyReflectionContent,
        *,
        memory_count: int,
        active_days: int,
    ) -> None:
        existing = await self._reflections.find_for_week(user_id, week_start)
        payload = {
            "summary": content.summary,
            "learned": content.learned,
            "worked_on": content.worked_on,
            "problems": content.problems,
            "insights": content.insights,
            "recurring_themes": content.recurring_themes,
            "progress_notes": content.progress_notes,
            "insufficient_evidence": content.insufficient_evidence,
        }
        if existing:
            await self._reflections.update(
                existing.id,
                {
                    "content": payload,
                    "memory_count": memory_count,
                    "active_days": active_days,
                    "insufficient_evidence": content.insufficient_evidence,
                },
            )
        else:
            await self._reflections.create(
                {
                    "user_id": user_id,
                    "week_start": week_start,
                    "week_end": week_end,
                    "content": payload,
                    "memory_count": memory_count,
                    "active_days": active_days,
                    "insufficient_evidence": content.insufficient_evidence,
                }
            )

    @staticmethod
    def _rule_based(events: list) -> WeeklyReflectionContent:
        themes: set[str] = set()
        learned: set[str] = set()
        worked: set[str] = set()
        problems: set[str] = set()

        for evt in events:
            analysis = evt.ai_analysis or {}
            for skill in analysis.get("skills") or []:
                themes.add(str(skill))
            for lesson in analysis.get("lessons") or []:
                learned.add(str(lesson))
            for activity in analysis.get("activities") or []:
                worked.add(str(activity))
            for problem in analysis.get("problems") or []:
                problems.add(str(problem))

        summary = (
            f"This week you captured {len(events)} memories"
            + (f" across {len({e.event_date for e in events})} days." if events else ".")
        )
        if themes:
            summary += f" Themes included {', '.join(sorted(themes)[:3])}."

        return WeeklyReflectionContent(
            summary=summary,
            learned=sorted(learned)[:5],
            worked_on=sorted(worked)[:5],
            problems=sorted(problems)[:5],
            recurring_themes=sorted(themes)[:5],
            insufficient_evidence=len(events) < MIN_WEEKLY_MEMORIES,
        )
