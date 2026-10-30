"""Health check endpoint.

Used by load balancers and container orchestrators to determine if the
application is ready to receive traffic.
"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.schemas.health import HealthResponse, ServiceHealth

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application health check",
    description=(
        "Verifies database and configured runtime dependencies. "
        "Returns 200 OK if all critical services are reachable."
    ),
)
async def health_check(request: Request) -> HealthResponse:
    """Perform health checks on all infrastructure dependencies."""
    settings = request.app.state.settings
    session_factory: async_sessionmaker[AsyncSession] = (
        request.app.state.session_factory
    )
    redis_client = getattr(request.app.state, "redis_client", None)

    checks: dict[str, ServiceHealth] = {}
    overall_status: str = "ok"

    # Check Database
    start = time.perf_counter()
    try:
        async with session_factory() as session:
            # Simple query to verify connection and permissions
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=5)
        latency = (time.perf_counter() - start) * 1000
        checks["database"] = ServiceHealth(status="ok", latency_ms=latency)
    except Exception as exc:
        checks["database"] = ServiceHealth(
            status="unavailable",
            detail="Database unavailable" if settings.is_production else str(exc),
        )
        overall_status = "unavailable"

    # Optional legacy check only; the webhook runtime never creates a Redis client.
    if redis_client is not None:
        try:
            await asyncio.wait_for(redis_client.ping(), timeout=5)
            checks["redis"] = ServiceHealth(status="ok")
        except Exception:
            checks["redis"] = ServiceHealth(
                status="unavailable", detail="Legacy Redis unavailable"
            )
            overall_status = "unavailable"
    if hasattr(request.app.state, "telegram_ready"):
        ready = request.app.state.telegram_ready
        checks["telegram"] = ServiceHealth(status="ok" if ready else "unavailable")
        task = getattr(request.app.state, "dispatcher_task", None)
        running = task is not None and not task.done()
        checks["dispatcher"] = ServiceHealth(status="ok" if running else "unavailable")
        storage_ready = request.app.state.storage_ready
        storage = getattr(request.app.state, "storage_provider", None)
        from app.storage.supabase import SupabaseStorageProvider

        if isinstance(storage, SupabaseStorageProvider):
            try:
                await asyncio.wait_for(storage.check_private_bucket(), timeout=5)
            except Exception:
                storage_ready = False
        checks["storage"] = ServiceHealth(
            status="ok" if storage_ready else "unavailable"
        )
        if not ready or not running or not storage_ready:
            overall_status = "unavailable"

    return HealthResponse(
        status=overall_status,  # type: ignore[arg-type]
        version=settings.app_version,
        checks=checks,
    )


@router.get("/ready", include_in_schema=False)
async def readiness(request: Request):
    health = await health_check(request)
    return JSONResponse(
        status_code=200 if health.status == "ok" else 503,
        content=health.model_dump(mode="json"),
    )
