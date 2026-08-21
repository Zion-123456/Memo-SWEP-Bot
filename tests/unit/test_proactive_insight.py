"""Unit tests for proactive insight service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.proactive_insight import ProactiveInsightService


@pytest.mark.asyncio
async def test_connection_hint_from_term_overlap() -> None:
    user_id = uuid.uuid4()
    event_id = uuid.uuid4()
    other_id = uuid.uuid4()

    current = MagicMock()
    current.id = event_id
    current.raw_text = "Today I studied reservoir engineering concepts"
    current.ai_analysis = {"skills": ["reservoir engineering"]}

    prior = MagicMock()
    prior.id = other_id
    prior.raw_text = "Learned reservoir engineering fundamentals yesterday"
    prior.ai_analysis = {"skills": ["reservoir engineering"]}

    event_repo = MagicMock()
    event_repo.get_by_id = AsyncMock(return_value=current)
    event_repo.find_by_user_id = AsyncMock(return_value=[current, prior])
    conn_repo = MagicMock()
    conn_repo.find_for_event = AsyncMock(return_value=[])
    state_repo = MagicMock()

    service = ProactiveInsightService(state_repo, conn_repo, event_repo)
    hint = await service.get_connection_hint(user_id, event_id)
    assert hint is not None
    assert "connects" in hint.lower()


@pytest.mark.asyncio
async def test_pop_pending_insight_respects_cooldown() -> None:
    user_id = uuid.uuid4()
    state = MagicMock()
    state.pending_proactive_insight = {"message": "You are learning drilling"}
    state.last_proactive_insight_at = datetime.now(UTC) - timedelta(hours=1)

    state_repo = MagicMock()
    state_repo.get_or_create = AsyncMock(return_value=state)
    state_repo.update = AsyncMock()

    service = ProactiveInsightService(state_repo, MagicMock(), MagicMock())
    result = await service.pop_pending_insight(user_id)
    assert result is None
