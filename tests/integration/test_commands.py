"""Integration tests for Telegram bot commands (/insights, /today, /timeline)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update
from telegram.ext import ContextTypes

from app.models.event import Event, PayloadType, ProcessingStatus, SourceType
from app.models.user import User
from app.telegram.handlers.commands import handle_insights, handle_today


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


def _make_mock_context(mock_session: MagicMock) -> MagicMock:
    """Build a mock PTB context with bot_data wired for command handlers."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    mock_session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()

    context.bot_data = {
        "session_factory": mock_session_factory,
        "storage_provider": AsyncMock(),
        "ai_service": MagicMock(),
    }

    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()

    return context


def _make_mock_update() -> MagicMock:
    """Build a mock Update object matching the handler's access patterns."""
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock()
    update.effective_user.id = 123456789

    message = MagicMock()
    message.message_id = 42
    message.chat_id = 100
    message.date = datetime.now(timezone.utc)
    message.reply_text = AsyncMock()
    message.text = None
    message.caption = None
    update.effective_message = message

    return update


def _make_event_with_ai(
    *,
    raw_text: str = "Raw memory",
    ai_analysis: dict | None = None,
) -> Event:
    """Build an Event ORM instance with optional AI analysis."""
    return Event(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        event_date=date.today(),
        captured_at=datetime.now(timezone.utc),
        source_type=SourceType.telegram,
        payload_type=PayloadType.text,
        raw_text=raw_text,
        status=ProcessingStatus.processed,
        payload_metadata=None,
        ai_analysis=ai_analysis,
        is_deleted=False,
        attachments=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# /insights
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insights_shows_ai_analysis() -> None:
    """When events have AI analysis, /insights displays them."""
    user = _make_mock_user()
    event = _make_event_with_ai(
        raw_text="Debugged a conveyor motor today.",
        ai_analysis={
            "summary": "Debugged conveyor motor starter.",
            "activities": ["motor wiring"],
            "skills": ["electrical"],
            "tools": ["multimeter"],
            "problems": ["starter tripping"],
            "solutions": ["replaced overload relay"],
            "lessons": ["always verify voltage first"],
            "entities": ["motor", "starter"],
            "confidence": 0.85,
        },
    )

    mock_session = MagicMock()
    mock_session.execute = MagicMock()
    mock_session.execute.return_value.scalars = MagicMock(return_value=MagicMock(
        all=AsyncMock(return_value=[event])
    ))

    context = _make_mock_context(mock_session)
    update = _make_mock_update()

    with patch(
        "app.telegram.handlers.commands.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ), patch(
        "app.telegram.handlers.commands.EventRepository"
    ) as mock_repo_cls:
        mock_repo_inst = MagicMock()
        mock_repo_inst.find_by_user_id = AsyncMock(return_value=[event])
        mock_repo_cls.return_value = mock_repo_inst

        await handle_insights(update, context)

    # Verify reply was sent with insights content
    update.effective_message.reply_text.assert_awaited_once()
    sent_text = update.effective_message.reply_text.call_args[0][0]
    assert "Your Insights" in sent_text
    assert "motor wiring" in sent_text
    assert "electrical" in sent_text


@pytest.mark.asyncio
async def test_insights_empty_state() -> None:
    """When no AI-analyzed events exist, /insights shows guidance."""
    user = _make_mock_user()
    event = _make_event_with_ai(ai_analysis=None)

    mock_session = MagicMock()
    context = _make_mock_context(mock_session)
    update = _make_mock_update()

    with patch(
        "app.telegram.handlers.commands.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ), patch(
        "app.telegram.handlers.commands.EventRepository"
    ) as mock_repo_cls:
        mock_repo_inst = MagicMock()
        mock_repo_inst.find_by_user_id = AsyncMock(return_value=[event])
        mock_repo_cls.return_value = mock_repo_inst

        await handle_insights(update, context)

    sent_text = update.effective_message.reply_text.call_args[0][0]
    assert "No AI-processed insights yet" in sent_text


@pytest.mark.asyncio
async def test_insights_no_events_at_all() -> None:
    """When no events exist at all, /insights shows empty state."""
    user = _make_mock_user()

    mock_session = MagicMock()
    context = _make_mock_context(mock_session)
    update = _make_mock_update()

    with patch(
        "app.telegram.handlers.commands.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ), patch(
        "app.telegram.handlers.commands.EventRepository"
    ) as mock_repo_cls:
        mock_repo_inst = MagicMock()
        mock_repo_inst.find_by_user_id = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo_inst

        await handle_insights(update, context)

    sent_text = update.effective_message.reply_text.call_args[0][0]
    assert "No AI-processed insights yet" in sent_text


# ---------------------------------------------------------------------------
# /today
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_today_shows_events() -> None:
    """/today lists events for the current day."""
    user = _make_mock_user()
    event = _make_event_with_ai(
        raw_text="Wired the conveyor motor",
        ai_analysis={"summary": "Motor wiring"},
    )

    mock_session = MagicMock()
    context = _make_mock_context(mock_session)
    update = _make_mock_update()

    with patch(
        "app.telegram.handlers.commands.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ), patch(
        "app.telegram.handlers.commands.EventRepository"
    ) as mock_repo_cls:
        mock_repo_inst = MagicMock()
        mock_repo_inst.find_by_user_and_date = AsyncMock(return_value=[event])
        mock_repo_cls.return_value = mock_repo_inst

        await handle_today(update, context)

    sent_text = update.effective_message.reply_text.call_args[0][0]
    assert "Today's Memories" in sent_text
    assert "Wired the conveyor motor" in sent_text


@pytest.mark.asyncio
async def test_today_empty_state() -> None:
    """/today shows empty state when no events captured today."""
    user = _make_mock_user()

    mock_session = MagicMock()
    context = _make_mock_context(mock_session)
    update = _make_mock_update()

    with patch(
        "app.telegram.handlers.commands.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ), patch(
        "app.telegram.handlers.commands.EventRepository"
    ) as mock_repo_cls:
        mock_repo_inst = MagicMock()
        mock_repo_inst.find_by_user_and_date = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo_inst

        await handle_today(update, context)

    sent_text = update.effective_message.reply_text.call_args[0][0]
    assert "No memories captured today" in sent_text
