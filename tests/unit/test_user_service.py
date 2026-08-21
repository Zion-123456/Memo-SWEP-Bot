"""Unit tests for the UserService."""

import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import DomainValidationError
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.user import UserService


async def test_upsert_from_onboarding_creates_new_user(
    user_service: UserService,
    mock_user_repo: MagicMock,
    valid_profile_data: dict[str, object],
) -> None:
    # Arrange
    mock_user_repo.find_by_telegram_id.return_value = None
    mock_user = User(id=uuid.uuid4(), **valid_profile_data)  # type: ignore[arg-type]
    mock_user_repo.create.return_value = mock_user

    profile = UserCreate(**valid_profile_data)  # type: ignore[arg-type]

    # Act
    user, created = await user_service.upsert_from_onboarding(
        telegram_id=123,
        telegram_username="alice",
        telegram_last_name="Smith",
        profile=profile,
    )

    # Assert
    assert created is True
    assert user.id == mock_user.id
    mock_user_repo.create.assert_called_once()
    mock_user_repo.update.assert_not_called()


async def test_upsert_from_onboarding_updates_existing_user(
    user_service: UserService,
    mock_user_repo: MagicMock,
    valid_profile_data: dict[str, object],
) -> None:
    # Arrange
    existing_user = User(id=uuid.uuid4(), telegram_id=123)
    mock_user_repo.find_by_telegram_id.return_value = existing_user

    updated_user = User(id=existing_user.id, **valid_profile_data)  # type: ignore[arg-type]
    mock_user_repo.update.return_value = updated_user

    profile = UserCreate(**valid_profile_data)  # type: ignore[arg-type]

    # Act
    user, created = await user_service.upsert_from_onboarding(
        telegram_id=123,
        telegram_username="alice",
        telegram_last_name="Smith",
        profile=profile,
    )

    # Assert
    assert created is False
    assert user.id == existing_user.id
    mock_user_repo.create.assert_not_called()
    mock_user_repo.update.assert_called_once()


async def test_upsert_from_onboarding_rejects_invalid_date_range(
    user_service: UserService,
    valid_profile_data: dict[str, object],
) -> None:
    # Arrange
    data = valid_profile_data.copy()
    data["start_date"] = date(2025, 10, 1)
    data["end_date"] = date(2025, 9, 1)  # Before start_date
    profile = UserCreate(**data)  # type: ignore[arg-type]

    # Act & Assert
    with pytest.raises(DomainValidationError, match="end date must be strictly after"):
        await user_service.upsert_from_onboarding(
            telegram_id=123,
            telegram_username="alice",
            telegram_last_name=None,
            profile=profile,
        )
