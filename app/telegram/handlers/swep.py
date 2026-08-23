"""Fast SWEP historical-reconstruction and daily logbook MVP flow.

The flow intentionally uses Telegram ``user_data`` for conversational state so
we can ship the MVP without a new database migration. Redis persistence already
used by Memo keeps the state across bot restarts.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.swep.context import SwepContext

CTX_KEY = "swep_flow"
ACTION_START = "swep:start"
ACTION_RECONSTRUCT = "swep:reconstruct"
ACTION_FILL = "swep:fill"
ACTION_CAPTURE = "swep:capture"
ACTION_EVIDENCE = "swep:evidence"
ACTION_PROGRESS = "swep:progress"
ACTION_NEXT = "swep:next"
ACTION_RETRY = "swep:retry"
ACTION_CONFIRM = "swep:confirm"

_PHASE_LABELS = {
    "initial_orientation": "Initial Orientation",
    "department_rotation": "Department Rotation",
    "second_phase_orientation": "Second-Phase Orientation",
    "specialized_project": "Specialized Project",
}


def _ctx() -> SwepContext:
    return SwepContext()


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🧠 Reconstruct Previous SWEP", callback_data=ACTION_RECONSTRUCT)],
            [InlineKeyboardButton("📘 Fill My Logbook", callback_data=ACTION_FILL)],
            [InlineKeyboardButton("➕ Capture Today's Experience", callback_data=ACTION_CAPTURE)],
            [InlineKeyboardButton("📸 Add Evidence", callback_data=ACTION_EVIDENCE)],
            [InlineKeyboardButton("📊 My Progress", callback_data=ACTION_PROGRESS)],
        ]
    )


def _building_keyboard() -> InlineKeyboardMarkup:
    ctx = _ctx()
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for ident, name in ctx.building_options():
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


def _phase_intro(day: date, phase: str) -> str:
    label = _PHASE_LABELS[phase]
    if phase == "department_rotation":
        return (
            f"📅 *{day.strftime('%d %B %Y')}*\n\n"
            f"This falls in the *{label}* phase.\n\n"
            "Which building/department were you in that day? I’ll use the shared SWEP context "
            "to help you recover the session."
        )
    return (
        f"📅 *{day.strftime('%d %B %Y')}*\n\n"
        f"This falls in the *{label}* phase.\n\n"
        "Tell me anything you remember from the day — even a short note is enough."
    )


async def _send_menu(update: Update) -> None:
    text = (
        "📘 *Memo SWEP*\n\n"
        "I’ll help you reconstruct past SWEP days, turn your memories into logbook-ready "
        "suggestions, and keep the process quick.\n\n"
        "Choose what you want to do:"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=_menu_keyboard(), parse_mode="Markdown")
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=_menu_keyboard(), parse_mode="Markdown")


async def start_swep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open the SWEP mini-menu."""
    context.user_data.pop(CTX_KEY, None)
    await _send_menu(update)


async def _begin_reconstruction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data[CTX_KEY] = {"state": "awaiting_date"}
    text = (
        "🧠 *Reconstruct Previous SWEP*\n\n"
        "Which date are you trying to fill?\n\n"
        "Send it as `DD/MM/YYYY`, e.g. `05/08/2026`."
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown")


async def _begin_fill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data[CTX_KEY] = {"state": "awaiting_date"}
    text = (
        "📘 *Fill My Logbook*\n\n"
        "Which SWEP date do you want to prepare?\n\n"
        "Send `DD/MM/YYYY`."
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown")


async def _handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE, day: date) -> None:
    flow = context.user_data[CTX_KEY]
    phase = _ctx().phase_for_date(day)
    flow.update({"state": "awaiting_building" if phase == "department_rotation" else "awaiting_memory", "date": day.isoformat(), "phase": phase})
    if phase == "department_rotation":
        await update.effective_message.reply_text(_phase_intro(day, phase), parse_mode="Markdown", reply_markup=_building_keyboard())
    else:
        await update.effective_message.reply_text(_phase_intro(day, phase), parse_mode="Markdown")


async def _handle_building(update: Update, context: ContextTypes.DEFAULT_TYPE, building_id: str) -> None:
    flow = context.user_data[CTX_KEY]
    building = _ctx().get_building(building_id)
    if not building:
        await update.effective_message.reply_text("I couldn't find that building. Please choose again.", reply_markup=_building_keyboard())
        return
    flow.update({"state": "awaiting_memory", "building_id": building_id})
    await update.effective_message.reply_text(
        f"🏢 *{building.get('building_name')}* selected.\n\n"
        "What do you personally remember from this session? A sentence, keywords, or even “I mostly listened” is enough.",
        parse_mode="Markdown",
    )


async def _generate(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    flow: dict[str, Any],
    student_input: str,
    personal_answers: list[str],
) -> dict[str, Any]:
    provider = context.bot_data.get("ai_provider")
    if provider is None:
        return {
            "draft": {"activity_description": student_input, "learning": "", "personal_contribution": student_input, "skills": "", "reflection": ""},
            "question": "What do you remember most clearly from this session?",
        }
    ctx = _ctx()
    day = str(flow["date"])
    phase = str(flow["phase"])
    building = ctx.get_building(str(flow.get("building_id"))) if flow.get("building_id") else None
    bundle = ctx.prompt_bundle(day=day, phase=phase, building=building, student_input=student_input, personal_answers=personal_answers)
    messages = [
        {
            "role": "system",
            "content": (
                "You are Memo, a SWEP logbook assistant. Generate grounded, concise logbook content. "
                "Shared context is NOT proof of personal participation. Never invent actions, equipment use, "
                "facilitators, dates, measurements, results, or experiences. Every first-person claim must be "
                "supported by student input or personal answers. Return JSON only with keys: draft, question, "
                "ready. draft must contain activity_description, learning, personal_contribution, skills, reflection. "
                "question must be a single useful personalization question or empty string. Ask at most one question."
            ),
        },
        {"role": "user", "content": json.dumps(bundle, ensure_ascii=False)},
    ]
    return await provider.generate_json(messages, max_tokens=1400, temperature=0.15)


async def _handle_memory(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    flow = context.user_data[CTX_KEY]
    flow["student_input"] = text
    flow.setdefault("personal_answers", [])
    result = await _generate(context, flow=flow, student_input=text, personal_answers=flow["personal_answers"])
    draft = result.get("draft") if isinstance(result.get("draft"), dict) else {}
    flow["draft"] = draft
    question = str(result.get("question") or "").strip()
    if question and len(flow["personal_answers"]) < 3:
        flow["state"] = "awaiting_personal_answer"
        await update.effective_message.reply_text(
            _format_draft(draft) + f"\n\n❓ *One quick question:*\n{question}",
            parse_mode="Markdown",
        )
        return
    await _finish_draft(update, context)


async def _handle_personal_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    flow = context.user_data[CTX_KEY]
    flow.setdefault("personal_answers", []).append(text)
    result = await _generate(
        context,
        flow=flow,
        student_input=str(flow.get("student_input", "")),
        personal_answers=flow["personal_answers"],
    )
    flow["draft"] = result.get("draft") if isinstance(result.get("draft"), dict) else flow.get("draft", {})
    flow["state"] = "ready"
    await _finish_draft(update, context)


async def _finish_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    flow = context.user_data[CTX_KEY]
    entries = context.user_data.setdefault("swep_entries", {})
    entries[str(flow["date"])] = {
        "date": flow["date"],
        "phase": flow["phase"],
        "building_id": flow.get("building_id"),
        "student_input": flow.get("student_input", ""),
        "personal_answers": flow.get("personal_answers", []),
        "draft": flow.get("draft", {}),
        "saved_at": datetime.utcnow().isoformat(),
    }
    flow["state"] = "ready"
    await update.effective_message.reply_text(
        _format_draft(flow.get("draft", {}))
        + "\n\n⚠️ *Review this before writing it into your official logbook.* "
        "Memo only uses information you supplied or confirmed."
        + "\n\n✅ Saved to Memo.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("➡️ Continue to next day", callback_data=ACTION_NEXT)],
             [InlineKeyboardButton("📘 SWEP Menu", callback_data=ACTION_START)]]
        ),
    )


async def handle_swep_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    flow = context.user_data.get(CTX_KEY)
    if not flow or not update.effective_message or not update.effective_message.text:
        return
    text = update.effective_message.text.strip()
    state = flow.get("state")
    if state == "awaiting_date":
        day = _date_from_text(text)
        if not day:
            await update.effective_message.reply_text("Please send the date as `DD/MM/YYYY`.", parse_mode="Markdown")
            return
        await _handle_date(update, context, day)
    elif state == "awaiting_memory":
        await _handle_memory(update, context, text)
    elif state == "awaiting_personal_answer":
        await _handle_personal_answer(update, context, text)


async def handle_building_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    building_id = (query.data or "").split(":", 2)[-1]
    flow = context.user_data.get(CTX_KEY)
    if not flow:
        await query.edit_message_text("Start a SWEP flow from the menu first.")
        return
    building = _ctx().get_building(building_id)
    if not building:
        await query.edit_message_text("I couldn't find that building. Please try again.", reply_markup=_building_keyboard())
        return
    flow.update({"state": "awaiting_memory", "building_id": building_id})
    await query.edit_message_text(
        f"🏢 *{building.get('building_name')}* selected.\n\n"
        "What do you personally remember from this session? A sentence, keywords, or even “I mostly listened” is enough.",
        parse_mode="Markdown",
    )


async def handle_swep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    action = query.data or ""
    if action == ACTION_RECONSTRUCT:
        await _begin_reconstruction(update, context)
    elif action == ACTION_FILL:
        await _begin_fill(update, context)
    elif action == ACTION_NEXT:
        flow = context.user_data.get(CTX_KEY, {})
        current = date.fromisoformat(str(flow.get("date", date.today().isoformat())))
        next_day = current.fromordinal(current.toordinal() + 1)
        context.user_data[CTX_KEY] = {"state": "awaiting_date", "prefilled_date": next_day.isoformat()}
        await query.answer()
        await query.edit_message_text(
            f"➡️ *Next day: {next_day.strftime('%d %B %Y')}*\n\n"
            "Send `Continue` to use this date, or send another date.",
            parse_mode="Markdown",
        )
    elif action == ACTION_START:
        await _send_menu(update)
    elif action == ACTION_CAPTURE:
        await query.answer()
        await query.edit_message_text("➕ Send your text, voice note, photo, or document and Memo's normal capture system will save it.")
    elif action == ACTION_EVIDENCE:
        await query.answer()
        await query.edit_message_text("📸 Send a photo or document now. Memo's existing capture system will store it. Evidence linking will be added in the next SWEP iteration.")
    elif action == ACTION_PROGRESS:
        entries = context.user_data.get("swep_entries", {})
        await query.answer()
        await query.edit_message_text(
            f"📊 *SWEP Progress*\n\nDays prepared: *{len(entries)}*\n\n"
            "Use *Fill My Logbook* or *Reconstruct Previous SWEP* to prepare another day.",
            parse_mode="Markdown",
            reply_markup=_menu_keyboard(),
        )
    else:
        await query.answer("Unknown SWEP action.", show_alert=True)


def register_swep_handlers(app: Any) -> None:
    """Register SWEP MVP commands, callbacks, and stateful text capture."""
    app.add_handler(CommandHandler("swep", start_swep), group=0)
    app.add_handler(CallbackQueryHandler(handle_building_callback, pattern=r"^swep:building:"), group=0)
    app.add_handler(CallbackQueryHandler(handle_swep_callback, pattern=r"^swep:(start|reconstruct|fill|capture|evidence|progress|next)$"), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_swep_text), group=0)
