"""Pytest configuration and shared fixtures.

Most fixtures here are for unit tests, meaning they mock out the database
and Redis dependencies. Integration test fixtures (which would spin up
real containers using testcontainers) belong in tests/integration/conftest.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.user import User
from app.repositories.user import UserRepository
from app.services.user import UserService
from app.config.settings import Settings, get_settings

@pytest.fixture(autouse=True)
def override_settings():
    """Override settings for all tests to bypass validation."""
    settings = Settings(
        telegram_bot_token="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ",
        database_url="postgresql+asyncpg://memo:memo@localhost:5432/memo",
        redis_url="redis://localhost:6379/0",
        app_env="development"
    )
    get_settings.cache_clear()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.config.settings.get_settings", lambda: settings)
        yield settings
    get_settings.cache_clear()


@pytest.fixture
def mock_user_repo() -> MagicMock:
    """Return a mock UserRepository."""
    repo = MagicMock(spec=UserRepository)
    # Async methods need to be explicitly mocked as AsyncMocks in older Python,
    # but MagicMock handles it well in 3.8+ if the spec is an async class.
    # We still explicit mock the hot paths to be safe.
    repo.find_by_telegram_id = AsyncMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    return repo


@pytest.fixture
def user_service(mock_user_repo: MagicMock) -> UserService:
    """Return a UserService bound to the mock repository."""
    return UserService(mock_user_repo)


@pytest.fixture
def valid_profile_data() -> dict[str, object]:
    """Return a valid dictionary matching UserCreate."""
    from datetime import date

    return {
        "telegram_id": 123456789,
        "first_name": "Alice",
        "university": "Tech University",
        "department": "Engineering",
        "programme": "Software Engineering",
        "company": "Stripe",
        "start_date": date(2025, 6, 1),
        "end_date": date(2025, 9, 1),
    }
