"""Generic async repository base.

Provides typed CRUD operations that all concrete repositories inherit.
The base repository is intentionally narrow: it only handles operations that
apply uniformly to every model. Domain-specific queries belong exclusively in
the concrete repository subclasses.

Design principles:
- Repositories are stateless beyond the injected session.
- They never contain business logic or raise domain exceptions.
- All methods are async to remain compatible with the async engine.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic repository providing typed CRUD operations for an ORM model.

    Args:
        session: The active :class:`AsyncSession` for this unit of work.
        model: The SQLAlchemy model class this repository manages.
    """

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self._session = session
        self._model = model

    @property
    def session(self) -> AsyncSession:
        """Expose the current unit-of-work session to orchestration services."""
        return self._session

    async def _resolve_maybe_awaitable(self, value: Any) -> Any:
        """Return awaited values for async test doubles, or the value directly."""
        if inspect.isawaitable(value):
            return await value
        return value

    async def get_by_id(self, record_id: uuid.UUID) -> ModelT | None:
        """Retrieve a single record by its primary key.

        Args:
            record_id: The UUID primary key of the record.

        Returns:
            The model instance, or ``None`` if not found.
        """
        return await self._session.get(self._model, record_id)

    async def list_all(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ModelT]:
        """Retrieve a paginated list of all records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip from the start.

        Returns:
            A sequence of model instances.
        """
        result = await self._session.execute(
            select(self._model).limit(limit).offset(offset)
        )
        scalars = await self._resolve_maybe_awaitable(result.scalars())
        return await self._resolve_maybe_awaitable(scalars.all())

    async def create(self, data: dict[str, Any]) -> ModelT:
        """Persist a new record built from the provided field mapping.

        Args:
            data: Dictionary of column names to values.

        Returns:
            The newly created and session-tracked model instance.
        """
        instance = self._model(**data)
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def update(
        self,
        record_id: uuid.UUID,
        data: dict[str, Any],
    ) -> ModelT | None:
        """Apply a partial update to an existing record.

        Only keys present in ``data`` are modified. ``None`` values are
        written as-is; to skip a field, omit it from the dict.

        Args:
            record_id: The UUID of the record to update.
            data: Dictionary of column names to new values.

        Returns:
            The updated model instance, or ``None`` if not found.
        """
        instance = await self.get_by_id(record_id)
        if instance is None:
            return None
        for key, value in data.items():
            setattr(instance, key, value)
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def delete(self, record_id: uuid.UUID) -> bool:
        """Delete a record by its primary key.

        Args:
            record_id: The UUID of the record to delete.

        Returns:
            ``True`` if the record was found and deleted, ``False`` otherwise.
        """
        instance = await self.get_by_id(record_id)
        if instance is None:
            return False
        await self._session.delete(instance)
        await self._session.flush()
        return True
