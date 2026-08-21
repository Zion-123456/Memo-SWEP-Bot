"""Unit tests for memory query service."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.longitudinal_models import MemoryQueryAnswer
from app.services.memory_query import MemoryQueryService
from app.services.memory_retrieval import MemoryRetrievalService


@pytest.mark.asyncio
async def test_answer_returns_no_memories_message() -> None:
    repo = MagicMock()
    repo.find_by_user_id = AsyncMock(return_value=[])
    repo.search_by_topic = AsyncMock(return_value=[])
    retrieval = MemoryRetrievalService(repo)
    service = MemoryQueryService(retrieval, enabled=False)

    answer = await service.answer(uuid.uuid4(), "What did I learn about drilling?")
    assert "don't have any memories" in answer.lower()


@pytest.mark.asyncio
async def test_answer_uses_ai_provider_when_enabled() -> None:
    event = MagicMock()
    event.id = uuid.uuid4()
    event.event_date = date.today()
    event.captured_at = event.event_date
    event.raw_text = "Learned drilling"
    event.ai_analysis = {"summary": "Learned drilling"}

    repo = MagicMock()
    repo.search_by_topic = AsyncMock(return_value=[event])
    retrieval = MemoryRetrievalService(repo)

    provider = MagicMock()
    provider.answer_memory_query = AsyncMock(
        return_value=MemoryQueryAnswer(
            answer="You learned about drilling.",
            evidence_event_ids=[str(event.id)],
        )
    )

    service = MemoryQueryService(retrieval, provider, enabled=True)
    answer = await service.answer(uuid.uuid4(), "What have I learned about drilling?")
    assert "drilling" in answer.lower()
    provider.answer_memory_query.assert_called_once()
