"""Integration tests for Events API router."""

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.factory import create_app
from app.models.event import Event, PayloadType, ProcessingStatus, SourceType
from app.models.user import User


@pytest.fixture
def mock_app() -> any:
    app = create_app()

    # Mock settings & factory on app state
    mock_settings = MagicMock()
    mock_settings.app_version = "0.2.0"
    app.state.settings = mock_settings

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session_factory = MagicMock(return_value=mock_session)
    app.state.session_factory = mock_session_factory

    return app, mock_session


@pytest.mark.asyncio
async def test_get_event_not_found(mock_app: any) -> None:
    app, mock_session = mock_app
    mock_session.execute.return_value.scalar_one_or_none.return_value = None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/events/{uuid.uuid4()}")

    assert res.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_get_event_success(mock_app: any) -> None:
    app, mock_session = mock_app

    event_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_evt = Event(
        id=event_id,
        user_id=user_id,
        event_date=date.today(),
        captured_at=datetime.now(timezone.utc),
        source_type=SourceType.telegram,
        payload_type=PayloadType.text,
        raw_text="Today I wired a three-phase motor.",
        status=ProcessingStatus.pending,
        payload_metadata=None,
        is_deleted=False,
        attachments=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mock_session.execute.return_value.scalar_one_or_none.return_value = mock_evt

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/events/{event_id}")

    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["id"] == str(event_id)
    assert data["raw_text"] == "Today I wired a three-phase motor."
