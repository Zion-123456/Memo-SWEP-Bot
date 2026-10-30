from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

from app.config.settings import Settings
from app.factory import configure_webhook, validate_project_target


@pytest.mark.asyncio
async def test_registration_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("REGISTER_WEBHOOK", raising=False)
    settings = Settings(
        _env_file=None,
        telegram_bot_token="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ",
        ai_enabled=False,
    )
    bot = SimpleNamespace(get_webhook_info=AsyncMock(), set_webhook=AsyncMock())
    assert settings.register_webhook is False
    await configure_webhook(bot, settings)
    bot.get_webhook_info.assert_not_awaited()
    bot.set_webhook.assert_not_awaited()


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://user:synthetic@db.confirmed.supabase.co.attacker.example/postgres",
        "postgresql://postgres.confirmed-extra:synthetic@region.pooler.supabase.com/postgres",
        "postgresql://postgres.confirmed:synthetic@attacker.example/postgres",
    ],
)
def test_project_guard_rejects_substring_identity_matches(dsn):
    settings = SimpleNamespace(
        storage_provider="supabase",
        supabase_project_ref="confirmed",
        supabase_url="https://confirmed.supabase.co",
        database_url=dsn,
    )
    with pytest.raises(RuntimeError, match="same confirmed Supabase project"):
        validate_project_target(settings)


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://memo:synthetic@db.confirmed.supabase.co/postgres",
        "postgresql://postgres.confirmed:synthetic@region.pooler.supabase.com:5432/postgres",
        "postgresql://memo_role.confirmed:synthetic@region.pooler.supabase.com:5432/postgres",
    ],
)
def test_project_guard_accepts_exact_direct_or_session_pooler_identity(dsn):
    validate_project_target(
        SimpleNamespace(
            storage_provider="supabase",
            supabase_project_ref="confirmed",
            supabase_url="https://confirmed.supabase.co",
            database_url=dsn,
        )
    )


@pytest.mark.asyncio
async def test_registration_preserves_pending_updates_and_uses_secret():
    bot = SimpleNamespace(
        get_webhook_info=AsyncMock(return_value=SimpleNamespace(url="")),
        set_webhook=AsyncMock(),
    )
    settings = SimpleNamespace(
        register_webhook=True,
        webhook_url="https://pilot.example/telegram/webhook",
        telegram_webhook_secret=SecretStr("synthetic-webhook-secret"),
    )
    await configure_webhook(bot, settings)
    arguments = bot.set_webhook.call_args.kwargs
    assert arguments["drop_pending_updates"] is False
    assert arguments["secret_token"] == "synthetic-webhook-secret"
    assert arguments["max_connections"] == 1


@pytest.mark.asyncio
async def test_registration_refuses_to_replace_another_deployment():
    bot = SimpleNamespace(
        get_webhook_info=AsyncMock(
            return_value=SimpleNamespace(url="https://other.example/webhook")
        ),
        set_webhook=AsyncMock(),
    )
    settings = SimpleNamespace(
        register_webhook=True, webhook_url="https://pilot.example/telegram/webhook"
    )
    with pytest.raises(RuntimeError, match="different webhook"):
        await configure_webhook(bot, settings)
    bot.set_webhook.assert_not_awaited()


def test_mismatched_supabase_projects_are_rejected_before_network_access():
    settings = SimpleNamespace(
        storage_provider="supabase",
        supabase_project_ref="confirmed",
        supabase_url="https://confirmed.supabase.co",
        database_url="postgresql://user:synthetic@db.different.supabase.co/postgres",
    )
    with pytest.raises(RuntimeError, match="same confirmed Supabase project"):
        validate_project_target(settings)
