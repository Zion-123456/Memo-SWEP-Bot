"""Telegram bot command handlers (/today, /timeline, /delete, /help)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.repositories.event import EventRepository
from app.repositories.user import UserRepository
from app.telegram.handlers.dashboard import show_dashboard

logger = structlog.get_logger(__name__)


async def _get_user_or_reply_error(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Any | None:
    """Helper to verify user is onboarded."""
    if not update.effective_user or not update.effective_message:
        return None

    session_factory = context.bot_data.get("session_factory")
    if not session_factory:
        return None

    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.find_by_telegram_id(update.effective_user.id)
        if not user:
            await update.effective_message.reply_text(
                "⚠️ You need to complete onboarding first before using commands. Send /start to begin."
            )
            return None
        return user


async def handle_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /today command — list today's captured memories."""
    user = await _get_user_or_reply_error(update, context)
    if not user or not update.effective_message:
        return

    today = date.today()
    session_factory = context.bot_data["session_factory"]

    async with session_factory() as session:
        event_repo = EventRepository(session)
        events = await event_repo.find_by_user_and_date(user.id, today)

        if not events:
            await update.effective_message.reply_text(
                f"📅 **Today's Memories ({today.strftime('%d %b %Y')})**\n\n"
                "No memories captured today yet. Send a message, voice note, photo, or document to capture your day!"
            )
            return

        lines = [
            f"📅 **Today's Memories ({today.strftime('%d %b %Y')})** — {len(events)} item(s):",
            "",
        ]
        for idx, evt in enumerate(events, 1):
            att_info = (
                f" ({len(evt.attachments)} attachment(s))" if evt.attachments else ""
            )
            text_preview = f' "{evt.raw_text}"' if evt.raw_text else ""
            lines.append(
                f"{idx}. [{evt.payload_type.value.upper()}]{att_info}{text_preview}"
            )
            lines.append(f"   ID: `{evt.id}`")
            lines.append("")

        lines.append("Use `/delete <event_id>` to remove a memory.")
        await update.effective_message.reply_text(
            "\n".join(lines), parse_mode="Markdown"
        )


async def handle_insights(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /insights command — show AI-extracted insights from recent memories."""
    user = await _get_user_or_reply_error(update, context)
    if not user or not update.effective_message:
        return

    session_factory = context.bot_data["session_factory"]
    async with session_factory() as session:
        event_repo = EventRepository(session)
        events = await event_repo.find_by_user_id(user.id, limit=50)
        analyzed = [e for e in events if e.ai_analysis]

        if not analyzed:
            await update.effective_message.reply_text(
                "🔍 **Your Insights**\n\n"
                "No AI-processed insights yet. Capture some memories first — "
                "the AI will extract skills, tools, problems, and solutions from your notes!\n"
                "Processing happens in the background after you save a memory."
            )
            return

        lines = ["🔍 **Your Insights** — AI-extracted from your memories:", ""]

        for evt in analyzed:
            analysis = evt.ai_analysis or {}
            summary = analysis.get("summary")
            created = (
                evt.event_date.strftime("%d %b %Y") if evt.event_date else "unknown"
            )

            if summary:
                lines.append(f"📅 **{created}** — *{summary}*\n")
            else:
                lines.append(f"📅 **{created}**")

            for field in (
                "activities",
                "skills",
                "tools",
                "problems",
                "solutions",
                "lessons",
            ):
                items = analysis.get(field) or []
                if items:
                    emoji_map = {
                        "activities": "🔧",
                        "skills": "⚡",
                        "tools": "🛠️",
                        "problems": "⚠️",
                        "solutions": "✅",
                        "lessons": "💡",
                    }
                    emoji = emoji_map.get(field, "•")
                    items_str = ", ".join(str(i) for i in items)
                    lines.append(f"  {emoji} **{field.title()}**: {items_str}")

            confidence = analysis.get("confidence")
            if confidence is not None:
                lines.append(f"  _confidence: {confidence:.0%}_")
            lines.append("")

        lines.append("Keep capturing to build more insights over time!")
        await update.effective_message.reply_text(
            "\n".join(lines), parse_mode="Markdown"
        )


async def handle_timeline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /timeline command — list recent memories grouped by day (last 7 days)."""
    user = await _get_user_or_reply_error(update, context)
    if not user or not update.effective_message:
        return

    today = date.today()
    start_date = today - timedelta(days=7)
    session_factory = context.bot_data["session_factory"]

    async with session_factory() as session:
        event_repo = EventRepository(session)
        events = await event_repo.find_by_user_date_range(user.id, start_date, today)

        if not events:
            await update.effective_message.reply_text(
                "📜 **Timeline (Last 7 Days)**\n\nNo memories captured in the last 7 days."
            )
            return

        # Group by date
        grouped: dict[date, list[Any]] = {}
        for evt in events:
            grouped.setdefault(evt.event_date, []).append(evt)

        lines = ["📜 **Timeline (Recent Memories)**", ""]
        for dt in sorted(grouped.keys(), reverse=True):
            day_events = grouped[dt]
            lines.append(
                f"📅 **{dt.strftime('%A, %d %b %Y')}** ({len(day_events)} items):"
            )
            for evt in day_events:
                att_info = f" [{len(evt.attachments)} files]" if evt.attachments else ""
                preview = (
                    f" - {evt.raw_text[:40]}..."
                    if evt.raw_text and len(evt.raw_text) > 40
                    else f" - {evt.raw_text}" if evt.raw_text else ""
                )
                lines.append(
                    f"  • `{str(evt.id)[:8]}` [{evt.payload_type.value}]{att_info}{preview}"
                )
            lines.append("")

        lines.append("Use `/delete <event_id>` to remove a memory.")
        await update.effective_message.reply_text(
            "\n".join(lines), parse_mode="Markdown"
        )


async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delete <event_id> command."""
    user = await _get_user_or_reply_error(update, context)
    if not user or not update.effective_message:
        return

    if not context.args or len(context.args) < 1:
        await update.effective_message.reply_text(
            "Usage: `/delete <event_id>`\nExample: `/delete 123e4567-e89b-12d3-a456-426614174000`",
            parse_mode="Markdown",
        )
        return

    raw_id = context.args[0].strip()
    try:
        event_id = uuid.UUID(raw_id)
    except ValueError:
        await update.effective_message.reply_text(
            "⚠️ Invalid UUID format. Please check the event ID."
        )
        return

    session_factory = context.bot_data["session_factory"]
    async with session_factory() as session:
        event_repo = EventRepository(session)
        event = await event_repo.get_by_id(event_id)

        if not event or event.user_id != user.id:
            await update.effective_message.reply_text(
                "⚠️ Memory not found or access denied."
            )
            return

        success = await event_repo.soft_delete(event_id)
        await session.commit()

        if success:
            await update.effective_message.reply_text(
                f"🗑️ Memory `{event_id}` has been deleted.", parse_mode="Markdown"
            )
        else:
            await update.effective_message.reply_text("⚠️ Memory was already deleted.")


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command — display available commands and usage guide."""
    if not update.effective_message:
        return

    help_text = (
        "💡 **Memo — AI Memory Operating System**\n\n"
        "Just type or send media anytime to log your SWEP day!\n\n"
        "**Supported Inputs:**\n"
        "• 💬 **Text**: Type any update or notes.\n"
        "• 🎙️ **Voice Notes**: Speak your log hands-free.\n"
        "• 📷 **Photos**: Snap diagrams, machines, or work sheets.\n"
        "• 📄 **Documents**: Upload PDFs, DOCX, or manuals.\n\n"
        "**Bot Commands:**\n"
        "• `/menu` — Open the interactive dashboard.\n"
        "• `/today` — View all memories captured today.\n"
        "• `/timeline` — View recent memories grouped by day.\n"
        "• `/insights` — View AI-extracted insights (skills, tools, problems).\n"
        "• `/delete <id>` — Delete a captured memory.\n"
        "• `/start` — Re-run the onboarding configuration.\n"
        "• `/help` — Display this guide."
    )
    await update.effective_message.reply_text(help_text, parse_mode="Markdown")


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /menu command — return the dashboard."""
    await show_dashboard(update, context)


def register_command_handlers(app: Any) -> None:
    """Register bot commands on the Telegram Application."""
    app.add_handler(CommandHandler("today", handle_today))
    app.add_handler(CommandHandler("timeline", handle_timeline))
    app.add_handler(CommandHandler("insights", handle_insights))
    app.add_handler(CommandHandler("delete", handle_delete))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("menu", handle_menu))
