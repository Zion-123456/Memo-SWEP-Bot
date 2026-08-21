"""Conversation repository — data access layer for the Conversation model."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    """Data access operations specific to the :class:`Conversation` model."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Conversation)

    async def find_by_user_id(self, user_id: uuid.UUID) -> Conversation | None:
        """Retrieve the active conversation record for a user.

        Args:
            user_id: The internal UUID of the user.

        Returns:
            The :class:`Conversation` record, or ``None`` if none exists.
        """
        result = await self._session.execute(
            select(Conversation).where(Conversation.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: uuid.UUID,
        state: str,
        last_message_id: int | None = None,
    ) -> Conversation:
        """Create or update the conversation record for a user.

        This is the single write path for conversation state — callers do not
        need to distinguish between insert and update.

        Args:
            user_id: The internal UUID of the user.
            state: The current conversation state name.
            last_message_id: Optional Telegram message ID of the last reply.

        Returns:
            The persisted :class:`Conversation` instance.
        """
        existing = await self.find_by_user_id(user_id)
        if existing is not None:
            update_data: dict[str, object] = {"state": state}
            if last_message_id is not None:
                update_data["last_message_id"] = last_message_id
            updated = await self.update(existing.id, update_data)
            assert updated is not None  # noqa: S101 — guaranteed by find_by_user_id
            return updated
        return await self.create(
            {
                "user_id": user_id,
                "state": state,
                "last_message_id": last_message_id,
            }
        )
