"""Global error handler for the Telegram bot.

Catches all unhandled exceptions that bubble up through the PTB dispatcher
and logs them with full context. Sends a generic error message to the user
so they are never left with a silent failure.
"""

from __future__ import annotations

import traceback

import structlog
from telegram import Update
from telegram.ext import ContextTypes

logger = structlog.get_logger(__name__)

_USER_ERROR_MESSAGE: str = (
    "Something went wrong on my end. Please try again in a moment. "
    "If the problem persists, restart with /start."
)


async def handle_error(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Log the exception and notify the user of the failure.

    This handler is registered as the application-level error handler and
    is invoked whenever an unhandled exception escapes a PTB handler or
    post-processing hook.

    Args:
        update: The Telegram Update that triggered the error (may be ``None``
            if the error occurred outside of an update context).
        context: The PTB context carrying the exception information.
    """
    logger.error(
        "telegram.unhandled_error",
        error=str(context.error),
        traceback=traceback.format_exception(
            type(context.error),
            context.error,
            context.error.__traceback__ if context.error else None,
        ),
    )

    if not isinstance(update, Update):
        return

    # Clear conversation states to allow the user to immediately restart.
    chat_id = update.effective_chat.id if update.effective_chat else None
    tg_user = update.effective_user

    if chat_id and tg_user:
        # 1. Clear Redis conversation state
        try:
            await context.application.persistence.update_conversation(
                "onboarding", (chat_id, tg_user.id), None
            )
            # Clear user temporary data cache
            context.user_data.clear()
            logger.info("telegram.error_recovery.redis_cleared", user_id=tg_user.id)
        except Exception as exc:
            logger.warning("telegram.error_recovery.redis_failed", error=str(exc))

        # 2. Clear Database representation of conversation state
        session_factory = context.bot_data.get("session_factory")
        if session_factory:
            try:
                from app.repositories.conversation import ConversationRepository
                from app.repositories.user import UserRepository
                from app.services.conversation import ConversationService

                async with session_factory() as session:
                    user_repo = UserRepository(session)
                    user = await user_repo.find_by_telegram_id(tg_user.id)
                    if user:
                        conv_service = ConversationService(ConversationRepository(session))
                        await conv_service.reset_state_on_error(user.id)
                        await session.commit()
                        logger.info(
                            "telegram.error_recovery.db_cleared",
                            telegram_id=tg_user.id,
                            user_id=str(user.id),
                        )
            except Exception as exc:
                logger.warning("telegram.error_recovery.db_failed", error=str(exc))

    if update.effective_message:
        await update.effective_message.reply_text(_USER_ERROR_MESSAGE)

