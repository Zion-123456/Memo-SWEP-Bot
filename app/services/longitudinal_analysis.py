"""Longitudinal analysis service — cross-memory intelligence (Sprint 4)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.longitudinal_models import (
    KnowledgeTopicAnalysis,
    LongitudinalAnalysisResult,
    ProactiveInsight,
)
from app.ai.provider import AIProvider
from app.models.knowledge_topic import KnowledgeTopic, TopicStatus, TopicTrend
from app.models.memory_connection import ConnectionType, MemoryConnection
from app.models.progress_snapshot import SnapshotTrigger
from app.repositories.event import EventRepository
from app.repositories.knowledge_topic import KnowledgeTopicRepository
from app.repositories.memory_connection import MemoryConnectionRepository
from app.repositories.progress_snapshot import ProgressSnapshotRepository
from app.repositories.user_longitudinal_state import UserLongitudinalStateRepository
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.progress_narrative import ProgressNarrativeService

logger = structlog.get_logger(__name__)

ANALYSIS_THRESHOLD = 5
MIN_MEMORIES_FOR_ANALYSIS = 3


class LongitudinalAnalysisService:
    """Analyze memories over time and persist topics/connections."""

    def __init__(
        self,
        ai_provider: AIProvider | None,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        enabled: bool = True,
        analysis_threshold: int = ANALYSIS_THRESHOLD,
    ) -> None:
        self._provider = ai_provider
        self._session_factory = session_factory
        self._enabled = enabled and ai_provider is not None
        self._threshold = analysis_threshold

    def schedule_after_capture(self, user_id: uuid.UUID) -> None:
        """Fire-and-forget incremental analysis trigger."""
        if not self._enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._safe_maybe_analyze(user_id))

    async def _safe_maybe_analyze(self, user_id: uuid.UUID) -> None:
        try:
            await self.maybe_analyze(user_id)
        except Exception as exc:
            logger.warning(
                "longitudinal.analysis_failed",
                user_id=str(user_id),
                error=str(exc),
            )

    async def maybe_analyze(self, user_id: uuid.UUID) -> bool:
        """Run analysis if threshold met. Returns True if analysis ran."""
        async with self._session_factory() as session:
            state_repo = UserLongitudinalStateRepository(session)
            event_repo = EventRepository(session)
            state = await state_repo.get_or_create(user_id)
            state.events_since_last_analysis += 1

            total = await event_repo.count_by_user_id(user_id)
            should_run = (
                state.events_since_last_analysis >= self._threshold
                or (
                    state.last_analysis_at is None
                    and total >= MIN_MEMORIES_FOR_ANALYSIS
                )
            )
            await session.commit()

            if not should_run:
                return False

        await self.analyze(user_id, trigger=SnapshotTrigger.threshold)
        return True

    async def analyze(
        self,
        user_id: uuid.UUID,
        *,
        trigger: SnapshotTrigger = SnapshotTrigger.manual,
    ) -> LongitudinalAnalysisResult | None:
        """Run full longitudinal analysis for a user."""
        async with self._session_factory() as session:
            event_repo = EventRepository(session)
            events = list(await event_repo.find_by_user_id(user_id, limit=100))
            if len(events) < MIN_MEMORIES_FOR_ANALYSIS:
                return None

            evidence = MemoryRetrievalService.events_to_evidence(events)
            processed = [e for e in events if e.ai_analysis and e.ai_analysis.get("summary")]

        result = await self._analyze_with_ai(evidence)
        if result is None:
            result = self._analyze_rule_based(processed if processed else events)

        async with self._session_factory() as session:
            await self._persist_topics(session, user_id, result)
            await self._persist_connections(session, user_id, result, events)
            await self._update_state(session, user_id, len(events))
            await self._maybe_snapshot(session, user_id, result, len(events), trigger)
            await session.commit()

        return result

    async def _analyze_with_ai(
        self,
        evidence: list[dict[str, object]],
    ) -> LongitudinalAnalysisResult | None:
        if not self._enabled or self._provider is None:
            return None
        try:
            return await self._provider.analyze_longitudinal(evidence)
        except Exception as exc:
            logger.warning("longitudinal.ai_failed", error=str(exc))
            return None

    def _analyze_rule_based(self, events: list) -> LongitudinalAnalysisResult:
        """Deterministic fallback when AI is unavailable."""
        from collections import Counter

        topic_counter: Counter[str] = Counter()
        topic_events: dict[str, list] = {}

        for event in events:
            analysis = event.ai_analysis or {}
            candidates = set()
            for field in ("skills", "tools", "entities", "activities"):
                for item in analysis.get(field) or []:
                    if isinstance(item, str) and len(item) > 2:
                        candidates.add(item.strip().lower())
            summary = analysis.get("summary") or event.raw_text or ""
            if summary:
                for word in summary.split():
                    if len(word) > 4:
                        candidates.add(word.strip(".,!?").lower())

            for topic in candidates:
                topic_counter[topic] += 1
                topic_events.setdefault(topic, []).append(event)

        topics: list[KnowledgeTopicAnalysis] = []
        for topic, count in topic_counter.most_common(5):
            if count < 2:
                continue
            ev_list = topic_events[topic][:5]
            from app.ai.longitudinal_models import TopicEvidence

            evidence_objs: list[TopicEvidence] = []
            for evt in ev_list:
                analysis = evt.ai_analysis or {}
                summary = analysis.get("summary") or (evt.raw_text or "")[:120]
                ev = TopicEvidence.from_dict(
                    {
                        "event_id": str(evt.id),
                        "event_date": evt.event_date.isoformat() if evt.event_date else None,
                        "summary": summary,
                    }
                )
                if ev:
                    evidence_objs.append(ev)
            if not evidence_objs:
                continue
            topics.append(
                KnowledgeTopicAnalysis(
                    topic=topic.title(),
                    status="developing" if count >= 3 else "emerging",
                    trend="growing" if count >= 3 else "new",
                    evidence=evidence_objs,
                )
            )

        return LongitudinalAnalysisResult(
            topics=topics,
            connections=[],
            insufficient_evidence=len(topics) == 0,
        )

    async def _persist_topics(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        result: LongitudinalAnalysisResult,
    ) -> None:
        repo = KnowledgeTopicRepository(session)
        for topic_data in result.topics:
            if not topic_data.evidence:
                continue
            existing = await repo.find_by_user_and_topic(user_id, topic_data.topic)
            evidence_payload = [
                {
                    "event_id": ev.event_id,
                    "event_date": ev.event_date,
                    "summary": ev.summary,
                }
                for ev in topic_data.evidence
            ]
            dates = [
                date.fromisoformat(ev.event_date)
                for ev in topic_data.evidence
                if ev.event_date
            ]
            first_seen = min(dates) if dates else date.today()
            last_seen = max(dates) if dates else date.today()

            status = self._map_status(topic_data.status)
            trend = self._map_trend(topic_data.trend)

            if existing:
                existing.last_seen = max(existing.last_seen, last_seen)
                existing.memory_count = len(evidence_payload)
                existing.status = status
                existing.trend = trend
                existing.evidence = evidence_payload
                existing.progression = topic_data.progression or None
                existing.category = topic_data.category
                session.add(existing)
            else:
                topic = KnowledgeTopic(
                    user_id=user_id,
                    topic=topic_data.topic,
                    category=topic_data.category,
                    first_seen=first_seen,
                    last_seen=last_seen,
                    memory_count=len(evidence_payload),
                    status=status,
                    trend=trend,
                    evidence=evidence_payload,
                    progression=topic_data.progression or None,
                )
                session.add(topic)

    async def _persist_connections(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        result: LongitudinalAnalysisResult,
        events: list,
    ) -> None:
        repo = MemoryConnectionRepository(session)
        valid_ids = {str(e.id) for e in events}

        for conn in result.connections:
            if (
                conn.source_event_id not in valid_ids
                or conn.target_event_id not in valid_ids
            ):
                continue
            try:
                conn_type = ConnectionType(conn.connection_type)
            except ValueError:
                continue
            source_id = uuid.UUID(conn.source_event_id)
            target_id = uuid.UUID(conn.target_event_id)
            if await repo.exists(source_id, target_id, conn_type.value):
                continue
            session.add(
                MemoryConnection(
                    user_id=user_id,
                    source_event_id=source_id,
                    target_event_id=target_id,
                    connection_type=conn_type,
                    explanation=conn.explanation,
                )
            )

    async def _update_state(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        memory_count: int,
    ) -> None:
        state_repo = UserLongitudinalStateRepository(session)
        state = await state_repo.get_or_create(user_id)
        state.last_analysis_at = datetime.now(UTC)
        state.events_since_last_analysis = 0
        state.last_analyzed_memory_count = memory_count

    async def _maybe_snapshot(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        result: LongitudinalAnalysisResult,
        memory_count: int,
        trigger: SnapshotTrigger,
    ) -> None:
        if result.insufficient_evidence:
            return
        narrative_service = ProgressNarrativeService(
            EventRepository(session),
            KnowledgeTopicRepository(session),
            MemoryConnectionRepository(session),
            self._provider,
            enabled=self._enabled,
        )
        narrative = await narrative_service.generate(user_id)
        if narrative.insufficient_evidence:
            return

        snapshot_repo = ProgressSnapshotRepository(session)
        await snapshot_repo.create(
            {
                "user_id": user_id,
                "narrative": {
                    "title": narrative.title,
                    "overview": narrative.overview,
                    "learning": narrative.learning,
                    "activities": narrative.activities,
                    "changes": narrative.changes,
                    "recent_direction": narrative.recent_direction,
                    "evidence": narrative.evidence,
                },
                "evidence_event_ids": [
                    ev.event_id for topic in result.topics for ev in topic.evidence
                ],
                "memory_count": memory_count,
                "trigger": trigger,
            }
        )

        insight = self._build_proactive_insight(result)
        if insight:
            state_repo = UserLongitudinalStateRepository(session)
            state = await state_repo.get_or_create(user_id)
            await state_repo.update(
                user_id,
                {
                    "pending_proactive_insight": {
                        "message": insight.message,
                        "topics": insight.topics,
                        "evidence_event_ids": insight.evidence_event_ids,
                    }
                },
            )

    @staticmethod
    def _build_proactive_insight(
        result: LongitudinalAnalysisResult,
    ) -> ProactiveInsight | None:
        if not result.topics or len(result.topics) < 1:
            return None
        top = result.topics[0]
        if len(top.evidence) < 3:
            return None
        message = (
            f"Over your recent memories, you've repeatedly explored {top.topic}.\n\n"
        )
        if top.progression:
            message += (
                "Your understanding appears to be shifting:\n"
                + " → ".join(top.progression[:3])
            )
        else:
            message += f"Your focus on {top.topic} is developing across multiple captures."
        return ProactiveInsight(
            message=message,
            topics=[top.topic],
            evidence_event_ids=[ev.event_id for ev in top.evidence[:5]],
        )

    @staticmethod
    def _map_status(value: str) -> TopicStatus:
        mapping = {
            "emerging": TopicStatus.emerging,
            "developing": TopicStatus.developing,
            "established": TopicStatus.established,
        }
        return mapping.get(value.lower(), TopicStatus.developing)

    @staticmethod
    def _map_trend(value: str) -> TopicTrend:
        mapping = {
            "new": TopicTrend.new,
            "growing": TopicTrend.growing,
            "stable": TopicTrend.stable,
            "declining": TopicTrend.declining,
        }
        return mapping.get(value.lower(), TopicTrend.growing)
