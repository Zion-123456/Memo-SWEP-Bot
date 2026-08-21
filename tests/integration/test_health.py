"""Integration tests for the health endpoint."""

from typing import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.router import api_router


@pytest.fixture
def app_with_mocks() -> FastAPI:
    """Return a minimal FastAPI app with mocked infrastructure in state.

    We test the health endpoint using mocked infrastructure to ensure it
    correctly handles and reports failure states without requiring real
    containers for this specific test suite.
    """
    app = FastAPI()
    app.include_router(api_router)

    # Mock settings
    class MockSettings:
        app_version = "0.1.0"
        is_production = False

    app.state.settings = MockSettings()

    return app


@pytest.fixture
async def client(app_with_mocks: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Return a test client for the mocked app."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_mocks),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_check_ok(app_with_mocks: FastAPI, client: AsyncClient) -> None:
    # Arrange: Mock healthy DB and Redis
    mock_session = AsyncMock()
    app_with_mocks.state.session_factory = MagicMock(return_value=mock_session)
    # The session factory returns a context manager that yields the session
    mock_session.__aenter__.return_value = mock_session

    mock_redis = AsyncMock()
    app_with_mocks.state.redis_client = mock_redis

    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["checks"]["database"]["status"] == "ok"
    assert data["checks"]["redis"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_check_database_unavailable(
    app_with_mocks: FastAPI, client: AsyncClient
) -> None:
    # Arrange: Mock failing DB, healthy Redis
    mock_session = AsyncMock()
    mock_session.execute.side_effect = Exception("Connection refused")
    app_with_mocks.state.session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session

    mock_redis = AsyncMock()
    app_with_mocks.state.redis_client = mock_redis

    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200  # Endpoint still returns 200, status payload reflects error
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["checks"]["database"]["status"] == "unavailable"
    assert "Connection refused" in data["checks"]["database"]["detail"]
    assert data["checks"]["redis"]["status"] == "ok"


from unittest.mock import MagicMock
