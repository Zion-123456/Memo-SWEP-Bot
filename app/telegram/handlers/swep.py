"""Fast SWEP historical-reconstruction and daily logbook MVP flow.

The flow is isolated in a ConversationHandler so normal Memo capture remains
untouched when the student is not actively using the SWEP workflow.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from app.swep.context import SwepContext

MENU, AWAITING_DATE, AWAITING_BUILDING, AWAITING_MEMORY, AWAITING_PERSONAL, READY = range(6)
ACTION_RECONSTRUCT = "swep:reconstruct"
ACTION_FILL = "swep:fill"
ACTION_CAPTURE = "swep:capture"
ACTION_EVIDENCE = "swep:evidence"
ACTION_PROGRESS = "swep:progress"
ACTION_NEXT = "swep:next"
ACTION_MENU = "swep:menu"

_PHASE_LABELS = {
    "initial_orientation": "Initial Orientation",
    "department_rotation": "Department Rotation",
    "second_phase_orientation": "Second-Phase Orientation",
    "specialized_project": "Specialized Project",
}


def _ctx() -> SwepContext:
    return SwepContext()


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 Reconstruct Previous SWEP", callback_data=ACTION_RECONSTRUCT)],
        [InlineKeyboardButton("📘 Fill My Logbook", callback_data=ACTION_FILL)],
        [InlineKeyboardButton("➕ Capture Today's Experience", callback_data=ACTION_CAPTURE)],
        [InlineKeyboardButton("📸 Add Evidence", callback_data=ACTION_EVIDENCE)],
        [InlineKeyboardButton("📊 My Progress", callback_data=ACTION_PROGRESS)],
    ])


def _building_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for ident, name in _ctx().building_options():
        row.append(InlineKeyboardButton(name, callback_data=f"swep:building:{ident}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _format_draft(draft: dict[str, Any]) -> str:
    labels = [
        ("activity_description", "📌 Activity / Work Done"),
        ("learning", "🧠 Knowledge / Learning Gained"),
        ("personal_contribution", "👤 My Participation / Experience"),
        ("skills", "🛠 Skills / Competencies Developed"),
        ("reflection", "💭 Personal Takeaway"),
    ]
    lines = ["📘 *Suggested Logbook Entry*", ""]
    for key, label in labels:
        value = str(draft.get(key) or "").strip()
        if value:
            lines.extend([f"*{label}*", value, ""])
    return "\n".join(lines).strip()


def _date_from_text(text: str) -> date | None:
    raw = text.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _flow(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    return context.user_data.setdefault("swep_flow", {})


async def start_swep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["swep_flow"] = {}
    await update.effective_message.reply_text(
        "📘 *Memo SWEP*\n\n"
        "I’ll help you reconstruct past SWEP days, turn your memories into logbook-ready suggestions, and keep the process quick.\n\n"
        "Choose what you want to do:",
        reply_markup=_menu_keyboard(),
        parse_mode="Markdown",
    )
    return MENU


async def begin_reconstruct(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🧠 *Reconstruct Previous SWEP*\n\nWhich date are you trying to fill?\n\nSend it as `DD/MM/YYYY`, e.g. `05/08/2026`.",
        parse_mode="Markdown",
    )
    _flow(context)["mode"] = "reconstruct"
    return AWAITING_DATE


async def begin_fill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📘 *Fill My Logbook*\n\nWhich SWEP date do you want to prepare?\n\nSend `DD/MM/YYYY`.",
        parse_mode="Markdown",
    )
    _flow(context)["mode"] = "fill"
    return AWAITING_DATE


async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    flow = _flow(context)
    if text.lower() == "continue" and flow.get("prefilled_date"):
        day = date.fromisoformat(str(flow["prefilled_date"]))
    else:
        day = _date_from_text(text)
    if not day:
        await update.effective_message.reply_text("Please send the date as `DD/MM/YYYY`.", parse_mode="Markdown")
        return AWAITING_DATE

    phase = _ctx().phase_for_date(day)
    flow.update({"date": day.isoformat(), "phase": phase, "personal_answers": []})
    if phase == "department_rotation":
        await update.effective_message.reply_text(
            f"📅 *{day.strftime('%d %B %Y')}*\n\nThis falls in the *{_PHASE_LABELS[phase]}* phase.\n\n"
            "Which building/department were you in that day? I’ll use the shared SWEP context to help you recover the session.",
            parse_mode="Markdown", reply_markup=_building_keyboard(),
        )
        return AWAITING_BUILDING
    await update.effective_message.reply_text(
        f"📅 *{day.strftime('%d %B %Y')}*\n\nThis falls in the *{_PHASE_LABELS[phase]}* phase.\n\n"
        "Tell me anything you remember from the day — even a short note is enough.",
        parse_mode="Markdown",
    )
    return AWAITING_MEMORY


async def handle_building(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    building_id = (query.data or "").split(":", 2)[-1]
    building = _ctx().get_building(building_id)
    if not building:
        await query.edit_message_text("I couldn't find that building. Please choose again.", reply_markup=_building_keyboard())
        return AWAITING_BUILDING
    _flow(context)["building_id"] = building_id
    await query.edit_message_text(
        f"🏢 *{building.get('building_name')}* selected.\n\n"
        "What do you personally remember from this session? A sentence, keywords, or even “I mostly listened” is enough.",
        parse_mode="Markdown",
    )
    return AWAITING_MEMORY


async def _generate(context: ContextTypes.DEFAULT_TYPE, student_input: str) -> dict[str, Any]:
    provider = context.bot_data.get("ai_provider")
    flow = _flow(context)
    ctx = _ctx()
    building = ctx.get_building(str(flow.get("building_id"))) if flow.get("building_id") else None
    bundle = ctx.prompt_bundle(
        day=str(flow["date"]), phase=str(flow["phase"]), building=building,
        student_input=student_input, personal_answers=list(flow.get("personal_answers", [])),
    )
    if provider is None:
        return {"draft": {"activity_description": student_input, "personal_contribution": student_input}, "question": ""}
    messages = [
        {"role": "system", "content": (
            "You are Memo, a SWEP logbook assistant. Return JSON only with keys draft and question. "
            "draft must contain activity_description, learning, personal_contribution, skills, reflection. "
            "Shared context is NOT proof of personal participation. Never invent actions, equipment use, facilitators, "
            "dates, measurements, results, or experiences. Every first-person claim must be supported by student input "
            "or personal answers. Ask at most one high-value personalization question, or use an empty question when "
            "enough personal information is available. Keep entries concise and suitable for handwriting."
        )},
        {"role": "user", "content": json.dumps(bundle, ensure_ascii=False)},
    ]
    return await provider.generate_json(messages, max_tokens=1400, temperature=0.15)


async def handle_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = _flow(context)
    flow["student_input"] = (update.effective_message.text or "").strip()
    flow.setdefault("personal_answers", [])
    result = await _generate(context, str(flow["student_input"]))
    flow["draft"] = result.get("draft") if isinstance(result.get("draft"), dict) else {}
    question = str(result.get("question") or "").strip()
    if question and len(flow["personal_answers"]) < 3:
        await update.effective_message.reply_text(
            _format_draft(flow["draft"]) + f"\n\n❓ *One quick question:*\n{question}", parse_mode="Markdown"
        )
        return AWAITING_PERSONAL
    return await save_and_show(update, context)


async def handle_personal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = _flow(context)
    flow.setdefault("personal_answers", []).append((update.effective_message.text or "").strip())
    result = await _generate(context, str(flow.get("student_input", "")))
    if isinstance(result.get("draft"), dict):
        flow["draft"] = result["draft"]
    return await save_and_show(update, context)


async def save_and_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = _flow(context)
    entries = context.user_data.setdefault("swep_entries", {})
    entries[str(flow["date"])] = {
        "date": flow["date"], "phase": flow["phase"], "building_id": flow.get("building_id"),
        "student_input": flow.get("student_input", ""), "personal_answers": flow.get("personal_answers", []),
        "draft": flow.get("draft", {}), "saved_at": datetime.utcnow().isoformat(),
    }
    await update.effective_message.reply_text(
        _format_draft(flow.get("draft", {}))
        + "\n\n⚠️ *Review this before writing it into your official logbook.*"
        + "\n\n✅ Saved to Memo.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ Continue to next day", callback_data=ACTION_NEXT)],
            [InlineKeyboardButton("📘 SWEP Menu", callback_data=ACTION_MENU)],
        ]),
    )
    return READY


async def handle_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    flow = _flow(context)
    current = date.fromisoformat(str(flow["date"]))
    next_day = current + timedelta(days=1)
    flow.clear()
    flow.update({"mode": "fill", "prefilled_date": next_day.isoformat()})
    await query.edit_message_text(
        f"➡️ *Next day: {next_day.strftime('%d %B %Y')}*\n\nSend *Continue* to use this date, or send another date.",
        parse_mode="Markdown",
    )
    return AWAITING_DATE


async def handle_capture(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "➕ *Capture Today's Experience*\n\nSend your text, voice note, photo, or document now. Memo's normal capture pipeline will handle it.\n\nUse /swep again when you want the logbook flow.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def handle_evidence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📸 *Add Evidence*\n\nSend a photo or document now. Memo's existing capture system will store it. Evidence-to-logbook linking is a later iteration.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def handle_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    entries = context.user_data.get("swep_entries", {})
    await query.edit_message_text(
        f"📊 *SWEP Progress*\n\nDays prepared: *{len(entries)}*\n\nUse *Fill My Logbook* or *Reconstruct Previous SWEP* to prepare another day.",
        parse_mode="Markdown", reply_markup=_menu_keyboard(),
    )
    return MENU


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📘 *Memo SWEP*\n\nChoose what you want to do:", reply_markup=_menu_keyboard(), parse_mode="Markdown")
    return MENU


async def cancel_swep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("swep_flow", None)
    if update.effective_message:
        await update.effective_message.reply_text("SWEP flow closed. Your normal Memo tools are still available.")
    return ConversationHandler.END


def build_swep_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("swep", start_swep)],
        states={
            MENU: [
                CallbackQueryHandler(begin_reconstruct, pattern=r"^swep:reconstruct$"),
                CallbackQueryHandler(begin_fill, pattern=r"^swep:fill$"),
                CallbackQueryHandler(handle_capture, pattern=r"^swep:capture$"),
                CallbackQueryHandler(handle_evidence, pattern=r"^swep:evidence$"),
                CallbackQueryHandler(handle_progress, pattern=r"^swep:progress$"),
            ],
            AWAITING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date)],
            AWAITING_BUILDING: [CallbackQueryHandler(handle_building, pattern=r"^swep:building:")],
            AWAITING_MEMORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_memory)],
            AWAITING_PERSONAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_personal)],
            READY: [
                CallbackQueryHandler(handle_next, pattern=r"^swep:next$"),
                CallbackQueryHandler(show_menu, pattern=r"^swep:menu$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_swep)],
        name="swep_mvp", persistent=True, per_user=True, per_chat=True,
    )


def register_swep_handlers(app: Any) -> None:
    app.add_handler(build_swep_conversation(), group=0)
