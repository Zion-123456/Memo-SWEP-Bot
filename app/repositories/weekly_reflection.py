"""WeeklyReflection repository."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.weekly_reflection import WeeklyReflection
from app.repositories.base import BaseRepository


class WeeklyReflectionRepository(BaseRepository[WeeklyReflection]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WeeklyReflection)

    async def find_for_week(
        self,
        user_id: uuid.UUID,
        week_start: date,
    ) -> WeeklyReflection | None:
        result = await self._session.execute(
            select(WeeklyReflection).where(
                WeeklyReflection.user_id == user_id,
                WeeklyReflection.week_start == week_start,
            )
        )
        return await self._resolve_maybe_awaitable(result.scalar_one_or_none())

    async def get_latest_for_user(
        self,
        user_id: uuid.UUID,
    ) -> WeeklyReflection | None:
        result = await self._session.execute(
            select(WeeklyReflection)
            .where(WeeklyReflection.user_id == user_id)
            .order_by(WeeklyReflection.week_start.desc())
            .limit(1)
        )
        return await self._resolve_maybe_awaitable(result.scalar_one_or_none())
