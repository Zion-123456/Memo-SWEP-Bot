"""FastAPI webhook host with durable PostgreSQL dispatch and private storage."""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncGenerator
from urllib.parse import urlsplit

import structlog
from fastapi import FastAPI
from sqlalchemy import text
from telegram import Bot

from app.ai.groq import GroqProvider
from app.api.telegram_webhook import router as webhook_router
from app.api.v1.router import api_router
from app.config import settings as settings_module
from app.core.logging import configure_logging
from app.database.session import (
    build_engine,
    build_session_factory,
    database_schema,
    normalize_database_url,
)
from app.documents.pdf import PdfTextExtractor
from app.services.ai_memory import AiMemoryService
from app.services.longitudinal_analysis import LongitudinalAnalysisService
from app.services.webhook import WebhookRuntime
from app.storage.local import LocalStorageProvider
from app.storage.supabase import SupabaseStorageProvider
from app.telegram.bot import build_bot_application

logger = structlog.get_logger(__name__)


def build_storage(settings):
    if settings.storage_provider == "supabase":
        key = settings.supabase_service_role_key
        return SupabaseStorageProvider(
            settings.supabase_url,
            settings.supabase_storage_bucket,
            key.get_secret_value() if key else "",
        )
    if settings.is_production:
        raise RuntimeError(
            "Production uploads require private Supabase Storage; local files are ephemeral on Render Free."
        )
    return LocalStorageProvider()


async def configure_webhook(bot, settings):
    if not settings.register_webhook:
        return
    info = await bot.get_webhook_info()
    if info.url and info.url != settings.webhook_url:
        raise RuntimeError(
            "A different webhook is configured. Review that deployment before switching."
        )
    await bot.set_webhook(
        url=settings.webhook_url,
        secret_token=settings.telegram_webhook_secret.get_secret_value(),
        allowed_updates=["message", "callback_query"],
        max_connections=1,
        drop_pending_updates=False,
    )


def validate_project_target(settings):
    if settings.storage_provider != "supabase":
        return
    reference = settings.supabase_project_ref
    url = normalize_database_url(settings.database_url)
    host = urlsplit(settings.supabase_url).hostname
    if (
        not reference
        or host != reference + ".supabase.co"
        or (reference not in (url.host or "") and reference not in (url.username or ""))
    ):
        raise RuntimeError(
            "Database and Storage must identify the same confirmed Supabase project."
        )


@contextlib.asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = app.state.settings
    configure_logging(settings.log_level, is_production=settings.is_production)
    validate_project_target(settings)
    if settings.is_production and (
        not os.environ.get("DATABASE_URL") or database_schema() != "memo"
    ):
        raise RuntimeError(
            "Production requires the inspected DATABASE_URL and isolated DATABASE_SCHEMA=memo."
        )
    if not settings.telegram_webhook_secret:
        raise RuntimeError(
            "Set TELEGRAM_WEBHOOK_SECRET securely before starting the webhook host."
        )
    engine = build_engine(settings.database_url)
    sessions = build_session_factory(engine)
    storage = app.state.storage_provider
    app.state.session_factory = sessions
    app.state.telegram_ready = False
    app.state.storage_ready = False
    provider = None
    ai_service = None
    runtime = None
    task = None
    try:
        async with engine.connect() as connection:
            version = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            if version != "0006":
                raise RuntimeError(
                    "Review and apply migration 0006 before starting the webhook host."
                )
        if isinstance(storage, SupabaseStorageProvider):
            await storage.check_private_bucket()
        app.state.storage_ready = True
        if settings.ai_enabled:
            provider = GroqProvider(
                settings.get_groq_api_key(),
                model=settings.groq_model,
                transcription_model=settings.groq_transcription_model,
            )
            longitudinal = LongitudinalAnalysisService(
                ai_provider=provider, session_factory=sessions, enabled=True
            )
            ai_service = AiMemoryService(
                ai_provider=provider,
                session_factory=sessions,
                storage_provider=storage,
                enabled=True,
                document_extractor=PdfTextExtractor(
                    max_characters=settings.doc_max_extract_chars
                ),
                longitudinal_service=longitudinal,
            )
            app.state.ai_provider = provider
            app.state.ai_service = ai_service
            app.state.longitudinal_service = longitudinal
        else:
            longitudinal = None
        # Bot initialization is read-only. Registration occurs only when explicitly
        # configured at deployment, never by import or offline test construction.
        async with Bot(settings.telegram_bot_token) as bot:
            await configure_webhook(bot, settings)
            app.state.telegram_ready = True

        def builder():
            return build_bot_application(
                token=settings.telegram_bot_token,
                session_factory=sessions,
                storage_provider=storage,
                ai_service=ai_service,
                ai_provider=provider,
                longitudinal_service=longitudinal,
            )

        runtime = WebhookRuntime(
            sessions, settings.telegram_bot_token.split(":")[0], builder
        )
        app.state.telegram_runtime = runtime
        app.state.telegram_inbox = runtime.inbox
        task = asyncio.create_task(runtime.run())

        def dispatch_finished(completed):
            if not completed.cancelled() and completed.exception() is not None:
                logger.error(
                    "webhook.dispatcher_stopped",
                    error_type=type(completed.exception()).__name__,
                )

        task.add_done_callback(dispatch_finished)
        app.state.dispatcher_task = task
        logger.info(
            "webhook.host_ready", transport="webhook", storage=settings.storage_provider
        )
        yield
    finally:
        app.state.telegram_ready = False
        if runtime:
            await runtime.stop()
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if ai_service:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(ai_service.drain(), timeout=30)
        if provider and provider._client is not None:
            await provider._client.close()
        if isinstance(storage, SupabaseStorageProvider):
            await storage.close()
        await engine.dispose()
        logger.info("webhook.host_stopped")


def create_app() -> FastAPI:
    settings = settings_module.get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=app_lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.storage_provider = build_storage(settings)
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(webhook_router)

    @app.get("/live", include_in_schema=False)
    async def live():
        return {"status": "alive"}

    @app.get("/", tags=["System"])
    async def root():
        return {
            "app": settings.app_name,
            "version": settings.app_version,
            "environment": settings.app_env,
        }

    return app
