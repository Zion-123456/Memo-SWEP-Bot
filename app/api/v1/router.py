"""API v1 router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import events, growth, health, users

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(users.router)
api_router.include_router(events.router)
api_router.include_router(events.users_router)
api_router.include_router(growth.router)
