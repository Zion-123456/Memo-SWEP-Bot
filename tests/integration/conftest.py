"""Shared fixtures and helpers for integration tests.

The key challenge in these tests is that handlers and services instantiate
*real* repository objects (e.g. MemoryConnectionRepository) and pass them a
session mock. The repositories then call ``await session.execute(...)`` or
``await session.get(...)``, which requires the mock to be an AsyncMock-based
object — not a plain MagicMock.

``make_async_session_mock`` is the canonical factory for this purpose and must
be used anywhere a session is injected into a handler under test.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


def make_async_session_mock() -> MagicMock:
    """Return a MagicMock that behaves like an AsyncSession for repository use.

    - ``session.execute(...)`` is awaitable; its return value exposes a
      ``scalars().all()`` chain that yields ``[]`` and a ``scalar_one()`` that
      returns ``0``.
    - ``session.get(...)`` is awaitable and returns ``None``.
    - ``session.commit``, ``flush``, ``refresh``, and ``delete`` are all
      ``AsyncMock`` instances.
    - ``session.add`` is a plain ``MagicMock`` (SQLAlchemy's ``add`` is sync).
    - The session supports ``async with session:`` via ``__aenter__`` /
      ``__aexit__`` AsyncMocks.
    """
    session = MagicMock()

    # Build a mock result whose .scalars().all() / .scalar_one() work cleanly
    mock_scalars = MagicMock()
    mock_scalars.all = MagicMock(return_value=[])
    mock_scalars.first = MagicMock(return_value=None)
    mock_result = MagicMock()
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    mock_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_result.scalar_one = MagicMock(return_value=0)

    session.execute = AsyncMock(return_value=mock_result)
    session.get = AsyncMock(return_value=None)
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()       # synchronous in SQLAlchemy
    session.delete = AsyncMock()

    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    return session
