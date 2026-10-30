"""API v1 router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.v1.endpoints import events, growth, health, users

api_router = APIRouter()


def require_private_development_api(request: Request) -> None:
    """Keep unauthenticated data routes unavailable in production.

    Telegram handlers enforce ownership using Telegram user identities. The
    REST data routes do not yet authenticate callers, so they must not be
    published until a separate authenticated API is implemented.
    """
    if request.app.state.settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The data API is unavailable in production pending authentication.",
        )


api_router.include_router(health.router)
_private_dependencies = [Depends(require_private_development_api)]
api_router.include_router(users.router, dependencies=_private_dependencies)
api_router.include_router(events.router, dependencies=_private_dependencies)
api_router.include_router(events.users_router, dependencies=_private_dependencies)
api_router.include_router(growth.router, dependencies=_private_dependencies)
