"""Regression coverage for safe bot startup configuration."""

import logging
from unittest.mock import MagicMock

from app.core.logging import configure_logging
from app.telegram.bot import build_bot_application


def test_http_clients_do_not_log_telegram_urls(caplog, monkeypatch):
    for name in ("httpx", "httpcore"):
        logger = logging.getLogger(name)
        monkeypatch.setattr(logger, "level", logger.level)
    with caplog.at_level(logging.DEBUG):
        configure_logging("DEBUG", is_production=False)
        logging.getLogger("httpx").info("HTTP Request: bot-test-secret")
        logging.getLogger("httpcore").debug("Transport: bot-test-secret")
        logging.getLogger("memo-test").info("ordinary log retained")
    assert "bot-test-secret" not in caplog.text
    assert "ordinary log retained" in caplog.text


def test_bot_processes_conversation_updates_sequentially():
    application = build_bot_application(
        token="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ",
        session_factory=MagicMock(),
        redis_client=MagicMock(),
    )
    assert application.update_processor.max_concurrent_updates == 1
