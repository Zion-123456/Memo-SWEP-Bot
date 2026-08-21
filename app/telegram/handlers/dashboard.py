"""Telegram Mini Dashboard handlers (Sprint 3.1).

Provides a button-driven dashboard that lets users navigate Memo's
capabilities without remembering commands. Each button handler delegates
to existing services — no business logic is duplicated.

Architecture:
    • All DB access goes through repository/service layer (thin handlers).
    • Dashboard is delivered via inline keyboard for clean, stateless UX.
    • ``/menu`` always returns the dashboard.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram import InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from app.models.event import Event
from app.models.user import User
from app.repositories.event import EventRepository
from app.repositories.user import UserRepository
from app.services.progress import ProgressService
from app.telegram.keyboards.dashboard import (
    DASHBOARD_ASK,
    DASHBOARD_CAPTURE,
    DASHBOARD_GROWTH,
    DASHBOARD_HELP,
    DASHBOARD_INSIGHTS,
    DASHBOARD_MEMORIES,
    DASHBOARD_PROFILE,
    DASHBOARD_PROGRESS,
    DASHBOARD_TODAY,
    DASHBOARD_WEEKLY,
    build_capture_button_keyboard,
    build_dashboard_keyboard,
)
from app.repositories.knowledge_topic import KnowledgeTopicRepository
from app.repositories.memory_connection import MemoryConnectionRepository
from app.repositories.weekly_reflection import WeeklyReflectionRepository
from app.services.progress_narrative import ProgressNarrativeService
from app.services.weekly_reflection import WeeklyReflectionService

logger = logging.getLogger(__name__)

_DATE_FORMAT = "%d %b %Y"

_PAYLOAD_EMOJI: dict[str, str] = {
    "text": "\U0001f4ac",
    "voice": "\U0001f399\ufe0f",
    "photo": "\U0001f4f8",
    "document": "\U0001f4ce",
}


def _escape_md(text: str) -> str:
    """Escape Telegram MarkdownV2 special characters in user-generated content."""
    if not text:
        return ""
    escape_chars = r"\_*[]()~`>#+-=|{}.!"
    result = ""
    for char in text:
        if char in escape_chars:
            result += f"\\{char}"
        else:
            result += char
    return result


def _b(text: str) -> str:
    """Escape text and wrap in MarkdownV2 bold."""
    return f"*{_escape_md(text)}*"


def _i(text: str) -> str:
    """Escape text and wrap in MarkdownV2 italic."""
    return f"_{_escape_md(text)}_"


# ---------------------------------------------------------------------------
# Static message text constants (plain text, will be escaped when wrapped)
# ---------------------------------------------------------------------------

_WELCOME_DASHBOARD = (
    "I'm here to help you capture, remember, and understand your journey."
)
_WELCOME_DASHBOARD_PROMPT = "What would you like to do?"

_CAPTURE_TITLE = "What happened today?"
_CAPTURE_BODY = "You can:"
_CAPTURE_HINT = "Don't worry about formatting. Just tell Memo what happened."

_MEMORIES_TITLE = "\U0001f4d6 Your Memories"
_MEMORIES_EMPTY = "You haven't captured any memories yet."
_MEMORIES_EMPTY_HINT = "Tell Memo what happened today and I'll remember it for you."

_INSIGHTS_TITLE = "\U0001f9e0 Your Insights"
_INSIGHTS_EMPTY = "No AI-processed insights yet."
_INSIGHTS_EMPTY_HINT = (
    "Capture some memories, and the AI will extract skills, tools, "
    "problems, and solutions from your notes!"
)
_INSIGHTS_HEADER = "AI-extracted from your memories:"
_INSIGHTS_FOOTER = "Keep capturing to build more insights over time!"

_TODAY_TITLE = "\U0001f4c5 Today's Journey"
_TODAY_EMPTY = "Nothing captured today yet."
_TODAY_QUESTION = "What have you learned, done, noticed, or struggled with?"

_PROGRESS_TITLE = "\U0001f4ca Your Memo Progress"
_PROGRESS_NO_STREAK = "No active streak yet. Start capturing!"

_PROFILE_TITLE = "\u2699\ufe0f My Profile"
_PROFILE_NAME = "Name"
_PROFILE_UNIVERSITY = "University"
_PROFILE_DEPARTMENT = "Department"
_PROFILE_PROGRAMME = "Programme"
_PROFILE_COMPANY = "SWEP Company"
_PROFILE_DATES = "SWEP Dates"
_PROFILE_EDITING = (
    "Editing is not yet available. Contact support to update your profile."
)

_HELP_TITLE = "\u2753 Help"
_HELP_JOURNEY = "Memo helps you capture and remember your journey."
_HELP_SEND = "You can send:"
_HELP_SAVE = (
    "Memo saves them and uses AI to organise what you've experienced " "and learned."
)
_HELP_COMMANDS = "Commands for power users:"
_HELP_START = "/start - Re-run onboarding"
_HELP_TODAY = "/today - View today's memories"
_HELP_TIMELINE = "/timeline - View recent memories"
_HELP_INSIGHTS = "/insights - AI-extracted insights"
_HELP_DELETE = "/delete <id> - Delete a memory"
_HELP_MENU = "/menu - Return to dashboard"
_HELP_HELP = "/help - This guide"

_NO_ONBOARDING = (
    "\u26a0\ufe0f You need to complete onboarding first. Send /start to begin."
)

_ASK_TITLE = "\U0001f4ac Ask Memo"
_ASK_INTRO = (
    "You can ask me things like:\n\n"
    "\u2022 What did I learn this week?\n"
    "\u2022 How have I progressed?\n"
    "\u2022 What skills am I developing?\n"
    "\u2022 What did I work on yesterday?\n"
    "\u2022 What have I learned about drilling?\n"
    "\u2022 What should I improve?"
)


# ---------------------------------------------------------------------------
# Helper: safe access to required objects from context
# ---------------------------------------------------------------------------


def _get_session_factory(
    context: ContextTypes.DEFAULT_TYPE,
) -> async_sessionmaker[AsyncSession]:
    return context.bot_data["session_factory"]  # type: ignore[no-any-return]


async def _resolve_user(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> User | None:
    """Resolve the current Telegram user or prompt them to onboard."""
    if not update.effective_user:
        return None
    session_factory = _get_session_factory(context)
    async with session_factory() as session:
        user_repo = UserRepository(session)
        return await user_repo.find_by_telegram_id(update.effective_user.id)


async def _ensure_user(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> User | None:
    """Resolve user or send an onboarding prompt. Returns None if not onboarded."""
    user = await _resolve_user(update, context)
    if user is None:
        msg = _NO_ONBOARDING
        if update.callback_query:
            await _reply_or_edit(update, msg, build_dashboard_keyboard())
        elif update.effective_message:
            await update.effective_message.reply_text(
                msg,
                reply_markup=ReplyKeyboardRemove(),
            )
        return None
    return user


async def _reply_or_edit(
    update: Update,
    text: str,
    reply_markup: object,
) -> None:
    """Send a new message or edit an existing callback-query message."""
    if update.callback_query:
        from telegram.error import BadRequest
        try:
            await update.callback_query.answer()
        except BadRequest as exc:
            import structlog
            structlog.get_logger(__name__).warning("callback.answer_failed", error=str(exc))
        edit_kb = (
            reply_markup if isinstance(reply_markup, InlineKeyboardMarkup) else None
        )
        await update.callback_query.edit_message_text(
            text,
            reply_markup=edit_kb,
            parse_mode="MarkdownV2",
        )
    elif update.effective_message:
        await update.effective_message.reply_text(
            text,
            reply_markup=reply_markup,  # type: ignore[arg-type]
            parse_mode="MarkdownV2",
        )


# ---------------------------------------------------------------------------
# 1. Main Dashboard
# ---------------------------------------------------------------------------


async def show_dashboard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    first_name: str | None = None,
) -> None:
    """Render the main dashboard welcome message with the navigation keyboard."""
    if first_name is None:
        first_name = update.effective_user.first_name if update.effective_user else None

    name = _escape_md(first_name or "there")
    header = (
        f"\U0001f9e0 {_b('Memo')}\n\n"
        f"Hey {name} \U0001f44b\n\n"
        f"{_i(_WELCOME_DASHBOARD)}\n\n"
        f"{_i(_WELCOME_DASHBOARD_PROMPT)}"
    )
    await _reply_or_edit(update, header, build_dashboard_keyboard())


# ---------------------------------------------------------------------------
# 2. Capture Memory
# ---------------------------------------------------------------------------


_CAPTURE_MSG = (
    f"{_b(_CAPTURE_TITLE)}\n\n"
    f"{_i(_CAPTURE_BODY)}\n"
    "• Type what happened\n"
    "• Send a voice note\n"
    "• Send a photo\n"
    "• Send a document\n\n"
    f"{_i(_CAPTURE_HINT)}"
)


async def handle_dashboard_capture(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show capture instructions; existing capture pipeline handles content."""
    user = await _ensure_user(update, context)
    if user is None:
        return
    await _reply_or_edit(update, _CAPTURE_MSG, ReplyKeyboardRemove())


# ---------------------------------------------------------------------------
# 3. My Memories
# ---------------------------------------------------------------------------


async def handle_dashboard_memories(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show memories grouped by date (reuse existing timeline/event services)."""
    user = await _ensure_user(update, context)
    if user is None:
        return

    session_factory = _get_session_factory(context)
    async with session_factory() as session:
        event_repo = EventRepository(session)
        events = await event_repo.find_by_user_id(user.id, limit=100)

        if not events:
            text = (
                f"{_i(_MEMORIES_TITLE)}\n\n"
                f"{_i(_MEMORIES_EMPTY)}\n\n"
                f"{_i(_MEMORIES_EMPTY_HINT)}"
            )
            await _reply_or_edit(update, text, build_capture_button_keyboard())
            return

        grouped: dict[date, list[Event]] = {}
        for evt in events:
            grouped.setdefault(evt.event_date, []).append(evt)

        lines = [_i(_MEMORIES_TITLE), ""]
        for dt in sorted(grouped.keys(), reverse=True):
            lines.append(f"{_b(dt.strftime(_DATE_FORMAT))}")
            for idx, evt in enumerate(grouped[dt], 1):
                emoji = _PAYLOAD_EMOJI.get(evt.payload_type.value, "\U0001f4cf")
                raw = evt.raw_text or ""
                preview = raw[:80] + "..." if len(raw) > 80 else raw
                safe = _escape_md(preview)
                att = len(evt.attachments)
                att_info = f" \U0001f4ce{att}" if att else ""
                safe_val = safe or _escape_md(evt.payload_type.value)
                lines.append(f"{idx}\\. {emoji} _{safe_val}{att_info}_")
            lines.append("")

        await _reply_or_edit(update, "\n".join(lines), build_capture_button_keyboard())


# ---------------------------------------------------------------------------
# 4. My Insights
# ---------------------------------------------------------------------------


_INSIGHT_FIELDS = (
    "activities",
    "skills",
    "tools",
    "problems",
    "solutions",
    "lessons",
)
_INSIGHT_EMOJI = {
    "activities": "\U0001f527",
    "skills": "\u26a1",
    "tools": "\U0001f6e0\ufe0f",
    "problems": "\u26a0\ufe0f",
    "solutions": "\u2705",
    "lessons": "\U0001f4a1",
}


async def handle_dashboard_insights(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show AI-extracted insights from analysed memories (reuse existing logic)."""
    user = await _ensure_user(update, context)
    if user is None:
        return

    session_factory = _get_session_factory(context)
    async with session_factory() as session:
        event_repo = EventRepository(session)
        events = await event_repo.find_by_user_id(user.id, limit=50)
        analyzed = [e for e in events if e.ai_analysis]

        if not analyzed:
            text = (
                f"\U0001f9e0 {_b(_INSIGHTS_TITLE)}\n\n"
                f"{_i(_INSIGHTS_EMPTY)}\n\n"
                f"{_i(_INSIGHTS_EMPTY_HINT)}"
            )
            await _reply_or_edit(update, text, build_capture_button_keyboard())
            return

        lines = [
            f"\U0001f9e0 {_b(_INSIGHTS_TITLE)}",
            f"{_b(_i(_INSIGHTS_HEADER))}",
            "",
        ]
        for evt in analyzed:
            analysis = evt.ai_analysis or {}
            summary = analysis.get("summary")
            created = (
                evt.event_date.strftime(_DATE_FORMAT) if evt.event_date else "unknown"
            )
            date_str = _escape_md(created)

            if summary:
                lines.append(f"{_b(date_str)} \u2014 {_i(_escape_md(str(summary)))}")
            else:
                lines.append(f"{_b(date_str)}")

            for field_name in _INSIGHT_FIELDS:
                items = analysis.get(field_name) or []
                if items:
                    emoji = _INSIGHT_EMOJI.get(field_name, "•")
                    items_str = ", ".join(_escape_md(str(i)) for i in items)
                    label = _b(field_name.title())
                    lines.append(f"  {emoji} {label}: {items_str}")

            confidence = analysis.get("confidence")
            if confidence is not None:
                lines.append(f"  {_i(f'confidence: {float(confidence):.0%}')}")
            lines.append("")

        lines.append(f"{_i(_INSIGHTS_FOOTER)}")
        await _reply_or_edit(update, "\n".join(lines), build_capture_button_keyboard())


# ---------------------------------------------------------------------------
# 5. Today's Journey
# ---------------------------------------------------------------------------


async def handle_dashboard_today(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show today's captured memories (reuse existing /today logic)."""
    user = await _ensure_user(update, context)
    if user is None:
        return

    today = date.today()
    session_factory = _get_session_factory(context)
    async with session_factory() as session:
        event_repo = EventRepository(session)
        events = await event_repo.find_by_user_and_date(user.id, today)

        if not events:
            text = (
                f"{_b(_TODAY_TITLE)}\n\n"
                f"{_i(_TODAY_EMPTY)}\n\n"
                f"{_i(_TODAY_QUESTION)}"
            )
            await _reply_or_edit(update, text, build_capture_button_keyboard())
            return

        lines = [
            f"{_b(_TODAY_TITLE + ' (' + today.strftime(_DATE_FORMAT) + ')')}",
            "",
        ]
        plural = "y" if len(events) == 1 else "ies"
        today_msg = f"You've captured {len(events)} memory{plural} today."
        lines.append(f"{_i(today_msg)}")
        lines.append("")
        for idx, evt in enumerate(events, 1):
            emoji = _PAYLOAD_EMOJI.get(evt.payload_type.value, "\U0001f4cf")
            raw = evt.raw_text or ""
            safe = _escape_md(raw[:50])
            lines.append(
                f"{idx}\\. {emoji} _{safe or _escape_md(evt.payload_type.value)}_"
            )
            lines.append("")

        await _reply_or_edit(update, "\n".join(lines), build_capture_button_keyboard())


# ---------------------------------------------------------------------------
# 6b. My Growth
# ---------------------------------------------------------------------------

_GROWTH_TITLE = "\U0001f4c8 My Growth"
_GROWTH_EMPTY = "No growth topics identified yet."
_GROWTH_EMPTY_HINT = (
    "Capture a few related memories and Memo will identify what you're "
    "learning over time."
)


async def handle_dashboard_growth(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show the user's evolving knowledge topics."""
    user = await _ensure_user(update, context)
    if user is None:
        return

    session_factory = _get_session_factory(context)
    async with session_factory() as session:
        topic_repo = KnowledgeTopicRepository(session)
        topics = await topic_repo.find_by_user_id(user.id)

        if not topics:
            text = (
                f"{_b(_GROWTH_TITLE)}\n\n"
                f"{_i(_GROWTH_EMPTY)}\n\n"
                f"{_i(_GROWTH_EMPTY_HINT)}"
            )
            await _reply_or_edit(update, text, build_capture_button_keyboard())
            return

        lines = [f"\U0001f4c8 {_b(_GROWTH_TITLE)}", ""]
        for topic in topics[:10]:
            status = _escape_md(topic.status.value.title())
            trend = _escape_md(topic.trend.value.title())
            lines.append(
                f"{_b(_escape_md(topic.topic))} — _{status}_ \U0001f4ca {trend}"
            )
            if topic.progression:
                prog = " → ".join(_escape_md(step) for step in topic.progression[:4])
                lines.append(f"  Progress: _{prog}_")
            for ev in (topic.evidence or [])[:3]:
                summary = _escape_md(str(ev.get("summary", ""))[:80])
                if summary:
                    lines.append(f"  • {summary}")
            lines.append("")

        await _reply_or_edit(update, "\n".join(lines), build_capture_button_keyboard())


# ---------------------------------------------------------------------------
# 6c. Weekly Reflection
# ---------------------------------------------------------------------------

_WEEKLY_TITLE = "\U0001f5d3 Weekly Reflection"


async def handle_dashboard_weekly(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show or generate the user's weekly reflection."""
    user = await _ensure_user(update, context)
    if user is None:
        return

    session_factory = _get_session_factory(context)
    ai_provider = context.bot_data.get("ai_provider")
    async with session_factory() as session:
        service = WeeklyReflectionService(
            EventRepository(session),
            WeeklyReflectionRepository(session),
            ai_provider,
            enabled=ai_provider is not None,
        )
        result = await service.get_or_generate(user.id)
        plain = result.content.to_telegram_text(
            memory_count=result.memory_count,
            active_days=result.active_days,
            document_count=result.document_count,
        )
        await _reply_or_edit(update, _escape_md(plain), build_capture_button_keyboard())


# ---------------------------------------------------------------------------
# 6. My Progress
# ---------------------------------------------------------------------------


async def handle_dashboard_progress(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show user progress metrics computed from real stored data."""
    user = await _ensure_user(update, context)
    if user is None:
        return

    session_factory = _get_session_factory(context)
    async with session_factory() as session:
        event_repo = EventRepository(session)
        progress_service = ProgressService(event_repo)
        summary = await progress_service.get_progress(user.id)

        lines = [f"\U0001f4ca {_b(_PROGRESS_TITLE)}", ""]
        lines.append(f"\U0001f4ac {summary.total_memories} memories")
        lines.append(f"\U0001f4c5 {summary.active_days} active days")
        lines.append(f"\U0001f9e0 {summary.ai_processed} AI-processed memories")
        lines.append(
            f"\U0001f4ce {summary.documents} docs \u00b7 \U0001f4f8"
            f" {summary.photos} photos \u00b7"
            f" \U0001f399\ufe0f {summary.voices} voice"
        )
        lines.append("")
        if summary.streak_days > 0:
            lines.append(f"\U0001f525 {summary.streak_days}\\-day capture streak")
        else:
            lines.append(f"{_i(_PROGRESS_NO_STREAK)}")

        await _reply_or_edit(update, "\n".join(lines), build_capture_button_keyboard())


# ---------------------------------------------------------------------------
# 7. My Profile
# ---------------------------------------------------------------------------


async def handle_dashboard_profile(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show the user's SWEP profile."""
    user = await _ensure_user(update, context)
    if user is None:
        return

    start = user.start_date.strftime(_DATE_FORMAT) if user.start_date else "unknown"
    end = user.end_date.strftime(_DATE_FORMAT) if user.end_date else "unknown"

    lines = [
        f"\u2699\ufe0f {_b(_PROFILE_TITLE)}",
        "",
        f"\U0001f466 {_b(_PROFILE_NAME)}: {_escape_md(user.first_name)}",
        f"\U0001f393 {_b(_PROFILE_UNIVERSITY)}: {_escape_md(user.university)}",
        f"\U0001f3eb {_b(_PROFILE_DEPARTMENT)}: {_escape_md(user.department)}",
        f"\U0001f4da {_b(_PROFILE_PROGRAMME)}: {_escape_md(user.programme)}",
        f"\U0001f3e2 {_b(_PROFILE_COMPANY)}: {_escape_md(user.company)}",
        f"\U0001f4d5 {_b(_PROFILE_DATES)}:"
        f" {_escape_md(start)} \u2192 {_escape_md(end)}",
        "",
        f"{_i(_PROFILE_EDITING)}",
    ]
    await _reply_or_edit(update, "\n".join(lines), build_dashboard_keyboard())


# ---------------------------------------------------------------------------
# 8. Help
# ---------------------------------------------------------------------------


_HELP_TEXT = (
    f"{_b(_HELP_TITLE)}\n\n"
    f"{_i(_HELP_JOURNEY)}\n\n"
    f"{_i(_HELP_SEND)}\n"
    "\U0001f4dd Text\n"
    "\U0001f399\ufe0f Voice notes\n"
    "\U0001f4f8 Photos\n"
    "\U0001f4ce Documents\n\n"
    f"{_i(_HELP_SAVE)}\n\n"
    f"{_b(_i(_HELP_COMMANDS))}\n"
    f"{_HELP_START}\n"
    f"{_HELP_TODAY}\n"
    f"{_HELP_TIMELINE}\n"
    f"{_HELP_INSIGHTS}\n"
    f"{_HELP_DELETE}\n"
    f"{_HELP_MENU}\n"
    f"{_HELP_HELP}"
)


async def handle_dashboard_help(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show help text."""
    user = await _ensure_user(update, context)
    if user is None:
        return
    await _reply_or_edit(update, _HELP_TEXT, build_dashboard_keyboard())


# ---------------------------------------------------------------------------
# 8b. Ask Memo
# ---------------------------------------------------------------------------

_ASK_TEXT = f"{_b(_ASK_TITLE)}\n\n" f"{_i(_ASK_INTRO)}"


async def handle_dashboard_ask(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show the 'Ask Memo' help text."""
    user = await _ensure_user(update, context)
    if user is None:
        return
    await _reply_or_edit(update, _ASK_TEXT, build_dashboard_keyboard())


# ---------------------------------------------------------------------------
# Callback routing and registration
# ---------------------------------------------------------------------------


_DASHBOARD_CALLBACKS: dict[str, Callable[[Update, ContextTypes.DEFAULT_TYPE], Any]] = {
    DASHBOARD_CAPTURE: handle_dashboard_capture,
    DASHBOARD_MEMORIES: handle_dashboard_memories,
    DASHBOARD_INSIGHTS: handle_dashboard_insights,
    DASHBOARD_TODAY: handle_dashboard_today,
    DASHBOARD_PROGRESS: handle_dashboard_progress,
    DASHBOARD_GROWTH: handle_dashboard_growth,
    DASHBOARD_WEEKLY: handle_dashboard_weekly,
    DASHBOARD_PROFILE: handle_dashboard_profile,
    DASHBOARD_ASK: handle_dashboard_ask,
    DASHBOARD_HELP: handle_dashboard_help,
}


async def _dashboard_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route a callback query to the matching dashboard handler."""
    query = update.callback_query
    if not query:
        return
    handler = _DASHBOARD_CALLBACKS.get(query.data or "")
    if handler:
        await handler(update, context)
    else:
        await query.answer("Unknown action.", show_alert=True)


def register_dashboard_handlers(app: Any) -> None:
    """Register the dashboard callback-query handler on the PTB Application."""
    app.add_handler(CallbackQueryHandler(_dashboard_router))
