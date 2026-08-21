"""UserLongitudinalState repository."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_longitudinal_state import UserLongitudinalState
from app.repositories.base import BaseRepository


class UserLongitudinalStateRepository(BaseRepository[UserLongitudinalState]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, UserLongitudinalState)

    async def get_or_create(self, user_id: uuid.UUID) -> UserLongitudinalState:
        state = await self.get_by_id(user_id)
        if state is not None:
            return state
        return await self.create({"user_id": user_id})
