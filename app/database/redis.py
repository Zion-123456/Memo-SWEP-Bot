"""Redis client factory.

Creates and configures an async Redis client that is shared across the
application lifetime. The client is created once at startup and closed
gracefully on shutdown.
"""

from __future__ import annotations

import redis.asyncio as aioredis
from redis.asyncio import Redis


def build_redis_client(redis_url: str) -> Redis:  # type: ignore[type-arg]
    """Create a configured async Redis client from a connection URL.

    Args:
        redis_url: A ``redis://`` or ``rediss://`` connection string.

    Returns:
        An async :class:`Redis` client with a connection pool. The pool is
        shared across all callers so only one set of connections is maintained
        per process.
    """
    return aioredis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
        socket_connect_timeout=5,
        socket_timeout=5,
        health_check_interval=30,
    )
