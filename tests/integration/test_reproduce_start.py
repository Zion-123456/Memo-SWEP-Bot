"""Reproduction test for existing-user /start showing dashboard."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.user import User
from app.telegram.handlers.start import handle_start


def _make_mock_user() -> User:
    return User(
        id=uuid.uuid4(),
        telegram_id=5499527319,
        first_name="Zion",
        last_name=None,
        username=None,
        university="Covenant University",
        department="Electrical and Electronics Engineering",
        programme="Electrical Engineering",
        company="Shell",
        supervisor=None,
        start_date=date(2025, 6, 1),
        end_date=date(2025, 9, 1),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_message_update() -> MagicMock:
    """Create a mock Update simulating a /start command message."""
    update = MagicMock(
        spec=["callback_query", "effective_user", "effective_message", "message"]
    )
    update.callback_query = None

    update.effective_user = MagicMock()
    update.effective_user.id = 5499527319
    update.effective_user.first_name = "Zion"
    update.effective_user.last_name = None
    update.effective_user.username = None

    # Use the same mock for both message and effective_message
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    update.effective_message = msg
    update.message = msg

    return update


def _make_mock_context() -> MagicMock:
    context = MagicMock(spec=["bot_data", "bot", "user_data"])
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()

    mock_session_factory = MagicMock(return_value=mock_session)
    context.bot_data = {
        "session_factory": mock_session_factory,
    }
    context.bot = MagicMock()
    context.user_data = {}
    return context


@pytest.mark.asyncio
async def test_existing_user_start_shows_dashboard() -> None:
    """Existing user /start should call show_dashboard without error."""
    update = _make_message_update()
    context = _make_mock_context()

    mock_user = _make_mock_user()

    with patch(
        "app.telegram.handlers.start.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=mock_user,
    ):
        await handle_start(update, context)

    # Should have sent the welcome message
    update.message.reply_text.assert_awaited()
    first_call_text = update.message.reply_text.call_args_list[0][0][0]
    assert "Welcome back" in first_call_text

    # Should have sent the dashboard (second reply_text call)
    assert update.message.reply_text.call_count >= 2

    # Check the dashboard message contains the keyboard
    second_call_kwargs = update.message.reply_text.call_args_list[1][1]
    assert "MarkdownV2" in str(second_call_kwargs.get("parse_mode", ""))
    markup = second_call_kwargs.get("reply_markup")
    if hasattr(markup, "inline_keyboard"):
        button_texts = [btn.text for row in markup.inline_keyboard for btn in row]
        assert any("Capture Memory" in t for t in button_texts)
        assert any("My Memories" in t for t in button_texts)
        assert any("Insights" in t for t in button_texts)
        assert any("Today" in t for t in button_texts)
        assert any("Progress" in t for t in button_texts)
        assert any("Profile" in t for t in button_texts)
        assert any("Help" in t for t in button_texts)
