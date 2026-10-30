from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.telegram_webhook import router
from app.models.telegram_runtime import TelegramInbox
from app.services.webhook import UPDATE_FAILED, DispatcherLease, Inbox
from app.telegram.persistence.postgres import PostgresPersistence

SECRET = "test_webhook_secret_" + "x" * 40


def endpoint(db):
    sessions = async_sessionmaker(bind=db.bind, expire_on_commit=False)
    app = FastAPI()
    app.state.settings = SimpleNamespace(telegram_webhook_secret=SecretStr(SECRET))
    app.state.telegram_inbox = Inbox(sessions)
    app.include_router(router)
    return app, sessions


@pytest.mark.asyncio
@pytest.mark.parametrize("header", [None, "wrong"])
async def test_webhook_rejects_missing_or_wrong_secret(db, header):
    app, _ = endpoint(db)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        headers = {} if header is None else {"X-Telegram-Bot-Api-Secret-Token": header}
        response = await client.post(
            "/telegram/webhook", json={"update_id": 1}, headers=headers
        )
    assert response.status_code == 403
    assert await db.scalar(select(TelegramInbox)) is None


@pytest.mark.asyncio
async def test_webhook_acknowledges_only_after_durable_unique_acceptance(db):
    app, sessions = endpoint(db)
    headers = {"X-Telegram-Bot-Api-Secret-Token": SECRET}
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        first = await client.post(
            "/telegram/webhook", json={"update_id": 42}, headers=headers
        )
        second = await client.post(
            "/telegram/webhook", json={"update_id": 42}, headers=headers
        )
    assert first.status_code == 200
    assert second.status_code == 200
    app_after_restart = Inbox(sessions)
    bot_app = SimpleNamespace(
        bot=None, process_update=AsyncMock(), update_persistence=AsyncMock()
    )
    assert await app_after_restart.process_one(bot_app)
    assert not await app_after_restart.process_one(bot_app)
    bot_app.process_update.assert_awaited_once()
    async with sessions() as session:
        row = await session.get(TelegramInbox, 42)
        assert row.state == "done"
        assert row.payload == {}


@pytest.mark.asyncio
async def test_failed_dispatch_retries_without_losing_payload(db):
    app, sessions = endpoint(db)
    await app.state.telegram_inbox.accept({"update_id": 44})
    bot_app = SimpleNamespace(
        bot=None,
        process_update=AsyncMock(side_effect=TimeoutError),
        update_persistence=AsyncMock(),
    )
    assert await Inbox(sessions).process_one(bot_app)
    async with sessions() as session:
        row = await session.get(TelegramInbox, 44)
        assert row.state == "pending"
        assert row.payload == {"update_id": 44}
        row.available_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    bot_app.process_update = AsyncMock()
    assert await Inbox(sessions).process_one(bot_app)
    bot_app.process_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_reported_handler_failure_is_not_marked_successful(db):
    app, sessions = endpoint(db)
    await app.state.telegram_inbox.accept({"update_id": 45})

    async def failed(update):
        UPDATE_FAILED.set(True)

    bot_app = SimpleNamespace(
        bot=None, process_update=failed, update_persistence=AsyncMock()
    )
    await Inbox(sessions).process_one(bot_app)
    async with sessions() as session:
        assert (await session.get(TelegramInbox, 45)).state == "pending"


@pytest.mark.asyncio
async def test_conversation_and_profile_restore_without_redis(db):
    _, sessions = endpoint(db)
    original = PostgresPersistence(sessions)
    await original.update_conversation("onboarding", (123, 456), 3)
    await original.update_user_data(
        456,
        {
            "first_name": "Synthetic",
            "start_date": date(2026, 10, 1),
            "credential": "omit",
        },
    )
    restored = PostgresPersistence(sessions)
    assert await restored.get_conversations("onboarding") == {(123, 456): 3}
    profile = (await restored.get_user_data())[456]
    assert profile == {"first_name": "Synthetic", "start_date": date(2026, 10, 1)}
    await restored.update_conversation("onboarding", (123, 456), None)
    assert await restored.get_conversations("onboarding") == {}
    await restored.update_user_data(456, {})
    assert await restored.get_user_data() == {}


@pytest.mark.asyncio
async def test_restart_recovers_accepted_inflight_update(db):
    app, sessions = endpoint(db)
    await app.state.telegram_inbox.accept({"update_id": 46})
    async with sessions() as session:
        row = await session.get(TelegramInbox, 46)
        row.state = "processing"
        await session.commit()
    restarted = Inbox(sessions)
    await restarted.recover()
    bot_app = SimpleNamespace(
        bot=None, process_update=AsyncMock(), update_persistence=AsyncMock()
    )
    assert await restarted.process_one(bot_app)
    bot_app.process_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatcher_lease_allows_standby_and_safe_takeover(db):
    _, sessions = endpoint(db)
    first, second = DispatcherLease(sessions, "synthetic"), DispatcherLease(
        sessions, "synthetic"
    )
    assert await first.acquire()
    assert not await second.acquire()
    assert await first.renew()
    await first.release()
    assert await second.acquire()
    assert not await first.renew()
    await first.release()
    assert await second.renew()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, [], {"update_id": True}, {"update_id": -1}])
async def test_malformed_updates_are_rejected(db, payload):
    app, _ = endpoint(db)
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/telegram/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_inbox_unavailable_returns_retryable_error(db):
    app, _ = endpoint(db)
    app.state.telegram_inbox = SimpleNamespace(
        accept=AsyncMock(side_effect=ConnectionError)
    )
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/telegram/webhook",
            json={"update_id": 99},
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_retry_preserves_chat_order_without_blocking_other_chats(db):
    app, sessions = endpoint(db)

    def payload(identifier, chat):
        return {
            "update_id": identifier,
            "message": {
                "message_id": identifier,
                "date": 1,
                "chat": {"id": chat, "type": "private"},
                "text": "Synthetic",
            },
        }

    await app.state.telegram_inbox.accept(payload(201, 1))
    await app.state.telegram_inbox.accept(payload(202, 1))
    await app.state.telegram_inbox.accept(payload(203, 2))
    failed = SimpleNamespace(
        bot=None,
        process_update=AsyncMock(side_effect=TimeoutError),
        update_persistence=AsyncMock(),
    )
    await Inbox(sessions).process_one(failed)
    succeeded = SimpleNamespace(
        bot=None, process_update=AsyncMock(), update_persistence=AsyncMock()
    )
    assert await Inbox(sessions).process_one(succeeded)
    assert succeeded.process_update.call_args.args[0].update_id == 203
    assert not await Inbox(sessions).process_one(succeeded)
