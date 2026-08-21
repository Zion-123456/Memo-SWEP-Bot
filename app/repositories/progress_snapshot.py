"""ProgressSnapshot repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress_snapshot import ProgressSnapshot
from app.repositories.base import BaseRepository


class ProgressSnapshotRepository(BaseRepository[ProgressSnapshot]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ProgressSnapshot)

    async def get_latest_for_user(
        self,
        user_id: uuid.UUID,
    ) -> ProgressSnapshot | None:
        result = await self._session.execute(
            select(ProgressSnapshot)
            .where(ProgressSnapshot.user_id == user_id)
            .order_by(ProgressSnapshot.generated_at.desc())
            .limit(1)
        )
        return await self._resolve_maybe_awaitable(result.scalar_one_or_none())
