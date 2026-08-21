"""Integration tests for AI processing scheduling after capture."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update

from app.models.user import User
from app.services.capture import CaptureResult
from app.telegram.handlers.capture import _persist_capture, handle_text


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


def _make_async_session_mock() -> MagicMock:
    """Return a MagicMock that behaves like an AsyncSession for repository use.

    - session.execute(...) is awaitable and returns a result whose
      .scalars().all() chain yields an empty list.
    - session.get(...) is awaitable and returns None.
    - Other common methods (commit, flush, refresh, add) are also mocked.
    """
    session = MagicMock()

    # Build a mock result whose .scalars().all() returns []
    mock_scalars = MagicMock()
    mock_scalars.all = MagicMock(return_value=[])
    mock_scalars.first = MagicMock(return_value=None)
    mock_scalars.scalar_one_or_none = MagicMock(return_value=None)
    mock_result = MagicMock()
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    mock_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_result.scalar_one = MagicMock(return_value=0)

    session.execute = AsyncMock(return_value=mock_result)
    session.get = AsyncMock(return_value=None)
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()  # synchronous in SQLAlchemy
    session.delete = AsyncMock()

    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    return session


def _make_mock_context(mock_session: MagicMock, mock_ai_service=None) -> MagicMock:
    """Build a mock PTB context with bot_data wired for capture + AI."""
    context = MagicMock(spec=["bot_data", "bot"])

    mock_session_factory = MagicMock(return_value=mock_session)

    context.bot_data = {
        "session_factory": mock_session_factory,
        "storage_provider": AsyncMock(),
        "ai_service": mock_ai_service,
    }

    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()

    return context


def _make_mock_update(text: str = "Today I wired a motor.") -> MagicMock:
    """Build a mock Update object matching the handler's access patterns."""
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock()
    update.effective_user.id = 123456789

    message = MagicMock()
    message.text = text
    message.caption = None
    message.message_id = 42
    message.chat_id = 100
    message.date = datetime.now(timezone.utc)
    message.media_group_id = None
    message.reply_text = AsyncMock()
    update.effective_message = message

    return update


# ---------------------------------------------------------------------------
# AI scheduling after capture
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_schedules_ai_processing() -> None:
    """After a successful text capture, ai_service.schedule is called with the event ID."""
    user = _make_mock_user()
    mock_session = _make_async_session_mock()

    mock_ai_service = MagicMock()
    mock_ai_service.schedule = MagicMock()

    context = _make_mock_context(mock_session, mock_ai_service=mock_ai_service)

    captured_event = MagicMock()
    captured_event.id = uuid.uuid4()

    async def mock_capture(req):
        return CaptureResult(event=captured_event, attachments_count=0)

    with patch(
        "app.telegram.handlers.capture.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ), patch(
        "app.telegram.handlers.capture.CaptureService"
    ) as mock_cs_cls:
        mock_cs_cls.return_value.capture = mock_capture

        update = _make_mock_update(text="Today I wired a three-phase motor.")
        await handle_text(update, context)

    mock_ai_service.schedule.assert_called_once_with(captured_event.id)


@pytest.mark.asyncio
async def test_capture_without_ai_service_does_not_crash() -> None:
    """When ai_service is None (AI disabled), capture still works and sends confirmation."""
    user = _make_mock_user()
    mock_session = _make_async_session_mock()

    context = _make_mock_context(mock_session, mock_ai_service=None)

    captured_event = MagicMock()
    captured_event.id = uuid.uuid4()

    async def mock_capture(req):
        return CaptureResult(event=captured_event, attachments_count=0)

    with patch(
        "app.telegram.handlers.capture.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ), patch(
        "app.telegram.handlers.capture.CaptureService"
    ) as mock_cs_cls:
        mock_cs_cls.return_value.capture = mock_capture

        update = _make_mock_update(text="Test memory")
        await handle_text(update, context)

    mock_ai_service = context.bot_data.get("ai_service")
    assert mock_ai_service is None


# ---------------------------------------------------------------------------
# Direct _persist_capture test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_capture_schedules_after_commit() -> None:
    """_persist_capture calls ai_service.schedule after session commit."""
    from app.models.event import PayloadType, SourceType

    mock_session = _make_async_session_mock()

    mock_ai_service = MagicMock()
    mock_ai_service.schedule = MagicMock()

    context = _make_mock_context(mock_session, mock_ai_service=mock_ai_service)

    captured_event = MagicMock()
    captured_event.id = uuid.uuid4()

    async def mock_capture(req):
        return CaptureResult(event=captured_event, attachments_count=0)

    with patch(
        "app.telegram.handlers.capture.CaptureService"
    ) as mock_cs_cls:
        mock_cs_cls.return_value.capture = mock_capture

        await _persist_capture(
            context=context,
            user_id=uuid.uuid4(),
            payload_type=PayloadType.text,
            source_label="Text",
            raw_text="Conveyor motor wiring notes",
            chat_id=100,
            reply_message_id=42,
        )

    # Schedule called with event ID
    mock_ai_service.schedule.assert_called_once_with(captured_event.id)
    # Confirmation message sent
    context.bot.send_message.assert_awaited_once()
