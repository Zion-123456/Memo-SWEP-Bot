"""Async SQLAlchemy session factory.

Provides a single ``AsyncEngine`` and an ``AsyncSessionFactory`` that are
created once at application startup and shared across all requests. Each
request (HTTP or Telegram update) acquires its own short-lived session from
the factory, ensuring connection pool hygiene.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_engine(database_url: str) -> AsyncEngine:
    """Create and configure the async SQLAlchemy engine.

    Args:
        database_url: A ``postgresql+asyncpg://`` connection string.

    Returns:
        A configured :class:`AsyncEngine` with connection pool settings
        appropriate for a production web service.
    """
    return create_async_engine(
        database_url,
        # Pool sizing: keep a modest baseline, allow bursting under load.
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Discard stale connections before use.
        pool_recycle=3600,   # Recycle connections after 1 hour.
        echo=False,          # Set to True only for SQL debugging.
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine.

    Args:
        engine: The :class:`AsyncEngine` to bind sessions to.

    Returns:
        An :class:`async_sessionmaker` that produces :class:`AsyncSession`
        instances. Sessions expire ORM objects on commit so that subsequent
        access re-fetches fresh data.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Async generator that yields a database session and ensures cleanup.

    Intended for use with FastAPI's ``Depends()`` via a closure. Commits on
    successful exit and rolls back on any exception.

    Args:
        session_factory: The factory to create sessions from.

    Yields:
        A transactional :class:`AsyncSession`.
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
