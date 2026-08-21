"""Telegram update logging middleware.

Logs every incoming Telegram update with a correlation ID that is bound to
the structlog context. This means every log line produced during the handling
of a single update automatically carries the ``update_id`` and ``chat_id``
fields, making distributed traces trivial to reconstruct.
"""

from __future__ import annotations

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars
from telegram import Update
from telegram.ext import BaseHandler, Application
from telegram.ext._utils.types import CCT

logger = structlog.get_logger(__name__)


class StructlogMiddleware:
    """A PTB-compatible middleware that logs each update and binds context vars.

    Registers itself as a pre-process handler on the Application. For every
    update it clears the previous context, binds update-scoped fields, and
    logs a structured entry that can be correlated with all downstream log
    lines produced during that update's lifecycle.

    Usage::

        StructlogMiddleware.install(application)
    """

    @staticmethod
    def install(application: Application) -> None:  # type: ignore[type-arg]
        """Attach the middleware to a PTB Application instance.

        Args:
            application: The PTB Application to instrument.
        """
        application.add_handler(
            _ContextBindingHandler(),
            group=-999,  # Run before all other handlers.
        )


class _ContextBindingHandler(BaseHandler):  # type: ignore[misc]
    """Internal handler that binds structlog context for each update."""

    def __init__(self) -> None:
        super().__init__(callback=self._bind_context)

    def check_update(self, update: object) -> bool:
        """Accept all updates."""
        return isinstance(update, Update)

    async def _bind_context(
        self,
        update: Update,
        context: CCT,
    ) -> None:
        """Bind update-scoped fields and log the incoming update.

        Args:
            update: The incoming Telegram update.
            context: The PTB handler context (unused directly).
        """
        clear_contextvars()

        chat_id = update.effective_chat.id if update.effective_chat else None
        user_id = update.effective_user.id if update.effective_user else None
        update_type = (
            "message"
            if update.message
            else "callback_query"
            if update.callback_query
            else "other"
        )

        bind_contextvars(
            update_id=update.update_id,
            chat_id=chat_id,
            telegram_user_id=user_id,
            update_type=update_type,
        )

        logger.debug(
            "telegram.update_received",
            update_id=update.update_id,
            update_type=update_type,
        )
