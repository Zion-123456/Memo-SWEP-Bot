"""KnowledgeTopic repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_topic import KnowledgeTopic
from app.repositories.base import BaseRepository


class KnowledgeTopicRepository(BaseRepository[KnowledgeTopic]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, KnowledgeTopic)

    async def find_by_user_id(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
    ) -> Sequence[KnowledgeTopic]:
        result = await self._session.execute(
            select(KnowledgeTopic)
            .where(KnowledgeTopic.user_id == user_id)
            .order_by(KnowledgeTopic.last_seen.desc(), KnowledgeTopic.memory_count.desc())
            .limit(limit)
        )
        scalars = await self._resolve_maybe_awaitable(result.scalars())
        return await self._resolve_maybe_awaitable(scalars.all())

    async def find_by_user_and_topic(
        self,
        user_id: uuid.UUID,
        topic: str,
    ) -> KnowledgeTopic | None:
        result = await self._session.execute(
            select(KnowledgeTopic).where(
                KnowledgeTopic.user_id == user_id,
                KnowledgeTopic.topic == topic,
            )
        )
        return await self._resolve_maybe_awaitable(result.scalar_one_or_none())
