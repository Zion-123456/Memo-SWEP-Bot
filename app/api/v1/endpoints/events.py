"""Event API endpoints (GET /events, GET /events/{id}, POST /events, DELETE /events/{id}, GET /users/{id}/events)."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import (
    get_ai_service,
    get_capture_service,
    get_event_repository,
    get_user_service,
)
from app.core.exceptions import UserNotFoundError
from app.models.event import EventSource
from app.repositories.event import EventRepository
from app.schemas.event import (
    EventCreate,
    EventDeleteResponse,
    EventListResponse,
    EventResponse,
    UserInsightsResponse,
)
from app.services.ai_memory import AiMemoryService
from app.services.capture import CaptureRequest, CaptureService
from app.services.user import UserService

router = APIRouter(prefix="/events", tags=["Events"])


@router.get(
    "",
    response_model=EventListResponse,
    summary="List all events",
    description="Retrieve paginated list of all active (non-deleted) events across users.",
)
async def list_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    event_repo: EventRepository = Depends(get_event_repository),
) -> EventListResponse:
    offset = (page - 1) * page_size
    items = await event_repo.list_active(limit=page_size, offset=offset)
    total = await event_repo.count_active()
    return EventListResponse(
        items=[EventResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{event_id}",
    response_model=EventResponse,
    summary="Get event by ID",
    description="Retrieve a single event and its linked media attachments.",
)
async def get_event(
    event_id: uuid.UUID,
    event_repo: EventRepository = Depends(get_event_repository),
) -> EventResponse:
    event = await event_repo.get_by_id_with_attachments(event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event with ID '{event_id}' not found.",
        )
    return EventResponse.model_validate(event)


@router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create event",
    description="Programmatically record a new text memory event via API.",
)
async def create_event(
    payload: EventCreate,
    user_service: UserService = Depends(get_user_service),
    capture_service: CaptureService = Depends(get_capture_service),
    event_repo: EventRepository = Depends(get_event_repository),
    ai_service: AiMemoryService | None = Depends(get_ai_service),
) -> EventResponse:
    try:
        await user_service.get_by_id(payload.user_id)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    req = CaptureRequest(
        user_id=payload.user_id,
        event_date=payload.event_date or date.today(),
        payload_type=payload.payload_type,
        source_type=payload.source_type or EventSource.api,
        raw_text=payload.raw_content if payload.raw_content is not None else payload.raw_text,
        payload_metadata=payload.payload_metadata,
    )
    result = await capture_service.capture(req)
    # Reload with attachments preloaded so pydantic serialization doesn't
    # trigger an async lazy-load (MissingGreenlet) on the relationship.
    event = await event_repo.get_by_id_with_attachments(result.event.id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist captured event.",
        )

    # Non-blocking: schedule AI processing after the capture commits.
    if ai_service is not None:
        ai_service.schedule(event.id)

    return EventResponse.model_validate(event)


@router.delete(
    "/{event_id}",
    response_model=EventDeleteResponse,
    summary="Delete event",
    description="Soft-delete an event by setting is_deleted=True and status=failed.",
)
async def delete_event(
    event_id: uuid.UUID,
    event_repo: EventRepository = Depends(get_event_repository),
) -> EventDeleteResponse:
    success = await event_repo.soft_delete(event_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event with ID '{event_id}' not found or already deleted.",
        )
    return EventDeleteResponse(id=event_id)


# User-scoped events endpoint
users_router = APIRouter(prefix="/users", tags=["Users"])


@users_router.get(
    "/{user_id}/events",
    response_model=EventListResponse,
    summary="Get user events",
    description="Retrieve all memories captured for a specific user.",
)
async def get_user_events(
    user_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_service: UserService = Depends(get_user_service),
    event_repo: EventRepository = Depends(get_event_repository),
) -> EventListResponse:
    try:
        await user_service.get_by_id(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    offset = (page - 1) * page_size
    items = await event_repo.list_by_user(user_id, limit=page_size, offset=offset)
    total = await event_repo.count_by_user_id(user_id)

    return EventListResponse(
        items=[EventResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@users_router.get(
    "/{user_id}/insights",
    response_model=UserInsightsResponse,
    summary="Get user insights",
    description="Retrieve AI-extracted insights (skills, tools, problems, solutions) from a user's processed memories.",
)
async def get_user_insights(
    user_id: uuid.UUID,
    event_repo: EventRepository = Depends(get_event_repository),
    user_service: UserService = Depends(get_user_service),
) -> UserInsightsResponse:
    """Return aggregated AI insights for a user's analysed memories."""
    from app.schemas.event import UserInsight

    try:
        await user_service.get_by_id(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    events = await event_repo.find_by_user_id(user_id, limit=50)
    analyzed = [e for e in events if e.ai_analysis]

    insights = []
    for evt in analyzed:
        analysis = evt.ai_analysis or {}
        insights.append(
            UserInsight(
                id=evt.id,
                event_date=evt.event_date,
                summary=analysis.get("summary"),
                skills=analysis.get("skills") or [],
                tools=analysis.get("tools") or [],
                problems=analysis.get("problems") or [],
                solutions=analysis.get("solutions") or [],
                lessons=analysis.get("lessons") or [],
                confidence=analysis.get("confidence"),
            )
        )

    return UserInsightsResponse(
        user_id=user_id,
        total_memories=len(events),
        analyzed_memories=len(analyzed),
        insights=insights,
    )
