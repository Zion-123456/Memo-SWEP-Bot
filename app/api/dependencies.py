"""FastAPI dependency injection providers — expanded for Sprint 2."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.session import get_session
from app.repositories.attachment import AttachmentRepository
from app.repositories.event import EventRepository
from app.repositories.user import UserRepository
from app.services.ai_memory import AiMemoryService
from app.services.capture import CaptureService
from app.services.user import UserService
from app.storage.local import LocalStorageProvider
from app.storage.provider import StorageProvider


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.session_factory


def get_ai_service(request: Request) -> AiMemoryService | None:
    """Return the AI memory service from app state, or None if AI is disabled."""
    return getattr(request.app.state, "ai_service", None)


def get_ai_provider(request: Request):
    """Return the AI provider from app state, or None if AI is disabled."""
    return getattr(request.app.state, "ai_provider", None)


async def get_db_session(
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session(session_factory):
        yield session


def get_storage_provider(request: Request) -> StorageProvider:
    return getattr(request.app.state, "storage_provider", LocalStorageProvider())


def get_user_repository(
    session: AsyncSession = Depends(get_db_session),
) -> UserRepository:
    return UserRepository(session)


def get_event_repository(
    session: AsyncSession = Depends(get_db_session),
) -> EventRepository:
    return EventRepository(session)


def get_attachment_repository(
    session: AsyncSession = Depends(get_db_session),
) -> AttachmentRepository:
    return AttachmentRepository(session)


def get_user_service(
    user_repo: UserRepository = Depends(get_user_repository),
) -> UserService:
    return UserService(user_repo)


def get_capture_service(
    event_repo: EventRepository = Depends(get_event_repository),
    attachment_repo: AttachmentRepository = Depends(get_attachment_repository),
    storage_provider: StorageProvider = Depends(get_storage_provider),
) -> CaptureService:
    return CaptureService(event_repo, attachment_repo, storage_provider)
