from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints.health import router
from app.factory import create_app


def host(*, database_ok=True, dispatcher_ok=True):
    app = FastAPI()
    app.include_router(router)
    app.state.settings = SimpleNamespace(app_version="0.1.0", is_production=True)
    session = AsyncMock()
    session.__aenter__.return_value = session
    if not database_ok:
        session.execute.side_effect = RuntimeError("sensitive-database-details")
    app.state.session_factory = MagicMock(return_value=session)
    app.state.telegram_ready = True
    app.state.storage_ready = True
    app.state.dispatcher_task = SimpleNamespace(done=lambda: not dispatcher_ok)
    return app


@pytest.mark.asyncio
async def test_readiness_has_no_redis_requirement():
    async with AsyncClient(
        transport=ASGITransport(host()), base_url="http://test"
    ) as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    assert "redis" not in response.json()["checks"]


@pytest.mark.asyncio
@pytest.mark.parametrize("database_ok,dispatcher_ok", [(False, True), (True, False)])
async def test_readiness_is_unavailable_for_failed_dependencies(
    database_ok, dispatcher_ok
):
    async with AsyncClient(
        transport=ASGITransport(
            host(database_ok=database_ok, dispatcher_ok=dispatcher_ok)
        ),
        base_url="http://test",
    ) as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    assert "sensitive-database-details" not in response.text


@pytest.mark.asyncio
async def test_liveness_does_not_require_downstream_services():
    async with AsyncClient(
        transport=ASGITransport(create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
