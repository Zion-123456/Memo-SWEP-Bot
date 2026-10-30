"""Exercise the actual FastAPI lifespan and PostgreSQL dispatcher without Redis."""

import asyncio
import json
import os
import sys

import pytest
from httpx import ASGITransport, AsyncClient
from telegram import Bot
from telegram.request import BaseRequest

from app import factory
from app.config.settings import Settings


class ReadOnlyTelegramAPI(BaseRequest):
    """Fail immediately if startup attempts polling or webhook registration."""

    @property
    def read_timeout(self):
        return 10

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def do_request(self, url, method, **kwargs):
        assert url.rsplit("/", 1)[-1] == "getMe"
        return (
            200,
            json.dumps(
                {
                    "ok": True,
                    "result": {
                        "id": 123456789,
                        "is_bot": True,
                        "first_name": "Synthetic Memo",
                        "username": "synthetic_memo_bot",
                    },
                }
            ).encode(),
        )


@pytest.mark.asyncio
async def test_actual_lifespan_starts_and_stops_with_postgres_and_no_redis(
    monkeypatch,
    tmp_path,
):
    dsn = os.environ.get("MEMO_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Requires an isolated local test database")
    configuration = Settings(
        _env_file=None,
        database_url=dsn,
        app_env="test",
        ai_enabled=False,
        telegram_bot_token="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ",
        telegram_webhook_secret="synthetic_webhook_secret_" + "x" * 32,
        register_webhook=False,
        storage_provider="local",
    )
    monkeypatch.setenv("DATABASE_SCHEMA", "public")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setitem(sys.modules, "redis", None)
    monkeypatch.setattr(factory.settings_module, "get_settings", lambda: configuration)
    monkeypatch.setattr(
        factory,
        "Bot",
        lambda token: Bot(token, request=ReadOnlyTelegramAPI()),
    )
    build = factory.build_bot_application
    monkeypatch.setattr(
        factory,
        "build_bot_application",
        lambda **kwargs: build(**kwargs, request=ReadOnlyTelegramAPI()),
    )
    app = factory.create_app()
    async with app.router.lifespan_context(app):
        for _ in range(100):
            if app.state.telegram_runtime.active:
                break
            if app.state.dispatcher_task.done():
                await app.state.dispatcher_task
            await asyncio.sleep(0.01)
        assert app.state.telegram_runtime.active
        assert not hasattr(app.state, "redis_client")
        async with AsyncClient(
            transport=ASGITransport(app),
            base_url="http://test",
        ) as client:
            assert (await client.get("/api/v1/ready")).status_code == 200
            assert (await client.get("/live")).status_code == 200
    assert app.state.dispatcher_task.done()
    assert not app.state.telegram_ready
    assert not app.state.telegram_runtime.active
