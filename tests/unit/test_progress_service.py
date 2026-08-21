"""Unit tests for ProgressService (Sprint 3.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.models.event import Event, PayloadType, ProcessingStatus, SourceType
from app.repositories.event import EventRepository
from app.services.progress import ProgressService, ProgressSummary

_TZ = UTC


def _make_event(
    *,
    payload_type: PayloadType = PayloadType.text,
    status: ProcessingStatus = ProcessingStatus.pending,
    ai_analysis: dict | None = None,
    created: datetime | None = None,
    offset_days: int = 0,
) -> Event:
    """Build an Event ORM instance for tests."""
    ev = Event(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        event_date=date.today(),
        captured_at=datetime.now(_TZ) - timedelta(days=offset_days),
        source_type=SourceType.telegram,
        payload_type=payload_type,
        raw_text="Some text",
        status=status,
        ai_analysis=ai_analysis,
        is_deleted=False,
        created_at=created or (datetime.now(_TZ) - timedelta(days=offset_days)),
        updated_at=datetime.now(_TZ),
    )
    ev.attachments = []
    return ev


@pytest.mark.asyncio
async def test_progress_counts_all_payload_types() -> None:
    """ProgressService counts text, voice, photo, document events correctly."""
    events = [
        _make_event(payload_type=PayloadType.text),
        _make_event(payload_type=PayloadType.voice),
        _make_event(payload_type=PayloadType.photo),
        _make_event(payload_type=PayloadType.document),
        _make_event(payload_type=PayloadType.voice),
    ]
    mock_repo = EventRepository.__new__(EventRepository)
    mock_repo.list_by_user = AsyncMock(return_value=events)

    service = ProgressService(mock_repo)
    summary = await service.get_progress(uuid.uuid4())

    assert summary.total_memories == 5
    assert summary.texts == 1
    assert summary.voices == 2
    assert summary.photos == 1
    assert summary.documents == 1


@pytest.mark.asyncio
async def test_progress_ai_processed_count() -> None:
    """Only events with ai_analysis and processed status are counted."""
    events = [
        _make_event(status=ProcessingStatus.processed, ai_analysis={"summary": "ok"}),
        _make_event(status=ProcessingStatus.processed, ai_analysis={"summary": "ok"}),
        _make_event(status=ProcessingStatus.pending, ai_analysis=None),
        _make_event(status=ProcessingStatus.processed, ai_analysis=None),
        _make_event(status=ProcessingStatus.failed, ai_analysis={"failure": True}),
    ]
    mock_repo = EventRepository.__new__(EventRepository)
    mock_repo.list_by_user = AsyncMock(return_value=events)

    service = ProgressService(mock_repo)
    summary = await service.get_progress(uuid.uuid4())

    assert summary.ai_processed == 2


@pytest.mark.asyncio
async def test_progress_empty_user() -> None:
    """A user with no events gets zeroed metrics."""
    mock_repo = EventRepository.__new__(EventRepository)
    mock_repo.list_by_user = AsyncMock(return_value=[])

    service = ProgressService(mock_repo)
    summary = await service.get_progress(uuid.uuid4())

    assert summary.total_memories == 0
    assert summary.ai_processed == 0
    assert summary.streak_days == 0


@pytest.mark.asyncio
async def test_progress_active_days() -> None:
    """Active days is the count of distinct dates with captures."""
    today = datetime.now(_TZ)
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)

    events = [
        _make_event(created=today),
        _make_event(created=today),  # same day
        _make_event(created=yesterday),
        _make_event(created=last_week),
    ]
    mock_repo = EventRepository.__new__(EventRepository)
    mock_repo.list_by_user = AsyncMock(return_value=events)

    service = ProgressService(mock_repo)
    summary = await service.get_progress(uuid.uuid4())

    assert summary.active_days == 3


@pytest.mark.asyncio
async def test_progress_today_and_week_counts() -> None:
    """Memories today and this week are calculated from created_at."""
    today = datetime.now(_TZ)
    yesterday = today - timedelta(days=1)
    six_days_ago = today - timedelta(days=6)
    eight_days_ago = today - timedelta(days=8)

    events = [
        _make_event(created=today),
        _make_event(created=today),
        _make_event(created=yesterday),
        _make_event(created=six_days_ago),
        _make_event(created=eight_days_ago),
    ]
    mock_repo = EventRepository.__new__(EventRepository)
    mock_repo.list_by_user = AsyncMock(return_value=events)

    service = ProgressService(mock_repo)
    summary = await service.get_progress(uuid.uuid4())

    assert summary.memories_today == 2
    assert summary.memories_this_week == 4  # today, yesterday, six days ago


@pytest.mark.asyncio
async def test_progress_streak() -> None:
    """Streak counts consecutive days ending at today."""
    today = datetime.now(_TZ).date()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)

    events = [
        _make_event(created=datetime.combine(today, datetime.min.time(), tzinfo=_TZ)),
        _make_event(
            created=datetime.combine(yesterday, datetime.min.time(), tzinfo=_TZ)
        ),
        _make_event(
            created=datetime.combine(day_before, datetime.min.time(), tzinfo=_TZ)
        ),
    ]
    mock_repo = EventRepository.__new__(EventRepository)
    mock_repo.list_by_user = AsyncMock(return_value=events)

    service = ProgressService(mock_repo)
    summary = await service.get_progress(uuid.uuid4())

    assert summary.streak_days == 3


@pytest.mark.asyncio
async def test_progress_streak_broken() -> None:
    """A gap in captures breaks the streak."""
    today = datetime.now(_TZ).date()
    two_days_ago = today - timedelta(days=2)  # yesterday is missing!

    events = [
        _make_event(created=datetime.combine(today, datetime.min.time(), tzinfo=_TZ)),
        _make_event(
            created=datetime.combine(two_days_ago, datetime.min.time(), tzinfo=_TZ)
        ),
    ]
    mock_repo = EventRepository.__new__(EventRepository)
    mock_repo.list_by_user = AsyncMock(return_value=events)

    service = ProgressService(mock_repo)
    summary = await service.get_progress(uuid.uuid4())

    assert summary.streak_days == 1  # only today


@pytest.mark.asyncio
async def test_progress_no_streak_when_never_captured() -> None:
    """No events → streak is 0."""
    mock_repo = EventRepository.__new__(EventRepository)
    mock_repo.list_by_user = AsyncMock(return_value=[])

    service = ProgressService(mock_repo)
    summary = await service.get_progress(uuid.uuid4())

    assert summary.streak_days == 0


@pytest.mark.asyncio
async def test_progress_returns_progresssummary() -> None:
    """get_progress returns a ProgressSummary instance."""
    mock_repo = EventRepository.__new__(EventRepository)
    mock_repo.list_by_user = AsyncMock(return_value=[_make_event()])

    service = ProgressService(mock_repo)
    summary = await service.get_progress(uuid.uuid4())

    assert isinstance(summary, ProgressSummary)
