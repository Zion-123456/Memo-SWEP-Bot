"""Onboarding ConversationHandler for the /start command.

Implements a linear multi-step onboarding flow that collects a student's
SWEP profile. Each step is a discrete handler function — no business logic
lives here. The handler delegates all persistence to :class:`UserService`
and :class:`ConversationService` via the session factory stored in
``context.bot_data``.

Flow:
    /start
        → AWAITING_FIRST_NAME
        → AWAITING_UNIVERSITY
        → AWAITING_DEPARTMENT
        → AWAITING_PROGRAMME
        → AWAITING_COMPANY
        → AWAITING_START_DATE
        → AWAITING_END_DATE
        → (upsert user) → END
"""

from __future__ import annotations

from datetime import date
from typing import Final

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram import Message, ReplyKeyboardRemove, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.core.exceptions import DomainValidationError
from app.repositories.conversation import ConversationRepository
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate
from app.services.conversation import ConversationService
from app.services.user import UserService
from app.telegram.handlers.dashboard import show_dashboard
from app.telegram.keyboards.reply import date_format_hint_keyboard, remove_keyboard
from app.telegram.states.onboarding import OnboardingState
from app.utils.dates import format_date, parse_date

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Bot message copy — centralised to ease future localisation
# ---------------------------------------------------------------------------

_MSG_WELCOME_NEW: Final[str] = (
    "👋 Welcome to *Memo*!\n\n"
    "I'll help you capture and remember your SWEP journey.\n\n"
    "Let's get you set up in under a minute. What's your *first name*?"
)

_MSG_WELCOME_RETURNING: Final[str] = (
    "👋 Welcome back to *Memo*!\n\n"
    "Let's update your SWEP profile. What's your *first name*?"
)

_MSG_ASK_UNIVERSITY: Final[str] = (
    "Great, {first_name}! 🎓\n\nWhich *university* are you from?"
)

_MSG_ASK_DEPARTMENT: Final[str] = "Which *department* are you in?"

_MSG_ASK_PROGRAMME: Final[str] = (
    "What's your *programme*?\n_(e.g. Computer Science BSc)_"
)

_MSG_ASK_COMPANY: Final[str] = "Which *company* are you doing your SWEP with?"

_MSG_ASK_START_DATE: Final[str] = (
    "When does your SWEP *start*? 📅\n_(use DD/MM/YYYY format)_"
)

_MSG_ASK_END_DATE: Final[str] = "And when does it *end*? 📅\n_(use DD/MM/YYYY format)_"

_MSG_INVALID_DATE: Final[str] = (
    "⚠️ I couldn't read that date.\n\n"
    "Please use *DD/MM/YYYY* format, e.g. `15/09/2025`."
)

_MSG_INVALID_DATE_RANGE: Final[str] = (
    "⚠️ The end date must be *after* the start date.\n\n"
    "When does your SWEP *end*? _(DD/MM/YYYY)_"
)

_MSG_CANCELLED: Final[str] = "Onboarding cancelled. Send /start anytime to try again."

_MSG_COMPLETE: Final[str] = (
    "✅ *You're all set! I'll help you remember your SWEP journey.*\n\n"
    "🏢 {company}\n"
    "🎓 {university} · {programme}\n"
    "📅 {start_date} → {end_date}\n\n"
    "Send me a message anytime to capture a memory!"
)

# ---------------------------------------------------------------------------
# Context data keys (stored in context.user_data during the conversation)
# ---------------------------------------------------------------------------

_KEY_FIRST_NAME: Final[str] = "first_name"
_KEY_UNIVERSITY: Final[str] = "university"
_KEY_DEPARTMENT: Final[str] = "department"
_KEY_PROGRAMME: Final[str] = "programme"
_KEY_COMPANY: Final[str] = "company"
_KEY_START_DATE: Final[str] = "start_date"


# ---------------------------------------------------------------------------
# Helper: safe access to required objects from context
# ---------------------------------------------------------------------------


def _get_session_factory(
    context: ContextTypes.DEFAULT_TYPE,
) -> async_sessionmaker[AsyncSession]:
    """Extract the session factory from bot_data.

    Args:
        context: The PTB handler context.

    Returns:
        The :class:`async_sessionmaker` stored at application startup.
    """
    return context.bot_data["session_factory"]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Handler functions
# ---------------------------------------------------------------------------


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for the /start command.

    Checks whether the user is already registered and sends the appropriate
    greeting. Clears any stale user_data from a previous incomplete flow.

    Args:
        update: The incoming Telegram update.
        context: The PTB handler context.

    Returns:
        The next conversation state: :attr:`OnboardingState.AWAITING_FIRST_NAME`.
    """
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END

    context.user_data.clear()

    telegram_id = update.effective_user.id
    session_factory = _get_session_factory(context)

    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.find_by_telegram_id(telegram_id)
        is_returning = user is not None

    if is_returning:
        assert user is not None
        await update.message.reply_text(
            "👋 Welcome back to *Memo*!\n\n"
            "Your dashboard is below. To update your profile, send /start again.",
            parse_mode="Markdown",
            reply_markup=remove_keyboard(),
        )
        await show_dashboard(update, context, first_name=user.first_name)
        logger.info("onboarding.returning_dashboard_shown", telegram_id=telegram_id)
        return ConversationHandler.END

    message = _MSG_WELCOME_NEW

    await update.message.reply_text(
        message,
        parse_mode="Markdown",
        reply_markup=remove_keyboard(),
    )

    logger.info(
        "onboarding.started",
        telegram_id=telegram_id,
        is_returning=False,
    )
    return OnboardingState.AWAITING_FIRST_NAME


async def handle_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect the user's first name and advance to university.

    Args:
        update: The incoming Telegram update.
        context: The PTB handler context.

    Returns:
        :attr:`OnboardingState.AWAITING_UNIVERSITY` on success, or the same
        state to prompt the user to retry on invalid input.
    """
    message = _require_message(update)
    if message is None:
        return OnboardingState.AWAITING_FIRST_NAME

    first_name = (message.text or "").strip()
    if not _is_valid_text_input(first_name, max_length=255):
        await message.reply_text(
            "Please send your *first name* as plain text (max 255 characters).",
            parse_mode="Markdown",
        )
        return OnboardingState.AWAITING_FIRST_NAME

    context.user_data[_KEY_FIRST_NAME] = first_name
    await message.reply_text(
        _MSG_ASK_UNIVERSITY.format(first_name=first_name),
        parse_mode="Markdown",
    )
    return OnboardingState.AWAITING_UNIVERSITY


async def handle_university(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect the university name and advance to department.

    Args:
        update: The incoming Telegram update.
        context: The PTB handler context.

    Returns:
        :attr:`OnboardingState.AWAITING_DEPARTMENT` on success.
    """
    message = _require_message(update)
    if message is None:
        return OnboardingState.AWAITING_UNIVERSITY

    university = (message.text or "").strip()
    if not _is_valid_text_input(university, max_length=500):
        await message.reply_text(
            "Please send your *university name* as plain text.",
            parse_mode="Markdown",
        )
        return OnboardingState.AWAITING_UNIVERSITY

    context.user_data[_KEY_UNIVERSITY] = university
    await message.reply_text(_MSG_ASK_DEPARTMENT, parse_mode="Markdown")
    return OnboardingState.AWAITING_DEPARTMENT


async def handle_department(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect the department and advance to programme.

    Args:
        update: The incoming Telegram update.
        context: The PTB handler context.

    Returns:
        :attr:`OnboardingState.AWAITING_PROGRAMME` on success.
    """
    message = _require_message(update)
    if message is None:
        return OnboardingState.AWAITING_DEPARTMENT

    department = (message.text or "").strip()
    if not _is_valid_text_input(department, max_length=500):
        await message.reply_text(
            "Please send your *department name* as plain text.",
            parse_mode="Markdown",
        )
        return OnboardingState.AWAITING_DEPARTMENT

    context.user_data[_KEY_DEPARTMENT] = department
    await message.reply_text(_MSG_ASK_PROGRAMME, parse_mode="Markdown")
    return OnboardingState.AWAITING_PROGRAMME


async def handle_programme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect the programme name and advance to company.

    Args:
        update: The incoming Telegram update.
        context: The PTB handler context.

    Returns:
        :attr:`OnboardingState.AWAITING_COMPANY` on success.
    """
    message = _require_message(update)
    if message is None:
        return OnboardingState.AWAITING_PROGRAMME

    programme = (message.text or "").strip()
    if not _is_valid_text_input(programme, max_length=500):
        await message.reply_text(
            "Please send your *programme name* as plain text.",
            parse_mode="Markdown",
        )
        return OnboardingState.AWAITING_PROGRAMME

    context.user_data[_KEY_PROGRAMME] = programme
    await message.reply_text(_MSG_ASK_COMPANY, parse_mode="Markdown")
    return OnboardingState.AWAITING_COMPANY


async def handle_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect the company name and advance to start date.

    Args:
        update: The incoming Telegram update.
        context: The PTB handler context.

    Returns:
        :attr:`OnboardingState.AWAITING_START_DATE` on success.
    """
    message = _require_message(update)
    if message is None:
        return OnboardingState.AWAITING_COMPANY

    company = (message.text or "").strip()
    if not _is_valid_text_input(company, max_length=500):
        await message.reply_text(
            "Please send your *company name* as plain text.",
            parse_mode="Markdown",
        )
        return OnboardingState.AWAITING_COMPANY

    context.user_data[_KEY_COMPANY] = company
    await message.reply_text(
        _MSG_ASK_START_DATE,
        parse_mode="Markdown",
        reply_markup=date_format_hint_keyboard(),
    )
    return OnboardingState.AWAITING_START_DATE


async def handle_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect and validate the SWEP start date.

    Args:
        update: The incoming Telegram update.
        context: The PTB handler context.

    Returns:
        :attr:`OnboardingState.AWAITING_END_DATE` on success, or the same
        state if the date cannot be parsed.
    """
    message = _require_message(update)
    if message is None:
        return OnboardingState.AWAITING_START_DATE

    raw = (message.text or "").strip()
    parsed = parse_date(raw)

    if parsed is None:
        await message.reply_text(
            _MSG_INVALID_DATE,
            parse_mode="Markdown",
            reply_markup=date_format_hint_keyboard(),
        )
        return OnboardingState.AWAITING_START_DATE

    context.user_data[_KEY_START_DATE] = parsed
    await message.reply_text(
        _MSG_ASK_END_DATE,
        parse_mode="Markdown",
        reply_markup=date_format_hint_keyboard(),
    )
    return OnboardingState.AWAITING_END_DATE


async def handle_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect the end date, validate the range, and finalise onboarding.

    On success, upserts the User via :class:`UserService`, records the
    final state via :class:`ConversationService`, and sends the completion
    message. On any validation failure, prompts the user to retry.

    Args:
        update: The incoming Telegram update.
        context: The PTB handler context.

    Returns:
        :const:`ConversationHandler.END` on success, or
        :attr:`OnboardingState.AWAITING_END_DATE` on failure.
    """
    message = _require_message(update)
    if message is None:
        return OnboardingState.AWAITING_END_DATE

    raw = (message.text or "").strip()
    end_date = parse_date(raw)

    if end_date is None:
        await message.reply_text(
            _MSG_INVALID_DATE,
            parse_mode="Markdown",
            reply_markup=date_format_hint_keyboard(),
        )
        return OnboardingState.AWAITING_END_DATE

    start_date: date = context.user_data[_KEY_START_DATE]

    if end_date <= start_date:
        await message.reply_text(
            _MSG_INVALID_DATE_RANGE,
            parse_mode="Markdown",
            reply_markup=date_format_hint_keyboard(),
        )
        return OnboardingState.AWAITING_END_DATE

    # All data collected — delegate persistence to the service layer.
    if update.effective_user is None:
        return ConversationHandler.END

    tg_user = update.effective_user
    profile = UserCreate(
        telegram_id=tg_user.id,
        first_name=context.user_data[_KEY_FIRST_NAME],
        university=context.user_data[_KEY_UNIVERSITY],
        department=context.user_data[_KEY_DEPARTMENT],
        programme=context.user_data[_KEY_PROGRAMME],
        company=context.user_data[_KEY_COMPANY],
        start_date=start_date,
        end_date=end_date,
    )

    session_factory = _get_session_factory(context)

    try:
        async with session_factory() as session:
            user_service = UserService(UserRepository(session))
            conv_service = ConversationService(ConversationRepository(session))

            user, _ = await user_service.upsert_from_onboarding(
                telegram_id=tg_user.id,
                telegram_username=tg_user.username,
                telegram_last_name=tg_user.last_name,
                profile=profile,
            )
            await conv_service.clear_state(user.id)
            await session.commit()

    except DomainValidationError as exc:
        # Defensive: date range was pre-validated above, but belt-and-braces.
        logger.warning("onboarding.domain_validation_error", error=str(exc))
        await message.reply_text(
            _MSG_INVALID_DATE_RANGE,
            parse_mode="Markdown",
            reply_markup=date_format_hint_keyboard(),
        )
        return OnboardingState.AWAITING_END_DATE

    await message.reply_text(
        _MSG_COMPLETE.format(
            company=profile.company,
            university=profile.university,
            programme=profile.programme,
            start_date=format_date(start_date),
            end_date=format_date(end_date),
        ),
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Show the main dashboard after onboarding (Sprint 3.1).
    await show_dashboard(update, context, first_name=profile.first_name)

    logger.info(
        "onboarding.completed",
        telegram_id=tg_user.id,
    )
    return ConversationHandler.END


async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Allow the user to abort the onboarding flow at any step.

    Args:
        update: The incoming Telegram update.
        context: The PTB handler context.

    Returns:
        :const:`ConversationHandler.END`.
    """
    context.user_data.clear()
    if update.message:
        await update.message.reply_text(
            _MSG_CANCELLED,
            reply_markup=ReplyKeyboardRemove(),
        )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# ConversationHandler factory
# ---------------------------------------------------------------------------


def build_onboarding_handler() -> ConversationHandler:  # type: ignore[type-arg]
    """Construct and return the configured onboarding ConversationHandler.

    Returns:
        A fully configured :class:`ConversationHandler` ready to be
        registered on the PTB Application.
    """
    text_only = filters.TEXT & ~filters.COMMAND

    return ConversationHandler(
        entry_points=[CommandHandler("start", handle_start)],
        states={
            OnboardingState.AWAITING_FIRST_NAME: [
                MessageHandler(text_only, handle_first_name)
            ],
            OnboardingState.AWAITING_UNIVERSITY: [
                MessageHandler(text_only, handle_university)
            ],
            OnboardingState.AWAITING_DEPARTMENT: [
                MessageHandler(text_only, handle_department)
            ],
            OnboardingState.AWAITING_PROGRAMME: [
                MessageHandler(text_only, handle_programme)
            ],
            OnboardingState.AWAITING_COMPANY: [
                MessageHandler(text_only, handle_company)
            ],
            OnboardingState.AWAITING_START_DATE: [
                MessageHandler(text_only, handle_start_date)
            ],
            OnboardingState.AWAITING_END_DATE: [
                MessageHandler(text_only, handle_end_date)
            ],
        },
        fallbacks=[CommandHandler("cancel", handle_cancel)],
        # Allow the user to restart mid-flow by sending /start again.
        allow_reentry=True,
        # Human-readable name for Redis key namespacing in persistence.
        name="onboarding",
        persistent=True,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _require_message(update: Update) -> Message | None:
    """Extract the message from an update or return None.

    Args:
        update: The incoming Telegram update.

    Returns:
        The :class:`Message` if present, or ``None``.
    """
    return update.message


def _is_valid_text_input(text: str, *, max_length: int) -> bool:
    """Check that a text value is non-empty and within the length limit.

    Args:
        text: The stripped user input.
        max_length: Maximum allowed character count.

    Returns:
        ``True`` if the input is valid, ``False`` otherwise.
    """
    return bool(text) and len(text) <= max_length
