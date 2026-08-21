"""Unit tests for progress narrative service."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.progress_narrative import ProgressNarrativeService


def _make_event(summary: str, event_date: date) -> MagicMock:
    event = MagicMock()
    event.id = uuid.uuid4()
    event.event_date = event_date
    event.raw_text = summary
    event.ai_analysis = {"summary": summary, "lessons": ["lesson one"], "activities": ["lab"]}
    return event


@pytest.mark.asyncio
async def test_rule_based_narrative_uses_evidence_only() -> None:
    events = [
        _make_event("Learned drilling basics", date(2026, 1, 1)),
        _make_event("Connected drilling to reservoir data", date(2026, 1, 8)),
    ]
    event_repo = MagicMock()
    event_repo.find_by_user_id = AsyncMock(return_value=events)
    topic_repo = MagicMock()
    topic_repo.find_by_user_id = AsyncMock(return_value=[])
    conn_repo = MagicMock()
    conn_repo.find_by_user_id = AsyncMock(return_value=[])

    service = ProgressNarrativeService(event_repo, topic_repo, conn_repo, enabled=False)
    narrative = await service.generate(uuid.uuid4())

    assert not narrative.insufficient_evidence
    assert "2 memories" in narrative.overview
    assert any("drilling" in e.lower() for e in narrative.evidence)


@pytest.mark.asyncio
async def test_insufficient_evidence_with_single_memory() -> None:
    event_repo = MagicMock()
    event_repo.find_by_user_id = AsyncMock(return_value=[_make_event("One memory", date.today())])
    topic_repo = MagicMock()
    topic_repo.find_by_user_id = AsyncMock(return_value=[])
    conn_repo = MagicMock()
    conn_repo.find_by_user_id = AsyncMock(return_value=[])

    service = ProgressNarrativeService(event_repo, topic_repo, conn_repo, enabled=False)
    narrative = await service.generate(uuid.uuid4())
    assert narrative.insufficient_evidence
