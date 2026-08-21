"""User API endpoints.

Exposes RESTful operations for the User domain. All business logic is
delegated to the injected UserService.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_user_service
from app.core.exceptions import UserNotFoundError
from app.schemas.user import UserResponse
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
    description="Retrieve a user's full profile by their internal UUID.",
)
async def get_user(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Retrieve a user by ID."""
    try:
        user = await user_service.get_by_id(user_id)
        # Pydantic's from_attributes=True on UserResponse handles the ORM conversion
        return user  # type: ignore[return-value]
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
