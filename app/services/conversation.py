"""Conversation service — business logic for conversation state management.

Maintains an observable record of each user's current dialogue state in the
database. This acts as an audit trail and disaster-recovery mechanism
alongside the Redis-backed PTB conversation handler state.
"""

from __future__ import annotations

import uuid

import structlog

from app.models.conversation import Conversation
from app.repositories.conversation import ConversationRepository

logger = structlog.get_logger(__name__)


class ConversationService:
    """Orchestrates conversation state persistence.

    Args:
        conversation_repository: The data access object for Conversation records.
    """

    def __init__(self, conversation_repository: ConversationRepository) -> None:
        self._repo = conversation_repository

    async def record_state(
        self,
        user_id: uuid.UUID,
        state: str,
        last_message_id: int | None = None,
    ) -> Conversation:
        """Persist the current conversation state for a user.

        This method is called after every state transition in the onboarding
        flow so the database always reflects the current PTB handler state.

        Args:
            user_id: The internal UUID of the user.
            state: A human-readable state name (e.g. ``"AWAITING_UNIVERSITY"``).
            last_message_id: Optional Telegram message ID of the bot's reply.

        Returns:
            The persisted :class:`Conversation` instance.
        """
        conversation = await self._repo.upsert(
            user_id=user_id,
            state=state,
            last_message_id=last_message_id,
        )
        logger.debug(
            "conversation.state_recorded",
            user_id=str(user_id),
            state=state,
        )
        return conversation

    async def clear_state(self, user_id: uuid.UUID) -> None:
        """Mark the conversation as completed.

        Sets the state to ``"COMPLETED"`` rather than deleting the record so
        that the history of completed onboardings is preserved.

        Args:
            user_id: The internal UUID of the user.
        """
        await self._repo.upsert(user_id=user_id, state="COMPLETED")
        logger.debug("conversation.completed", user_id=str(user_id))

    async def reset_state_on_error(self, user_id: uuid.UUID) -> None:
        """Mark the conversation state as cleared due to an system error.

        Sets the state to ``"ERROR_CLEARED"`` to ensure the database reflecting
        this reset.

        Args:
            user_id: The internal UUID of the user.
        """
        await self._repo.upsert(user_id=user_id, state="ERROR_CLEARED")
        logger.debug("conversation.error_cleared", user_id=str(user_id))

