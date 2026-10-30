"""Dispatcher lease safety during slow startup and failed construction."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.webhook import WebhookRuntime


@pytest.mark.asyncio
async def test_failed_builder_releases_dispatcher_lease():
    def broken_builder():
        raise RuntimeError("Synthetic construction failure")

    runtime = WebhookRuntime(None, "synthetic", broken_builder)
    runtime.lease = SimpleNamespace(
        acquire=AsyncMock(return_value=True),
        renew=AsyncMock(return_value=True),
        release=AsyncMock(),
    )
    with pytest.raises(RuntimeError, match="construction failure"):
        await runtime.run()
    runtime.lease.release.assert_awaited_once()
    assert not runtime.active


@pytest.mark.asyncio
async def test_lease_is_renewed_during_startup_and_released_on_shutdown_failure():
    renewed = asyncio.Event()
    app = SimpleNamespace(
        running=False,
        stop=AsyncMock(),
        shutdown=AsyncMock(side_effect=RuntimeError),
    )
    runtime = WebhookRuntime(None, "synthetic", lambda: app)
    runtime.lease_renew_interval = 0.001

    async def renew():
        assert not runtime.active
        renewed.set()
        return True

    async def initialize():
        await asyncio.wait_for(renewed.wait(), timeout=1)

    async def start():
        app.running = True
        await runtime.stop()

    app.initialize, app.start = initialize, start
    runtime.inbox.recover = AsyncMock()
    runtime.lease = SimpleNamespace(
        acquire=AsyncMock(return_value=True),
        renew=AsyncMock(side_effect=renew),
        release=AsyncMock(),
    )
    with pytest.raises(RuntimeError):
        await runtime.run()
    assert renewed.is_set()
    app.stop.assert_awaited_once()
    runtime.lease.release.assert_awaited_once()
    assert not runtime.active
