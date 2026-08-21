"""User service — business logic for user management.

The service layer is the only place where business rules live. It orchestrates
repository calls, enforces domain invariants, and translates between schemas
and ORM models. It has no knowledge of HTTP, Telegram, or any transport layer.
"""

from __future__ import annotations

import uuid
from datetime import date

import structlog

from app.core.exceptions import DomainValidationError, UserNotFoundError
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate, UserUpdate

logger = structlog.get_logger(__name__)


class UserService:
    """Orchestrates all user-related use-cases.

    Args:
        user_repository: The data access object for User records.
    """

    def __init__(self, user_repository: UserRepository) -> None:
        self._repo = user_repository

    async def get_by_id(self, user_id: uuid.UUID) -> User:
        """Retrieve a user by their internal UUID.

        Args:
            user_id: The internal UUID of the user.

        Returns:
            The located :class:`User` instance.

        Raises:
            UserNotFoundError: If no user exists with the given ID.
        """
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        """Retrieve a user by their Telegram platform ID.

        Returns ``None`` rather than raising so callers can distinguish between
        "user not found" and "error" without catching exceptions in the
        happy path.

        Args:
            telegram_id: The Telegram user ID.

        Returns:
            The matching :class:`User`, or ``None`` if not registered.
        """
        return await self._repo.find_by_telegram_id(telegram_id)

    async def upsert_from_onboarding(
        self,
        telegram_id: int,
        telegram_username: str | None,
        telegram_last_name: str | None,
        profile: UserCreate,
    ) -> tuple[User, bool]:
        """Create or fully update a user from the onboarding flow.

        This is the canonical write path triggered at the end of the /start
        conversation. If a user already exists for the given ``telegram_id``,
        their profile is updated. Otherwise a new user is created.

        Args:
            telegram_id: The Telegram user ID.
            telegram_username: Optional Telegram @username (without @).
            telegram_last_name: Optional last name from the Telegram profile.
            profile: Validated onboarding data collected during the flow.

        Returns:
            A tuple of ``(user, created)`` where ``created`` is ``True`` if a
            new record was inserted and ``False`` if an existing one was updated.

        Raises:
            DomainValidationError: If ``start_date`` is not before ``end_date``.
        """
        self._validate_date_range(profile.start_date, profile.end_date)

        existing = await self._repo.find_by_telegram_id(telegram_id)

        if existing is not None:
            updated = await self._repo.update(
                existing.id,
                {
                    "first_name": profile.first_name,
                    "last_name": telegram_last_name,
                    "username": telegram_username,
                    "university": profile.university,
                    "department": profile.department,
                    "programme": profile.programme,
                    "company": profile.company,
                    "supervisor": profile.supervisor,
                    "start_date": profile.start_date,
                    "end_date": profile.end_date,
                },
            )
            assert updated is not None  # noqa: S101
            logger.info(
                "user.profile_updated",
                telegram_id=telegram_id,
                user_id=str(updated.id),
            )
            return updated, False

        user = await self._repo.create(
            {
                "telegram_id": telegram_id,
                "first_name": profile.first_name,
                "last_name": telegram_last_name,
                "username": telegram_username,
                "university": profile.university,
                "department": profile.department,
                "programme": profile.programme,
                "company": profile.company,
                "supervisor": profile.supervisor,
                "start_date": profile.start_date,
                "end_date": profile.end_date,
            }
        )
        logger.info(
            "user.created",
            telegram_id=telegram_id,
            user_id=str(user.id),
        )
        return user, True

    @staticmethod
    def _validate_date_range(start_date: date, end_date: date) -> None:
        """Assert that the SWEP start date precedes the end date.

        Args:
            start_date: The SWEP placement start date.
            end_date: The SWEP placement end date.

        Raises:
            DomainValidationError: If ``end_date`` is not after ``start_date``.
        """
        if end_date <= start_date:
            raise DomainValidationError(
                "SWEP end date must be strictly after the start date. "
                f"Received start={start_date}, end={end_date}."
            )
