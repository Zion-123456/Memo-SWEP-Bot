"""Unit tests for CaptureService."""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.attachment import FileType
from app.models.event import PayloadType, SourceType
from app.services.capture import CaptureRequest, CaptureService, MediaPayload


@pytest.mark.asyncio
async def test_capture_text_memory_success() -> None:
    event_repo = AsyncMock()
    attachment_repo = AsyncMock()
    storage = AsyncMock()

    mock_event = MagicMock()
    mock_event.id = uuid.uuid4()
    mock_event.event_date = date.today()
    mock_event.payload_type = PayloadType.text
    event_repo.create.return_value = mock_event

    service = CaptureService(event_repo, attachment_repo, storage)

    req = CaptureRequest(
        user_id=uuid.uuid4(),
        event_date=date.today(),
        payload_type=PayloadType.text,
        source_type=SourceType.telegram,
        raw_text="Today I wired a three-phase motor starter.",
    )

    res = await service.capture(req)

    assert res.event == mock_event
    assert res.attachments_count == 0
    event_repo.create.assert_called_once()
    attachment_repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_capture_media_memory_success() -> None:
    event_repo = AsyncMock()
    attachment_repo = AsyncMock()
    storage = AsyncMock()

    mock_event = MagicMock()
    mock_event.id = uuid.uuid4()
    mock_event.event_date = date.today()
    mock_event.payload_type = PayloadType.photo
    event_repo.create.return_value = mock_event
    storage.store.return_value = "2025/08/05/uuid_photo.jpg"

    service = CaptureService(event_repo, attachment_repo, storage)

    media_item = MediaPayload(
        file_bytes=b"fake-image-bytes",
        filename="photo.jpg",
        content_type="image/jpeg",
        file_type=FileType.photo,
        telegram_file_id="tg_12345",
        width=1920,
        height=1080,
    )

    req = CaptureRequest(
        user_id=uuid.uuid4(),
        event_date=date.today(),
        payload_type=PayloadType.photo,
        source_type=SourceType.telegram,
        raw_text="Wiring schematic diagram",
        media_items=[media_item],
    )

    res = await service.capture(req)

    assert res.attachments_count == 1
    storage.store.assert_called_once()
    attachment_repo.create.assert_called_once()
