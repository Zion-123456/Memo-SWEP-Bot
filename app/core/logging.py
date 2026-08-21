"""Structlog configuration for the Memo application.

Provides two rendering pipelines:
- **Development**: human-readable, coloured console output.
- **Production**: structured JSON suitable for log aggregation (e.g. Datadog,
  Google Cloud Logging, Loki).

Call ``configure_logging`` exactly once at application startup before any
loggers are obtained.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(log_level: str, *, is_production: bool) -> None:
    """Configure structlog and stdlib logging for the application.

    Args:
        log_level: The minimum log level as a string (e.g. ``"INFO"``).
        is_production: When ``True``, emit JSON logs. When ``False``, emit
            coloured human-readable logs.
    """
    shared_processors: list[Any] = [
        # Merge any values bound to contextvars (e.g. request_id, user_id)
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    if is_production:
        processors: list[Any] = [
            *shared_processors,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level)
        ),
        context_class=dict,
        # Use stdlib loggers so processors like ``add_logger_name`` (which
        # access ``logger.name``) work and output is routed through the
        # ``logging.basicConfig`` handlers configured below.
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging through structlog so third-party libraries
    # (SQLAlchemy, uvicorn, python-telegram-bot) produce consistent output.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Silence overly verbose libraries in production
    if is_production:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
