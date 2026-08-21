"""Application factory and lifespan management.

Constructs the FastAPI application, configures middleware, and manages the
async lifespan (startup/shutdown) for shared infrastructure like database
connection pools, Redis clients, and the Telegram bot application.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.groq import GroqProvider
from app.api.v1.router import api_router
from app.config import settings as settings_module
from app.core.logging import configure_logging
from app.database.redis import build_redis_client
from app.database.session import build_engine, build_session_factory
from app.documents.pdf import PdfTextExtractor
from app.services.ai_memory import AiMemoryService
from app.services.longitudinal_analysis import LongitudinalAnalysisService
from app.services.memory_query import MemoryQueryService
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.progress_narrative import ProgressNarrativeService
from app.storage.local import LocalStorageProvider
from app.telegram.bot import build_bot_application

logger = structlog.get_logger(__name__)


@contextlib.asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage global application resources across the server lifecycle.

    Resources created here are attached to ``app.state`` so they can be
    accessed by dependency injection (for HTTP routes) or direct reference
    (for the health check).
    """
    settings = settings_module.get_settings()

    # 1. Logging
    configure_logging(
        log_level=settings.log_level,
        is_production=settings.is_production,
    )
    logger.info("Application starting up...", env=settings.app_env)

    # 2. Database
    logger.info("Initialising database connection pool...")
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    app.state.session_factory = session_factory

    # 3. Redis
    logger.info("Initialising Redis client...")
    redis_client = build_redis_client(settings.redis_url)
    app.state.redis_client = redis_client

    # 4. Storage
    logger.info("Initialising storage provider...")
    storage_provider = LocalStorageProvider()
    app.state.storage_provider = storage_provider

    # 5. AI Memory Intelligence Layer (Sprint 3) — optional, toggleable.
    ai_service: AiMemoryService | None = None
    ai_provider: GroqProvider | None = None
    longitudinal_service: LongitudinalAnalysisService | None = None
    if settings.ai_enabled:
        logger.info("Initialising AI memory processing service...")
        api_key = settings.get_groq_api_key()
        if api_key:
            ai_provider = GroqProvider(
                api_key=api_key,
                model=settings.groq_model,
                transcription_model=settings.groq_transcription_model,
            )
            document_extractor = PdfTextExtractor(
                max_characters=settings.doc_max_extract_chars,
            )
            longitudinal_service = LongitudinalAnalysisService(
                ai_provider=ai_provider,
                session_factory=session_factory,
                enabled=True,
            )
            ai_service = AiMemoryService(
                ai_provider=ai_provider,
                session_factory=session_factory,
                storage_provider=storage_provider,
                enabled=True,
                document_extractor=document_extractor,
                longitudinal_service=longitudinal_service,
            )
            app.state.ai_service = ai_service
            app.state.longitudinal_service = longitudinal_service
            app.state.ai_provider = ai_provider
        else:
            logger.warning(
                "AI_ENABLED is true but GROQ_API_KEY is not set; AI disabled."
            )

    # 6. Telegram Bot
    # The bot runs in the same event loop as FastAPI. This simplifies deployment
    # for Sprint 1 (single container) without sacrificing async concurrency.
    bot_app = build_bot_application(
        token=settings.telegram_bot_token,
        session_factory=session_factory,
        redis_client=redis_client,
        storage_provider=storage_provider,
        ai_service=ai_service,
        ai_provider=ai_provider,
        longitudinal_service=longitudinal_service,
    )
    app.state.bot_app = bot_app

    logger.info("Starting Telegram bot polling...")
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()  # type: ignore[union-attr]

    logger.info("Application startup complete.")
    yield

    # Shutdown sequence (runs in reverse order)
    logger.info("Application shutting down...")

    logger.info("Stopping Telegram bot...")
    await bot_app.updater.stop()  # type: ignore[union-attr]
    await bot_app.stop()
    await bot_app.shutdown()

    logger.info("Closing Redis client...")
    await redis_client.aclose()  # type: ignore[attr-defined]

    logger.info("Disposing database engine...")
    await engine.dispose()

    logger.info("Application shutdown complete.")


def create_app() -> FastAPI:
    """Construct the FastAPI application instance.

    Returns:
        A configured :class:`FastAPI` instance ready for uvicorn.
    """
    settings = settings_module.get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=app_lifespan,
        # Disable default docs in production for security, but keep them in dev.
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )

    # Store settings on state so handlers can access them without re-parsing.
    app.state.settings = settings

    # Storage provider (also initialised in lifespan; here for direct create_app callers like tests)
    app.state.storage_provider = LocalStorageProvider()

    # Setup CORS (restrict this in production based on frontend requirements)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routers
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/", tags=["System"])
    async def root() -> dict[str, str]:
        """Root endpoint returning basic application info."""
        return {
            "app": settings.app_name,
            "version": settings.app_version,
            "environment": settings.app_env,
        }

    return app
