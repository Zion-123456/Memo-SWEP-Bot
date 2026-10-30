"""Production must not expose REST data before caller authentication exists."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.router import api_router


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/users/00000000-0000-0000-0000-000000000001", None),
        ("GET", "/events", None),
        ("GET", "/events/00000000-0000-0000-0000-000000000001", None),
        ("DELETE", "/events/00000000-0000-0000-0000-000000000001", None),
        ("POST", "/events", {}),
        ("GET", "/users/00000000-0000-0000-0000-000000000001/events", None),
        ("GET", "/users/00000000-0000-0000-0000-000000000001/insights", None),
        ("GET", "/users/00000000-0000-0000-0000-000000000001/topics", None),
        ("GET", "/users/00000000-0000-0000-0000-000000000001/connections", None),
        ("GET", "/users/00000000-0000-0000-0000-000000000001/progress", None),
        ("GET", "/users/00000000-0000-0000-0000-000000000001/growth", None),
        ("GET", "/users/00000000-0000-0000-0000-000000000001/reflections/weekly", None),
        (
            "POST",
            "/users/00000000-0000-0000-0000-000000000001/query",
            {"query": "memories"},
        ),
    ],
)
async def test_production_data_routes_fail_closed(method, path, payload):
    app = FastAPI()
    app.state.settings = MagicMock(is_production=True)
    app.include_router(api_router, prefix="/api/v1")
    # No database state: denial must occur before any infrastructure access.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(method, "/api/v1" + path, json=payload)
    assert response.status_code == 503
    assert "authentication" in response.json()["detail"]


@pytest.mark.asyncio
async def test_production_health_remains_accessible():
    app = FastAPI()
    app.state.settings = MagicMock(is_production=True, app_version="0.1.0")
    session = AsyncMock()
    session.__aenter__.return_value = session
    app.state.session_factory = MagicMock(return_value=session)
    app.state.redis_client = AsyncMock()
    app.include_router(api_router, prefix="/api/v1")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
