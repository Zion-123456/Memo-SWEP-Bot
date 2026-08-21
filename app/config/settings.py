"""Application configuration via environment variables.

All settings are loaded from the environment (or a .env file in development).
No secrets are ever hardcoded. Accessing an instance through ``get_settings()``
uses ``lru_cache`` so the file is only parsed once per process lifetime.
"""

from __future__ import annotations

import functools
import re
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# BotFather tokens look like ``<bot_id>:<secret>`` (e.g. 8964284841:AAEc...).
_BOT_TOKEN_PATTERN = re.compile(r"^\d{6,10}:[A-Za-z0-9_-]{20,}$")


class Settings(BaseSettings):
    """Centralised, type-safe application configuration.

    All fields are populated from environment variables (case-insensitive).
    The ``model_config`` instructs pydantic-settings to also load a ``.env``
    file when present, making local development frictionless.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    app_name: str = "Memo"
    app_version: str = "0.1.0"
    app_env: Literal["development", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # -------------------------------------------------------------------------
    # Telegram
    # -------------------------------------------------------------------------
    telegram_bot_token: str = "your-bot-token-from-botfather"

    # -------------------------------------------------------------------------
    # Database
    # Format: postgresql+asyncpg://user:password@host:port/db
    # -------------------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://memo:memo@localhost:5432/memo"

    # -------------------------------------------------------------------------
    # Redis
    # Format: redis://host:port/db
    # -------------------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # -------------------------------------------------------------------------
    # AI Memory Intelligence Layer (Sprint 3) — optional and toggleable.
    # Never hard-code keys; they are always read from the environment / .env.
    # -------------------------------------------------------------------------
    ai_enabled: bool = False
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_transcription_model: str = "whisper-large-v3"
    # Sprint 4: model used for lightweight intent classification.
    # Falls back to groq_model when unset or when INTENT_MODEL points to default.
    intent_model: str = ""

    # -------------------------------------------------------------------------
    # Document Intelligence (Sprint 3.1)
    # -------------------------------------------------------------------------
    doc_max_extract_chars: int = 100_000

    # -------------------------------------------------------------------------
    # Derived properties
    # -------------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        """Return True when the application is running in production mode."""
        return self.app_env == "production"

    def get_groq_api_key(self) -> str | None:
        """Return the Groq API key as a plain string, or None if unset.

        The key is never persisted, logged, or serialised by Settings — it is
        only exposed via this accessor at the point of provider construction.
        """
        return self.groq_api_key.get_secret_value() if self.groq_api_key else None

    @model_validator(mode="after")
    def _validate_ai_config(self) -> Settings:
        """Ensure Groq credentials exist whenever AI processing is enabled."""
        if self.ai_enabled and not self.groq_api_key:
            raise ValueError("AI_ENABLED is true but GROQ_API_KEY is not set.")
        return self

    @field_validator("telegram_bot_token")
    @classmethod
    def telegram_bot_token_must_be_valid(cls, value: str) -> str:
        """Ensure a real Telegram Bot token from @BotFather is configured.

        The BotFather placeholder is always rejected with a clear message so the
        bot never boots against an invalid token. When a real token is present
        in ``.env`` it is validated against the standard BotFather format.
        """
        if not value:
            raise ValueError("TELEGRAM_BOT_TOKEN must not be empty.")
        if value == "your-bot-token-from-botfather":
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is still set to the placeholder. "
                "Replace it with a real token from @BotFather (see .env.example)."
            )
        if not _BOT_TOKEN_PATTERN.match(value):
            raise ValueError(
                "TELEGRAM_BOT_TOKEN must be a valid token from @BotFather."
            )
        return value


@functools.lru_cache
def get_settings() -> Settings:
    """Return the cached singleton Settings instance.

    Using ``lru_cache`` guarantees that the .env file and environment are
    only read once per process, which is the correct behaviour for a server.
    """
    return Settings()
