"""Telegram bot application factory and configuration."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram.ext import Application, ApplicationBuilder

from app.ai.groq import GroqProvider
from app.ai.provider import AIProvider
from app.database.redis import Redis
from app.intent.classifier import IntentClassifier
from app.intent.router import IntentRouter
from app.repositories.event import EventRepository
from app.repositories.knowledge_topic import KnowledgeTopicRepository
from app.repositories.memory_connection import MemoryConnectionRepository
from app.services.ai_memory import AiMemoryService
from app.services.longitudinal_analysis import LongitudinalAnalysisService
from app.services.memory_query import MemoryQueryService
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.progress_narrative import ProgressNarrativeService
from app.storage.local import LocalStorageProvider
from app.storage.provider import StorageProvider
from app.telegram.handlers.capture import register_capture_handlers
from app.telegram.handlers.commands import register_command_handlers
from app.telegram.handlers.dashboard import register_dashboard_handlers
from app.telegram.handlers.error import handle_error
from app.telegram.handlers.start import build_onboarding_handler
from app.telegram.middleware.logging import StructlogMiddleware
from app.telegram.persistence.redis_persistence import RedisPersistence

logger = logging.getLogger(__name__)


def build_bot_application(
    token: str,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,  # type: ignore[type-arg]
    storage_provider: StorageProvider | None = None,
    ai_service: AiMemoryService | None = None,
    ai_provider: GroqProvider | None = None,
    longitudinal_service: LongitudinalAnalysisService | None = None,
) -> Application:  # type: ignore[type-arg]
    logger.info("Building Telegram bot application...")

    persistence = RedisPersistence(redis_client)
    if storage_provider is None:
        storage_provider = LocalStorageProvider()

    app = (
        ApplicationBuilder()
        .token(token)
        .persistence(persistence)
        .concurrent_updates(True)
        .build()
    )

    app.bot_data["session_factory"] = session_factory
    app.bot_data["redis_client"] = redis_client
    app.bot_data["storage_provider"] = storage_provider
    app.bot_data["ai_service"] = ai_service
    if longitudinal_service is not None:
        app.bot_data["longitudinal_service"] = longitudinal_service

    intent_router: IntentRouter | None = None
    classifier = IntentClassifier(ai_provider)

    def _progress_factory(session: AsyncSession) -> ProgressNarrativeService:
        return ProgressNarrativeService(
            EventRepository(session),
            KnowledgeTopicRepository(session),
            MemoryConnectionRepository(session),
            ai_provider,
            enabled=ai_provider is not None,
        )

    intent_router = IntentRouter(
        classifier,
        session_factory,
        ai_provider=ai_provider,
        progress_narrative_service_factory=_progress_factory,
    )
    app.bot_data["intent_router"] = intent_router
    if ai_provider is not None:
        app.bot_data["ai_provider"] = ai_provider

    StructlogMiddleware.install(app)

    # 1. Onboarding ConversationHandler
    app.add_handler(build_onboarding_handler())

    # 2. Commands (/today, /timeline, /insights, /delete, /help, /menu)
    register_command_handlers(app)

    # 3. Memory Capture Handlers (Text, Voice, Photo, Document)
    register_capture_handlers(app)

    # 4. Telegram Mini Dashboard (Sprint 3.1)
    register_dashboard_handlers(app)

    # 5. Global Error Handler
    app.add_error_handler(handle_error)

    logger.info("Telegram bot application built successfully.")
    return app
