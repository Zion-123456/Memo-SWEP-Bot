"""User repository — data access layer for the User model."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Data access operations specific to the :class:`User` model.

    Extends :class:`BaseRepository` with queries that are unique to the
    User domain. All methods return ORM instances; callers are responsible
    for applying the correct schema transformation before returning data
    to clients.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def find_by_telegram_id(self, telegram_id: int) -> User | None:
        """Retrieve a user by their Telegram user ID.

        This is the primary lookup used by Telegram handlers, which identify
        users by their Telegram ID rather than the internal UUID.

        Args:
            telegram_id: The Telegram platform user identifier.

        Returns:
            The matching :class:`User`, or ``None`` if not registered.
        """
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def exists_by_telegram_id(self, telegram_id: int) -> bool:
        """Check whether a user with the given Telegram ID exists.

        Avoids loading the full User object when only existence is needed.

        Args:
            telegram_id: The Telegram platform user identifier.

        Returns:
            ``True`` if a matching user exists, ``False`` otherwise.
        """
        result = await self._session.execute(
            select(User.id).where(User.telegram_id == telegram_id).limit(1)
        )
        return result.scalar_one_or_none() is not None
