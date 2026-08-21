"""Sprint 4 growth and intelligence API endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_ai_provider, get_db_session
from app.core.exceptions import UserNotFoundError
from app.repositories.event import EventRepository
from app.repositories.knowledge_topic import KnowledgeTopicRepository
from app.repositories.memory_connection import MemoryConnectionRepository
from app.repositories.user import UserRepository
from app.repositories.weekly_reflection import WeeklyReflectionRepository
from app.schemas.growth import (
    KnowledgeTopicResponse,
    KnowledgeTopicsListResponse,
    MemoryConnectionResponse,
    MemoryConnectionsListResponse,
    MemoryQueryRequest,
    MemoryQueryResponse,
    ProgressNarrativeResponse,
    WeeklyReflectionResponse,
)
from app.services.memory_query import MemoryQueryService
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.progress_narrative import ProgressNarrativeService
from app.services.user import UserService
from app.services.weekly_reflection import WeeklyReflectionService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/users", tags=["Growth"])


async def _ensure_user(user_id: uuid.UUID, session: AsyncSession) -> None:
    user_service = UserService(UserRepository(session))
    try:
        await user_service.get_by_id(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/{user_id}/topics",
    response_model=KnowledgeTopicsListResponse,
    summary="Get user knowledge topics",
)
async def get_user_topics(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeTopicsListResponse:
    await _ensure_user(user_id, session)
    repo = KnowledgeTopicRepository(session)
    topics = await repo.find_by_user_id(user_id)
    return KnowledgeTopicsListResponse(
        user_id=user_id,
        topics=[KnowledgeTopicResponse.model_validate(t) for t in topics],
        total=len(topics),
    )


@router.get(
    "/{user_id}/connections",
    response_model=MemoryConnectionsListResponse,
    summary="Get memory connections",
)
async def get_user_connections(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> MemoryConnectionsListResponse:
    await _ensure_user(user_id, session)
    repo = MemoryConnectionRepository(session)
    connections = await repo.find_by_user_id(user_id)
    return MemoryConnectionsListResponse(
        user_id=user_id,
        connections=[MemoryConnectionResponse.model_validate(c) for c in connections],
        total=len(connections),
    )


@router.get(
    "/{user_id}/progress",
    response_model=ProgressNarrativeResponse,
    summary="Get progress narrative",
)
async def get_user_progress(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    ai_provider=Depends(get_ai_provider),
) -> ProgressNarrativeResponse:
    await _ensure_user(user_id, session)
    service = ProgressNarrativeService(
        EventRepository(session),
        KnowledgeTopicRepository(session),
        MemoryConnectionRepository(session),
        ai_provider,
        enabled=ai_provider is not None,
    )
    narrative = await service.generate(user_id)
    return ProgressNarrativeResponse(
        user_id=user_id,
        title=narrative.title,
        overview=narrative.overview,
        learning=narrative.learning,
        activities=narrative.activities,
        changes=narrative.changes,
        recent_direction=narrative.recent_direction,
        evidence=narrative.evidence,
        insufficient_evidence=narrative.insufficient_evidence,
    )


@router.get(
    "/{user_id}/growth",
    response_model=KnowledgeTopicsListResponse,
    summary="Get user growth profile",
)
async def get_user_growth(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeTopicsListResponse:
    return await get_user_topics(user_id, session)


@router.get(
    "/{user_id}/reflections/weekly",
    response_model=WeeklyReflectionResponse,
    summary="Get weekly reflection",
)
async def get_weekly_reflection(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    ai_provider=Depends(get_ai_provider),
) -> WeeklyReflectionResponse:
    await _ensure_user(user_id, session)
    from datetime import UTC, datetime, timedelta

    service = WeeklyReflectionService(
        EventRepository(session),
        WeeklyReflectionRepository(session),
        ai_provider,
        enabled=ai_provider is not None,
    )
    content = await service.get_or_generate(user_id)
    week_start = content.week_start or datetime.now(UTC).date()
    week_end = content.week_end or week_start
    return WeeklyReflectionResponse(
        user_id=user_id,
        week_start=week_start,
        week_end=week_end,
        summary=content.content.summary,
        learned=content.content.learned,
        worked_on=content.content.worked_on,
        problems=content.content.problems,
        insights=content.content.insights,
        recurring_themes=content.content.recurring_themes,
        progress_notes=content.content.progress_notes,
        memory_count=content.memory_count,
        active_days=content.active_days,
        insufficient_evidence=content.content.insufficient_evidence,
    )


@router.post(
    "/{user_id}/query",
    response_model=MemoryQueryResponse,
    summary="Query user memories",
)
async def query_memories(
    user_id: uuid.UUID,
    payload: MemoryQueryRequest,
    session: AsyncSession = Depends(get_db_session),
    ai_provider=Depends(get_ai_provider),
) -> MemoryQueryResponse:
    await _ensure_user(user_id, session)
    query_service = MemoryQueryService(
        MemoryRetrievalService(EventRepository(session)),
        ai_provider,
        enabled=ai_provider is not None,
    )
    answer = await query_service.answer(
        user_id,
        payload.query,
        time_range=payload.time_range,
        topic=payload.topic,
    )
    insufficient = "not enough" in answer.lower() or "don't have any" in answer.lower()
    return MemoryQueryResponse(
        user_id=user_id,
        query=payload.query,
        answer=answer,
        insufficient_evidence=insufficient,
    )
