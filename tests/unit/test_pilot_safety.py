import logging
from unittest.mock import AsyncMock

import pytest

from app.core.logging import SecretRedactionFilter
from app.database.session import database_schema, normalize_database_url
from app.telegram.handlers.companion import private_only


def test_connection_normalization_preserves_tls_and_password():
    url = normalize_database_url(
        "postgresql://user:p%25word@example.com/db?sslmode=require"
    )
    assert url.drivername == "postgresql+asyncpg"
    assert url.query["ssl"] == "require"
    assert url.password == "p%word"


def test_database_schema_rejects_sql_fragments(monkeypatch):
    monkeypatch.setenv("DATABASE_SCHEMA", "memo; DROP SCHEMA public")
    with pytest.raises(ValueError, match="schema name"):
        database_schema()


def test_log_redaction_removes_injected_credentials(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "synthetic-secret-value")
    record = logging.LogRecord(
        "test",
        logging.ERROR,
        "test",
        1,
        "Provider failed: %s",
        ("synthetic-secret-value",),
        None,
    )
    assert SecretRedactionFilter().filter(record)
    assert "synthetic-secret-value" not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


@pytest.mark.asyncio
async def test_group_chat_stops_before_private_records_are_accessed():
    from types import SimpleNamespace

    from telegram.ext import ApplicationHandlerStop

    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="group"),
        callback_query=None,
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
    )
    with pytest.raises(ApplicationHandlerStop):
        await private_only(update, None)
