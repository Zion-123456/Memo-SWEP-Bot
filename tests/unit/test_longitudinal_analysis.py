"""Unit tests for longitudinal analysis rule-based fallback."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.longitudinal_analysis import LongitudinalAnalysisService


def _event(summary: str, skills: list[str] | None = None) -> MagicMock:
    evt = MagicMock()
    evt.id = uuid.uuid4()
    evt.event_date = date(2026, 1, 1)
    evt.raw_text = summary
    evt.ai_analysis = {
        "summary": summary,
        "skills": skills or [],
        "tools": [],
        "entities": [],
        "activities": [],
    }
    return evt


def test_rule_based_detects_repeated_topics() -> None:
    service = LongitudinalAnalysisService(None, MagicMock(), enabled=False)
    events = [
        _event("Learned drilling", skills=["drilling", "engineering"]),
        _event("More drilling work", skills=["drilling", "engineering"]),
        _event("Reservoir study", skills=["reservoir", "engineering"]),
    ]
    result = service._analyze_rule_based(events)
    topic_names = {t.topic.lower() for t in result.topics}
    assert "drilling" in topic_names or "engineering" in topic_names


@pytest.mark.asyncio
async def test_maybe_analyze_increments_counter() -> None:
    """maybe_analyze increments events_since_last_analysis and returns False when threshold not met."""
    from unittest.mock import patch as mock_patch

    session = AsyncMock()
    session.commit = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    state = MagicMock()
    state.events_since_last_analysis = 0
    state.last_analysis_at = None

    state_repo = MagicMock()
    state_repo.get_or_create = AsyncMock(return_value=state)
    event_repo = MagicMock()
    event_repo.count_by_user_id = AsyncMock(return_value=1)

    session_factory = MagicMock(return_value=session)

    service = LongitudinalAnalysisService(None, session_factory, enabled=False)
    service.analyze = AsyncMock(return_value=None)  # type: ignore[method-assign]

    # Patch the repository classes so maybe_analyze gets our pre-configured mocks
    # instead of instantiating real repos that would try to await session.execute()
    with mock_patch(
        "app.services.longitudinal_analysis.UserLongitudinalStateRepository",
        return_value=state_repo,
    ), mock_patch(
        "app.services.longitudinal_analysis.EventRepository",
        return_value=event_repo,
    ):
        ran = await service.maybe_analyze(uuid.uuid4())

    assert ran is False
    assert state.events_since_last_analysis == 1
