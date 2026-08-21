"""Integration tests for the Telegram Mini Dashboard (Sprint 3.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.event import Event, PayloadType, ProcessingStatus, SourceType
from app.models.user import User
from app.telegram.handlers.dashboard import (
    _b,
    _i,
    handle_dashboard_capture,
    handle_dashboard_help,
    handle_dashboard_insights,
    handle_dashboard_memories,
    handle_dashboard_profile,
    handle_dashboard_progress,
    handle_dashboard_today,
    show_dashboard,
)
from app.telegram.keyboards.dashboard import (
    DASHBOARD_CAPTURE,
    DASHBOARD_HELP,
    DASHBOARD_INSIGHTS,
    DASHBOARD_MEMORIES,
    DASHBOARD_PROFILE,
    DASHBOARD_PROGRESS,
    DASHBOARD_TODAY,
)

_TZ = UTC


def _make_mock_user() -> User:
    return User(
        id=uuid.uuid4(),
        telegram_id=123456789,
        first_name="Alice",
        last_name=None,
        username="alice",
        university="Tech University",
        department="Engineering",
        programme="Computer Science BSc",
        company="SWEP Ltd",
        supervisor=None,
        start_date=date(2025, 6, 1),
        end_date=date(2025, 9, 1),
        created_at=datetime.now(_TZ),
        updated_at=datetime.now(_TZ),
    )


def _make_mock_context(mock_session: MagicMock) -> MagicMock:
    context = MagicMock(spec=["bot_data", "bot"])
    mock_session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()
    context.bot_data = {
        "session_factory": mock_session_factory,
        "storage_provider": AsyncMock(),
        "ai_service": MagicMock(),
    }
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    return context


def _make_callback_update(data: str) -> MagicMock:
    update = MagicMock(spec=["callback_query", "effective_user", "effective_message"])
    update.effective_user = MagicMock()
    update.effective_user.id = 123456789
    update.effective_message = None

    query = MagicMock(spec=["answer", "edit_message_text", "data"])
    query.data = data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    return update


def _make_text_event(
    *,
    raw_text: str = "Raw memory",
    ai_analysis: dict | None = None,
    payload_type: PayloadType = PayloadType.text,
    created: datetime | None = None,
    offset_days: int = 0,
) -> Event:
    if created is None:
        created = datetime.now(_TZ) - timedelta(days=offset_days)
    return Event(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        event_date=date.today(),
        captured_at=created,
        source_type=SourceType.telegram,
        payload_type=payload_type,
        raw_text=raw_text,
        status=ProcessingStatus.processed if ai_analysis else ProcessingStatus.pending,
        ai_analysis=ai_analysis,
        is_deleted=False,
        attachments=[],
        created_at=created,
        updated_at=created,
    )


def _patch_user_repo(user: User) -> MagicMock:
    patcher = patch(
        "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    )
    return patcher.start()


def _patch_event_repo(events: list[Event]) -> tuple:
    """Patch EventRepository in the dashboard module to return given events."""
    patcher = patch("app.telegram.handlers.dashboard.EventRepository")
    mock_cls = patcher.start()
    mock_inst = MagicMock()
    mock_inst.find_by_user_id = AsyncMock(return_value=events)
    mock_inst.find_by_user_and_date = AsyncMock(return_value=events)
    mock_cls.return_value = mock_inst
    return patcher, mock_inst


# ---------------------------------------------------------------------------
# Dashboard rendering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_shows_main_menu() -> None:
    """show_dashboard sends a message with the navigation keyboard."""
    update = _make_callback_update(DASHBOARD_CAPTURE)
    update.effective_user.first_name = "Alice"
    context = _make_mock_context(MagicMock())
    context.bot_data["ai_service"] = MagicMock()

    with patch(
        "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=_make_mock_user(),
    ):
        await show_dashboard(update, context)

    query = update.callback_query
    query.edit_message_text.assert_awaited_once()
    sent_text = query.edit_message_text.call_args[0][0]
    assert "Memo" in sent_text
    assert "What would you like to do?" in sent_text
    # Check keyboard has all buttons
    markup = query.edit_message_text.call_args[1]["reply_markup"]
    button_texts = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("Capture Memory" in t for t in button_texts)
    assert any("My Memories" in t for t in button_texts)
    assert any("My Insights" in t for t in button_texts)
    assert any("Today" in t for t in button_texts)
    assert any("My Progress" in t for t in button_texts)
    assert any("My Profile" in t for t in button_texts)
    assert any("Help" in t for t in button_texts)


# ---------------------------------------------------------------------------
# /menu (via handle_menu / show_dashboard from commands)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_menu_command_shows_dashboard() -> None:
    """/menu returns the dashboard."""
    from app.telegram.handlers.commands import handle_menu

    update = MagicMock(spec=["callback_query", "effective_user", "effective_message"])
    update.callback_query = None  # /menu is a command, not a callback
    update.effective_user = MagicMock()
    update.effective_user.id = 123456789
    update.effective_user.first_name = "Alice"

    message = MagicMock()
    message.reply_text = AsyncMock()
    update.effective_message = message

    context = _make_mock_context(MagicMock())
    context.bot_data["ai_service"] = MagicMock()

    with patch(
        "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=_make_mock_user(),
    ):
        await handle_menu(update, context)

    message.reply_text.assert_awaited_once()
    sent = message.reply_text.call_args[0][0]
    assert "Memo" in sent
    markup = message.reply_text.call_args[1]["reply_markup"]
    button_texts = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("Capture Memory" in t for t in button_texts)


# ---------------------------------------------------------------------------
# Capture button
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_button_shows_instructions() -> None:
    """Capture Memory button shows capture instructions."""
    update = _make_callback_update(DASHBOARD_CAPTURE)
    context = _make_mock_context(MagicMock())

    with patch(
        "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=_make_mock_user(),
    ):
        await handle_dashboard_capture(update, context)

    query = update.callback_query
    query.edit_message_text.assert_awaited_once()
    sent = query.edit_message_text.call_args[0][0]
    assert "What happened today?" in sent
    assert "voice note" in sent
    assert "photo" in sent
    assert "document" in sent


# ---------------------------------------------------------------------------
# Memories button
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memories_button_shows_events() -> None:
    """📖 My Memories button shows events grouped by date."""
    event = _make_text_event(raw_text="Learned about drilling")
    update = _make_callback_update(DASHBOARD_MEMORIES)
    context = _make_mock_context(MagicMock())

    with (
        patch(
            "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=_make_mock_user(),
        ),
        patch("app.telegram.handlers.dashboard.EventRepository") as mock_repo_cls,
    ):
        mock_repo_inst = MagicMock()
        mock_repo_inst.find_by_user_id = AsyncMock(return_value=[event])
        mock_repo_cls.return_value = mock_repo_inst

        await handle_dashboard_memories(update, context)

    query = update.callback_query
    query.edit_message_text.assert_awaited_once()
    sent = query.edit_message_text.call_args[0][0]
    assert "Your Memories" in sent
    assert "drilling" in sent


@pytest.mark.asyncio
async def test_memories_button_empty_state() -> None:
    """📖 My Memories with no events shows empty-state with capture button."""
    update = _make_callback_update(DASHBOARD_MEMORIES)
    context = _make_mock_context(MagicMock())

    with (
        patch(
            "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=_make_mock_user(),
        ),
        patch("app.telegram.handlers.dashboard.EventRepository") as mock_repo_cls,
    ):
        mock_repo_inst = MagicMock()
        mock_repo_inst.find_by_user_id = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo_inst

        await handle_dashboard_memories(update, context)

    query = update.callback_query
    query.edit_message_text.assert_awaited_once()
    sent = query.edit_message_text.call_args[0][0]
    assert "haven't captured" in sent


# ---------------------------------------------------------------------------
# Insights button
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insights_button_shows_analysis() -> None:
    """🧠 My Insights button shows AI-extracted fields."""
    event = _make_text_event(
        raw_text="Debugged motor",
        ai_analysis={
            "summary": "Motor debugging session",
            "skills": ["electrical"],
            "tools": ["multimeter"],
            "problems": ["starter tripping"],
            "solutions": ["replaced relay"],
            "lessons": ["verify voltage first"],
            "confidence": 0.85,
            "activities": ["wiring"],
        },
    )
    update = _make_callback_update(DASHBOARD_INSIGHTS)
    context = _make_mock_context(MagicMock())

    with (
        patch(
            "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=_make_mock_user(),
        ),
        patch("app.telegram.handlers.dashboard.EventRepository") as mock_repo_cls,
    ):
        mock_repo_inst = MagicMock()
        mock_repo_inst.find_by_user_id = AsyncMock(return_value=[event])
        mock_repo_cls.return_value = mock_repo_inst

        await handle_dashboard_insights(update, context)

    query = update.callback_query
    query.edit_message_text.assert_awaited_once()
    sent = query.edit_message_text.call_args[0][0]
    assert "Your Insights" in sent
    assert "motor debugging" in sent.lower()
    assert "electrical" in sent
    assert "multimeter" in sent
    assert "0.85" not in sent or "85%" in sent  # confidence formatted as percentage


@pytest.mark.asyncio
async def test_insights_formats_no_backslash_n_bug() -> None:
    """Fix: insights must not contain malformed `</n` or bare `<n` artifacts."""
    event = _make_text_event(
        ai_analysis={"summary": "Motor work", "skills": ["mechanical"]},
    )
    update = _make_callback_update(DASHBOARD_INSIGHTS)
    context = _make_mock_context(MagicMock())

    with (
        patch(
            "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=_make_mock_user(),
        ),
        patch("app.telegram.handlers.dashboard.EventRepository") as mock_repo_cls,
    ):
        mock_repo_inst = MagicMock()
        mock_repo_inst.find_by_user_id = AsyncMock(return_value=[event])
        mock_repo_cls.return_value = mock_repo_inst

        await handle_dashboard_insights(update, context)

    sent_text = update.callback_query.edit_message_text.call_args[0][0]
    assert "</n" not in sent_text
    assert "<n" not in sent_text


@pytest.mark.asyncio
async def test_insights_empty_state() -> None:
    """🧠 My Insights with no AI analysis shows empty state."""
    update = _make_callback_update(DASHBOARD_INSIGHTS)
    context = _make_mock_context(MagicMock())

    with (
        patch(
            "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=_make_mock_user(),
        ),
        patch("app.telegram.handlers.dashboard.EventRepository") as mock_repo_cls,
    ):
        mock_repo_inst = MagicMock()
        mock_repo_inst.find_by_user_id = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo_inst

        await handle_dashboard_insights(update, context)

    sent = update.callback_query.edit_message_text.call_args[0][0]
    assert "No AI" in sent
    assert "processed" in sent  # hyphen is escaped in MDv2


# ---------------------------------------------------------------------------
# Today button
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_today_button_shows_todays_events() -> None:
    """📅 Today's Journey button shows today's memories."""
    event = _make_text_event(raw_text="Studied reservoir engineering", offset_days=0)
    update = _make_callback_update(DASHBOARD_TODAY)
    context = _make_mock_context(MagicMock())

    with (
        patch(
            "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=_make_mock_user(),
        ),
        patch("app.telegram.handlers.dashboard.EventRepository") as mock_repo_cls,
    ):
        mock_repo_inst = MagicMock()
        mock_repo_inst.find_by_user_and_date = AsyncMock(return_value=[event])
        mock_repo_cls.return_value = mock_repo_inst

        await handle_dashboard_today(update, context)

    sent = update.callback_query.edit_message_text.call_args[0][0]
    assert "Today's Journey" in sent
    assert "reservoir engineering" in sent


@pytest.mark.asyncio
async def test_today_button_empty_state() -> None:
    """📅 Today's Journey with no events shows empty state with capture button."""
    update = _make_callback_update(DASHBOARD_TODAY)
    context = _make_mock_context(MagicMock())

    with (
        patch(
            "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=_make_mock_user(),
        ),
        patch("app.telegram.handlers.dashboard.EventRepository") as mock_repo_cls,
    ):
        mock_repo_inst = MagicMock()
        mock_repo_inst.find_by_user_and_date = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo_inst

        await handle_dashboard_today(update, context)

    sent = update.callback_query.edit_message_text.call_args[0][0]
    assert "Nothing captured today" in sent


# ---------------------------------------------------------------------------
# Progress button
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_button_shows_metrics() -> None:
    """📊 My Progress button shows real computed metrics."""
    events = [
        _make_text_event(raw_text="Memory 1"),
        _make_text_event(raw_text="Memory 2", ai_analysis={"summary": "ok"}),
        _make_text_event(
            ai_analysis={"summary": "ok"},
            payload_type=PayloadType.document,
            offset_days=0,
        ),
    ]
    update = _make_callback_update(DASHBOARD_PROGRESS)
    context = _make_mock_context(MagicMock())

    with (
        patch(
            "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=_make_mock_user(),
        ),
        patch("app.telegram.handlers.dashboard.EventRepository") as mock_repo_cls,
    ):
        mock_repo_inst = MagicMock()
        mock_repo_inst.list_by_user = AsyncMock(return_value=events)
        mock_repo_cls.return_value = mock_repo_inst

        await handle_dashboard_progress(update, context)

    sent = update.callback_query.edit_message_text.call_args[0][0]
    assert "Your Memo Progress" in sent
    assert "3 memories" in sent
    assert "AI" in sent
    assert "processed" in sent  # "AI-processed" has escaped -


# ---------------------------------------------------------------------------
# Profile button
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_profile_button_shows_user_info() -> None:
    """⚙️ My Profile button shows the user's SWEP profile."""
    user = _make_mock_user()
    update = _make_callback_update(DASHBOARD_PROFILE)
    context = _make_mock_context(MagicMock())

    with (
        patch(
            "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch("app.telegram.handlers.dashboard.EventRepository") as mock_repo_cls,
    ):
        mock_repo_inst = MagicMock()
        mock_repo_cls.return_value = mock_repo_inst

        await handle_dashboard_profile(update, context)

    sent = update.callback_query.edit_message_text.call_args[0][0]
    assert "My Profile" in sent
    assert "Alice" in sent
    assert "Tech University" in sent
    assert "SWEP Ltd" in sent


# ---------------------------------------------------------------------------
# Help button
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_help_button_shows_help_text() -> None:
    """❓ Help button shows help text with commands."""
    update = _make_callback_update(DASHBOARD_HELP)
    context = _make_mock_context(MagicMock())

    with (
        patch(
            "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=_make_mock_user(),
        ),
        patch("app.telegram.handlers.dashboard.EventRepository") as mock_repo_cls,
    ):
        mock_repo_inst = MagicMock()
        mock_repo_cls.return_value = mock_repo_inst

        await handle_dashboard_help(update, context)

    sent = update.callback_query.edit_message_text.call_args[0][0]
    assert "Help" in sent
    assert "/menu" in sent
    assert "/start" in sent
    assert "/today" in sent


# ---------------------------------------------------------------------------
# User isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_user_isolation() -> None:
    """Dashboard only shows the current user's data, not other users'."""
    user_a = _make_mock_user()
    event_a = _make_text_event(raw_text="Alice's secret memory")

    # User A sees only their events
    update_a = _make_callback_update(DASHBOARD_MEMORIES)
    context_a = _make_mock_context(MagicMock())

    with (
        patch(
            "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=user_a,
        ),
        patch("app.telegram.handlers.dashboard.EventRepository") as mock_repo_cls,
    ):
        mock_repo_inst = MagicMock()
        mock_repo_inst.find_by_user_id = AsyncMock(return_value=[event_a])
        mock_repo_cls.return_value = mock_repo_inst

        await handle_dashboard_memories(update_a, context_a)

    sent_a = update_a.callback_query.edit_message_text.call_args[0][0]
    assert "Alice's secret memory" in sent_a
    assert "Bob's secret memory" not in sent_a


# ---------------------------------------------------------------------------
# Unonboarded user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_unonboarded_user_prompted() -> None:
    """Users who haven't completed onboarding are prompted to /start."""
    update = _make_callback_update(DASHBOARD_CAPTURE)
    context = _make_mock_context(MagicMock())

    with patch(
        "app.telegram.handlers.dashboard.UserRepository.find_by_telegram_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await handle_dashboard_capture(update, context)

    query = update.callback_query
    query.edit_message_text.assert_awaited_once()
    sent = query.edit_message_text.call_args[0][0]
    assert "onboarding" in sent.lower()


# ---------------------------------------------------------------------------
# MarkdownV2 regression test
# ---------------------------------------------------------------------------

_MD2_SPECIAL = set(r"\_*[]()~`>#+-=|{}.!")


def _check_no_unescaped_md2(text: str) -> list[str]:
    """Return list of unescaped MarkdownV2 special characters in text.

    A character is 'unescaped' if it is NOT preceded by a backslash AND
    is NOT part of a valid formatting delimiter pair.
    """
    violations: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            i += 2
            continue
        if ch in _MD2_SPECIAL:
            violations.append(ch)
        i += 1
    return violations


@pytest.mark.parametrize(
    "text",
    [
        _i("I'm here to help you capture, remember, and understand your journey."),
        _i("What would you like to do?"),
        _b("Memo"),
        _i("Don't worry about formatting. Just tell Memo what happened."),
        _i("You haven't captured any memories yet."),
        _i("Tell Memo what happened today and I'll remember it for you."),
        _b("Today's Journey"),
        _i("Nothing captured today yet."),
        _i("What have you learned, done, noticed, or struggled with?"),
        _i("No active streak yet. Start capturing!"),
        _b("My Profile"),
        _i("Editing is not yet available. Contact support to update your profile."),
        _b("Help"),
        _i("Memo helps you capture and remember your journey."),
        _i("You can send:"),
        _i("Memo saves them and uses AI to organise what you've experienced and learned."),
        _b(_i("Commands for power users:")),
    ],
)
def test_dashboard_messages_have_no_unescaped_md2(text: str) -> None:
    """Regression: all dashboard messages must escape MarkdownV2 special chars.

    Previously, the dashboard header contained an unescaped '.' inside an
    italic section, causing Telegram to return 400 'can't parse entities'.
    """
    violations = _check_no_unescaped_md2(text)
    # The '_' and '*' chars are intentional formatting delimiters and
    # are allowed to appear unescaped as long as they are paired.
    # We only flag: . ! - > = | { } ( ) [ ] ~ ` # + and backslash
    non_delimiter_special = set(r".!->=|{}()[]~`#+")
    bad = [c for c in violations if c in non_delimiter_special]
    assert not bad, f"Unescaped MarkdownV2 chars in {text!r}: {bad}"
