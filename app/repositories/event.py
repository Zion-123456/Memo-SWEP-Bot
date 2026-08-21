"""Event repository — data access layer for the Event model."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import Event, ProcessingStatus
from app.repositories.base import BaseRepository


class EventRepository(BaseRepository[Event]):
    """Data access operations specific to the :class:`Event` model."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Event)

    async def get_by_id_with_attachments(self, event_id: uuid.UUID) -> Event | None:
        """Retrieve an event by ID including its linked attachments."""
        result = await self._session.execute(
            select(Event)
            .options(selectinload(Event.attachments))
            .where(Event.id == event_id, Event.is_deleted == False)  # noqa: E712
        )
        return await self._resolve_maybe_awaitable(result.scalar_one_or_none())

    async def list_active(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[Event]:
        """Retrieve active events across all users with attachments preloaded."""
        result = await self._session.execute(
            select(Event)
            .options(selectinload(Event.attachments))
            .where(Event.is_deleted == False)  # noqa: E712
            .order_by(Event.event_date.desc(), Event.captured_at.desc())
            .limit(limit)
            .offset(offset)
        )
        scalars = await self._resolve_maybe_awaitable(result.scalars())
        return await self._resolve_maybe_awaitable(scalars.all())

    async def count_active(self) -> int:
        """Count all non-deleted events."""
        result = await self._session.execute(
            select(func.count(Event.id)).where(Event.is_deleted == False)  # noqa: E712
        )
        value = await self._resolve_maybe_awaitable(result.scalar_one())
        return value or 0

    async def find_by_user_id(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 20,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> Sequence[Event]:
        """Retrieve paginated events for a given user, ordered by event_date desc, captured_at desc."""
        query = select(Event).options(selectinload(Event.attachments)).where(Event.user_id == user_id)
        if not include_deleted:
            query = query.where(Event.is_deleted == False)  # noqa: E712

        result = await self._session.execute(
            query.order_by(Event.event_date.desc(), Event.captured_at.desc())
            .limit(limit)
            .offset(offset)
        )
        scalars = await self._resolve_maybe_awaitable(result.scalars())
        return await self._resolve_maybe_awaitable(scalars.all())

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 20,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> Sequence[Event]:
        """Backward-compatible alias matching the Sprint 2 repository contract."""
        return await self.find_by_user_id(
            user_id,
            limit=limit,
            offset=offset,
            include_deleted=include_deleted,
        )

    async def count_by_user_id(self, user_id: uuid.UUID, include_deleted: bool = False) -> int:
        """Count total events for a user."""
        query = select(func.count(Event.id)).where(Event.user_id == user_id)
        if not include_deleted:
            query = query.where(Event.is_deleted == False)  # noqa: E712
        result = await self._session.execute(query)
        value = await self._resolve_maybe_awaitable(result.scalar_one())
        return value or 0

    async def find_by_user_and_date(
        self,
        user_id: uuid.UUID,
        target_date: date,
    ) -> Sequence[Event]:
        """Retrieve all active events for a specific user on a specific date."""
        result = await self._session.execute(
            select(Event)
            .options(selectinload(Event.attachments))
            .where(
                Event.user_id == user_id,
                Event.event_date == target_date,
                Event.is_deleted == False,  # noqa: E712
            )
            .order_by(Event.captured_at.asc())
        )
        scalars = await self._resolve_maybe_awaitable(result.scalars())
        return await self._resolve_maybe_awaitable(scalars.all())

    async def list_by_user_and_date(
        self,
        user_id: uuid.UUID,
        target_date: date,
    ) -> Sequence[Event]:
        """Backward-compatible alias matching the Sprint 2 repository contract."""
        return await self.find_by_user_and_date(user_id, target_date)

    async def find_by_user_date_range(
        self,
        user_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> Sequence[Event]:
        """Retrieve all active events within a date range (inclusive), ordered newest first."""
        result = await self._session.execute(
            select(Event)
            .options(selectinload(Event.attachments))
            .where(
                Event.user_id == user_id,
                Event.event_date >= start_date,
                Event.event_date <= end_date,
                Event.is_deleted == False,  # noqa: E712
            )
            .order_by(Event.event_date.desc(), Event.captured_at.desc())
        )
        scalars = await self._resolve_maybe_awaitable(result.scalars())
        return await self._resolve_maybe_awaitable(scalars.all())

    async def soft_delete(self, event_id: uuid.UUID) -> bool:
        """Soft-delete an event and mark its processing status as failed."""
        instance = await self.get_by_id(event_id)
        if instance is None or instance.is_deleted:
            return False
        instance.is_deleted = True
        instance.status = ProcessingStatus.failed
        self._session.add(instance)
        await self._session.flush()
        return True

    async def delete(self, event_id: uuid.UUID) -> bool:
        """Repository contract alias for soft-delete in Sprint 2."""
        return await self.soft_delete(event_id)

    async def search_by_topic(
        self,
        user_id: uuid.UUID,
        topic: str,
        *,
        limit: int = 50,
    ) -> Sequence[Event]:
        """Search for events matching a topic keyword in raw_text or ai_analysis.

        The search is case-insensitive and matches against the ``raw_text``
        column and the ``ai_analysis`` JSONB field.

        Args:
            user_id: The internal user UUID (enforces user isolation).
            topic: The topic keyword to search for.
            limit: Maximum number of results.

        Returns:
            A sequence of matching events, newest first.
        """
        from sqlalchemy import or_, text

        ilike_pattern = f"%{topic}%"
        result = await self._session.execute(
            select(Event)
            .options(selectinload(Event.attachments))
            .where(
                Event.user_id == user_id,
                Event.is_deleted == False,  # noqa: E712
                or_(
                    Event.raw_text.ilike(ilike_pattern),
                    text(f"ai_analysis::text ILIKE :p").bindparams(p=ilike_pattern),
                ),
            )
            .order_by(Event.event_date.desc(), Event.captured_at.desc())
            .limit(limit)
        )
        scalars = await self._resolve_maybe_awaitable(result.scalars())
        return await self._resolve_maybe_awaitable(scalars.all())
