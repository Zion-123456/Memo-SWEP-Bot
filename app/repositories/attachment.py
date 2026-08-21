"""Attachment repository — data access layer for Attachment model."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import Attachment
from app.repositories.base import BaseRepository


class AttachmentRepository(BaseRepository[Attachment]):
    """Data access operations specific to the :class:`Attachment` model."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Attachment)

    async def find_by_event_id(self, event_id: uuid.UUID) -> Sequence[Attachment]:
        """Retrieve all attachments linked to a specific Event."""
        result = await self._session.execute(
            select(Attachment).where(Attachment.event_id == event_id)
        )
        return result.scalars().all()

    async def list_by_event(self, event_id: uuid.UUID) -> Sequence[Attachment]:
        """Backward-compatible alias matching the Sprint 2 repository contract."""
        return await self.find_by_event_id(event_id)
