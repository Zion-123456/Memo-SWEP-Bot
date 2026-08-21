"""Health check endpoint.

Used by load balancers and container orchestrators to determine if the
application is ready to receive traffic.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.schemas.health import HealthResponse, ServiceHealth

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application health check",
    description=(
        "Verifies connectivity to the database and Redis cache. "
        "Returns 200 OK if all critical services are reachable."
    ),
)
async def health_check(request: Request) -> HealthResponse:
    """Perform health checks on all infrastructure dependencies."""
    settings = request.app.state.settings
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    redis_client = request.app.state.redis_client

    checks: dict[str, ServiceHealth] = {}
    overall_status: str = "ok"

    # Check Database
    start = time.perf_counter()
    try:
        async with session_factory() as session:
            # Simple query to verify connection and permissions
            await session.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000
        checks["database"] = ServiceHealth(status="ok", latency_ms=latency)
    except Exception as exc:
        checks["database"] = ServiceHealth(status="unavailable", detail=str(exc))
        overall_status = "unavailable"

    # Check Redis
    start = time.perf_counter()
    try:
        await redis_client.ping()
        latency = (time.perf_counter() - start) * 1000
        checks["redis"] = ServiceHealth(status="ok", latency_ms=latency)
    except Exception as exc:
        checks["redis"] = ServiceHealth(status="unavailable", detail=str(exc))
        overall_status = "unavailable"

    return HealthResponse(
        status=overall_status,  # type: ignore[arg-type]
        version=settings.app_version,
        checks=checks,
    )
