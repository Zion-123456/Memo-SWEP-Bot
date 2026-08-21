"""MemoryConnection repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_connection import MemoryConnection
from app.repositories.base import BaseRepository


class MemoryConnectionRepository(BaseRepository[MemoryConnection]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MemoryConnection)

    async def find_by_user_id(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 100,
    ) -> Sequence[MemoryConnection]:
        result = await self._session.execute(
            select(MemoryConnection)
            .where(MemoryConnection.user_id == user_id)
            .order_by(MemoryConnection.created_at.desc())
            .limit(limit)
        )
        scalars = await self._resolve_maybe_awaitable(result.scalars())
        return await self._resolve_maybe_awaitable(scalars.all())

    async def find_for_event(
        self,
        user_id: uuid.UUID,
        event_id: uuid.UUID,
        *,
        limit: int = 10,
    ) -> Sequence[MemoryConnection]:
        result = await self._session.execute(
            select(MemoryConnection)
            .where(
                MemoryConnection.user_id == user_id,
                or_(
                    MemoryConnection.source_event_id == event_id,
                    MemoryConnection.target_event_id == event_id,
                ),
            )
            .order_by(MemoryConnection.created_at.desc())
            .limit(limit)
        )
        scalars = await self._resolve_maybe_awaitable(result.scalars())
        return await self._resolve_maybe_awaitable(scalars.all())

    async def exists(
        self,
        source_event_id: uuid.UUID,
        target_event_id: uuid.UUID,
        connection_type: str,
    ) -> bool:
        from app.models.memory_connection import ConnectionType

        try:
            conn_type = ConnectionType(connection_type)
        except ValueError:
            return True
        result = await self._session.execute(
            select(MemoryConnection.id).where(
                MemoryConnection.source_event_id == source_event_id,
                MemoryConnection.target_event_id == target_event_id,
                MemoryConnection.connection_type == conn_type,
            )
        )
        return (await self._resolve_maybe_awaitable(result.scalar_one_or_none())) is not None
