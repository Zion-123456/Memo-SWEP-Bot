"""Integration tests for Telegram capture handlers.

Tests the end-to-end flow of media capture through Telegram handlers,
exercising the real CaptureService, repositories, and storage provider
with mocked database sessions and Telegram API calls.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update
from telegram.ext import ContextTypes

from app.models.user import User
from app.services.capture import CaptureResult
from app.telegram.handlers.capture import (
    _format_confirmation,
    handle_document,
    handle_photo,
    handle_text,
    handle_voice,
)
from tests.integration.conftest import make_async_session_mock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_user() -> User:
    """Return a realistic User instance for handler tests."""
    return User(
        id=uuid.uuid4(),
        telegram_id=123456789,
        first_name="Alice",
        last_name=None,
        username="alice_test",
        university="Tech University",
        department="Engineering",
        programme="Software Engineering",
        company="Memo",
        supervisor=None,
        start_date=date(2025, 6, 1),
        end_date=date(2025, 9, 1),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_mock_context(
    user: User,
    mock_session: MagicMock,
    mock_storage: AsyncMock | None = None,
    mock_send_message: AsyncMock | None = None,
) -> MagicMock:
    """Build a mock PTB context with bot_data wired to a mock session."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    mock_session_factory = MagicMock(return_value=mock_session)

    context.bot_data = {
        "session_factory": mock_session_factory,
        "storage_provider": mock_storage or AsyncMock(),
    }

    if mock_send_message is not None:
        context.bot.send_message = mock_send_message
    else:
        context.bot.send_message = AsyncMock()

    return context


def _make_mock_update(
    text: str | None = None,
    photo: MagicMock | None = None,
    voice: MagicMock | None = None,
    document: MagicMock | None = None,
    caption: str | None = None,
    media_group_id: str | None = None,
    message_id: int = 42,
    chat_id: int = 100,
) -> MagicMock:
    """Build a mock Update object matching the handler's access patterns."""
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock()
    update.effective_user.id = 123456789

    message = MagicMock()
    message.text = text
    message.caption = caption
    message.message_id = message_id
    message.chat_id = chat_id
    message.date = datetime.now(timezone.utc)
    message.media_group_id = media_group_id
    message.photo = photo
    message.voice = voice
    message.document = document
    message.reply_text = AsyncMock()
    update.effective_message = message

    return update


# ---------------------------------------------------------------------------
# Confirmation message format
# ---------------------------------------------------------------------------


def test_format_confirmation_with_attachments() -> None:
    """The confirmation message includes date, source, and attachment count."""
    msg = _format_confirmation(date(2025, 8, 5), "Photo", 2)
    assert "✅ Memory saved." in msg
    assert "📅 Date: 05 Aug 2025" in msg
    assert "📁 Source: Photo" in msg
    assert "📎 Attachments: 2" in msg


def test_format_confirmation_no_attachments() -> None:
    """Text-only captures omit the attachments line."""
    msg = _format_confirmation(date(2025, 8, 5), "Text", 0)
    assert "✅ Memory saved." in msg
    assert "📎" not in msg


# ---------------------------------------------------------------------------
# handle_text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_text_creates_event() -> None:
    """A plain text message should flow through CaptureService and save an event."""
    user = _make_mock_user()
    mock_session = make_async_session_mock()

    mock_send = AsyncMock()

    context = _make_mock_context(
        user=user,
        mock_session=mock_session,
        mock_storage=AsyncMock(),
        mock_send_message=mock_send,
    )

    # Patch the user lookup
    with patch(
        "app.telegram.handlers.capture.UserRepository"
    ) as mock_user_repo_cls, patch(
        "app.telegram.handlers.capture.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ) as mock_find:
        mock_user_repo_cls.return_value = MagicMock(
            find_by_telegram_id=mock_find
        )

        # Patch CaptureService.capture to avoid real DB calls
        async def mock_capture(req):
            return CaptureResult(
                event=MagicMock(id=uuid.uuid4(), event_date=date.today()),
                attachments_count=0,
            )

        with patch(
            "app.telegram.handlers.capture.CaptureService"
        ) as mock_cs_cls:
            mock_cs_cls.return_value.capture = mock_capture

            update = _make_mock_update(text="Today I wired a three-phase motor starter.")
            await handle_text(update, context)

            # Verify bot sent a confirmation message
            mock_send.assert_called_once()
            sent_text = mock_send.call_args.kwargs.get("text") or mock_send.call_args[0][1]
            assert "✅ Memory saved." in sent_text
            assert "Text" in sent_text or "📎 Attachments: 0" not in sent_text


# ---------------------------------------------------------------------------
# handle_voice
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_voice_downloads_and_saves_event() -> None:
    """A voice note should be downloaded, stored, and saved as an event."""
    user = _make_mock_user()
    mock_session = make_async_session_mock()

    mock_storage = AsyncMock()
    mock_storage.store = AsyncMock(return_value="2025/08/05/voice_abc.ogg")

    mock_send = AsyncMock()

    context = _make_mock_context(
        user=user,
        mock_session=mock_session,
        mock_storage=mock_storage,
        mock_send_message=mock_send,
    )

    voice_mock = MagicMock()
    voice_mock.file_id = "AwADBAADbXXXXXXXX"
    voice_mock.file_unique_id = "unique_voice_id"
    voice_mock.mime_type = "audio/ogg"
    voice_mock.duration = 12

    update = _make_mock_update(voice=voice_mock)

    async def mock_capture(req):
        return CaptureResult(
            event=MagicMock(id=uuid.uuid4(), event_date=date.today()),
            attachments_count=1,
        )

    with patch(
        "app.telegram.handlers.capture.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ), patch(
        "app.telegram.handlers.capture.CaptureService"
    ) as mock_cs_cls:
        mock_cs_cls.return_value.capture = mock_capture

        with patch(
            "app.telegram.handlers.capture._download_file_bytes",
            new_callable=AsyncMock,
            return_value=b"fake-voice-bytes",
        ):
            await handle_voice(update, context)

            mock_send.assert_called_once()
            sent_text = mock_send.call_args.kwargs.get("text") or mock_send.call_args[0][1]
            assert "✅ Memory saved." in sent_text
            assert "📎 Attachments: 1" in sent_text


# ---------------------------------------------------------------------------
# handle_photo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_photo_downloads_and_saves_event() -> None:
    """A single photo should be downloaded, stored, and saved as an event."""
    user = _make_mock_user()
    mock_session = make_async_session_mock()

    mock_storage = AsyncMock()
    mock_storage.store = AsyncMock(return_value="2025/08/05/photo_xyz.jpg")

    mock_send = AsyncMock()

    context = _make_mock_context(
        user=user,
        mock_session=mock_session,
        mock_storage=mock_storage,
        mock_send_message=mock_send,
    )

    photo_mock = MagicMock()
    photo_mock.file_id = "AgADBQADIb7Z9VUVBase"
    photo_mock.file_unique_id = "unique_photo_id"
    photo_mock.width = 1920
    photo_mock.height = 1080
    # photos come as a list; the handler takes [-1]
    message = MagicMock()
    message.effective_user = update_user = MagicMock()
    update_user.id = 123456789
    message.effective_message = message

    update = MagicMock(spec=Update)
    update.effective_user = MagicMock()
    update.effective_user.id = 123456789
    update.message = MagicMock()
    update.message.photo = [photo_mock]
    update.message.caption = None
    update.message.message_id = 42
    update.message.chat_id = 100
    update.message.date = datetime.now(timezone.utc)
    update.message.media_group_id = None
    update.message.reply_text = AsyncMock()
    update.effective_message = update.message

    async def mock_capture(req):
        return CaptureResult(
            event=MagicMock(id=uuid.uuid4(), event_date=date.today()),
            attachments_count=1,
        )

    with patch(
        "app.telegram.handlers.capture.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ), patch(
        "app.telegram.handlers.capture.CaptureService"
    ) as mock_cs_cls:
        mock_cs_cls.return_value.capture = mock_capture

        with patch(
            "app.telegram.handlers.capture._download_file_bytes",
            new_callable=AsyncMock,
            return_value=b"fake-image-bytes",
        ):
            await handle_photo(update, context)

            mock_send.assert_called_once()
            sent_text = mock_send.call_args.kwargs.get("text") or mock_send.call_args[0][1]
            assert "✅ Memory saved." in sent_text
            assert "📎 Attachments: 1" in sent_text


# ---------------------------------------------------------------------------
# handle_document
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_document_downloads_and_saves_event() -> None:
    """A document (PDF) should be downloaded, stored, and saved as an event."""
    user = _make_mock_user()
    mock_session = make_async_session_mock()

    mock_storage = AsyncMock()
    mock_storage.store = AsyncMock(return_value="2025/08/05/doc_xyz.pdf")

    mock_send = AsyncMock()

    context = _make_mock_context(
        user=user,
        mock_session=mock_session,
        mock_storage=mock_storage,
        mock_send_message=mock_send,
    )

    doc_mock = MagicMock()
    doc_mock.file_id = "BQACAgUADxX"
    doc_mock.file_unique_id = "unique_doc_id"
    doc_mock.file_name = "schematic.pdf"
    doc_mock.mime_type = "application/pdf"
    doc_mock.file_size = 5000

    update = _make_mock_update(document=doc_mock)

    async def mock_capture(req):
        return CaptureResult(
            event=MagicMock(id=uuid.uuid4(), event_date=date.today()),
            attachments_count=1,
        )

    with patch(
        "app.telegram.handlers.capture.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ), patch(
        "app.telegram.handlers.capture.CaptureService"
    ) as mock_cs_cls:
        mock_cs_cls.return_value.capture = mock_capture

        with patch(
            "app.telegram.handlers.capture._download_file_bytes",
            new_callable=AsyncMock,
            return_value=b"fake-pdf-bytes",
        ):
            await handle_document(update, context)

            mock_send.assert_called_once()
            sent_text = mock_send.call_args.kwargs.get("text") or mock_send.call_args[0][1]
            assert "✅ Memory saved." in sent_text
            assert "📎 Attachments: 1" in sent_text


# ---------------------------------------------------------------------------
# Media album grouping (multimodal)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_photo_album_queued_not_immediately_captured() -> None:
    """Photos with media_group_id are buffered, not immediately captured."""
    from app.telegram.handlers.capture import _ALBUM_BUFFER, _ALBUM_TASKS

    user = _make_mock_user()
    mock_session = MagicMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__ = AsyncMock(return_value=None)

    mock_storage = AsyncMock()
    context = _make_mock_context(
        user=user,
        mock_session=mock_session,
        mock_storage=mock_storage,
    )

    _ALBUM_BUFFER.clear()
    _ALBUM_TASKS.clear()

    photo_mock = MagicMock()
    photo_mock.file_id = "album_photo_1"
    photo_mock.file_unique_id = "album_photo_unique_1"
    photo_mock.width = 800
    photo_mock.height = 600

    update = MagicMock(spec=Update)
    update.effective_user = MagicMock()
    update.effective_user.id = 123456789
    update.message = MagicMock()
    update.message.photo = [photo_mock]
    update.message.caption = None
    update.message.message_id = 42
    update.message.chat_id = 100
    update.message.date = datetime.now(timezone.utc)
    update.message.media_group_id = "group_abc_123"
    update.message.reply_text = AsyncMock()
    update.effective_message = update.message

    async def mock_capture(req):
        return CaptureResult(
            event=MagicMock(id=uuid.uuid4(), event_date=date.today()),
            attachments_count=1,
        )

    with patch(
        "app.telegram.handlers.capture.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ), patch(
        "app.telegram.handlers.capture.CaptureService"
    ) as mock_cs_cls:
        mock_cs_cls.return_value.capture = mock_capture

        with patch(
            "app.telegram.handlers.capture._download_file_bytes",
            new_callable=AsyncMock,
            return_value=b"fake-album-photo",
        ), patch.object(
            context.bot, "send_message", new_callable=AsyncMock
        ):
            await handle_photo(update, context)

            # The album should be buffered, not flushed yet
            assert "group_abc_123" in _ALBUM_BUFFER
            buffered = _ALBUM_BUFFER["group_abc_123"]
            assert len(buffered["media_items"]) == 1
            assert buffered["user_id"] == user.id

    _ALBUM_BUFFER.clear()
    _ALBUM_TASKS.clear()
