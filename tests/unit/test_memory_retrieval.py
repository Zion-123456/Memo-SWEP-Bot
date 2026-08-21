"""Unit tests for memory retrieval service."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.memory_retrieval import MemoryRetrievalService


@pytest.fixture
def event_repo() -> MagicMock:
    repo = MagicMock()
    repo.find_by_user_id = AsyncMock(return_value=[])
    repo.search_by_topic = AsyncMock(return_value=[])
    repo.find_by_user_and_date = AsyncMock(return_value=[])
    repo.find_by_user_date_range = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(event_repo: MagicMock) -> MemoryRetrievalService:
    return MemoryRetrievalService(event_repo)


def test_extract_keywords_filters_stop_words() -> None:
    keywords = MemoryRetrievalService.extract_keywords(
        "What have I learned about drilling engineering?"
    )
    assert "drilling" in keywords
    assert "engineering" in keywords
    assert "what" not in keywords
    assert "learned" not in keywords


def test_infer_time_range() -> None:
    assert MemoryRetrievalService.infer_time_range("What did I do today?") == "today"
    assert MemoryRetrievalService.infer_time_range("What did I do last week?") == "last week"


def test_infer_topic() -> None:
    assert (
        MemoryRetrievalService.infer_topic("What have I learned about reservoir engineering?")
        == "reservoir engineering"
    )


@pytest.mark.asyncio
async def test_retrieve_searches_by_topic_keywords(
    service: MemoryRetrievalService,
    event_repo: MagicMock,
) -> None:
    user_id = uuid.uuid4()
    event = MagicMock()
    event.id = uuid.uuid4()
    event.event_date = date.today()
    event.captured_at = event.event_date
    event_repo.search_by_topic = AsyncMock(return_value=[event])

    results = await service.retrieve(
        user_id,
        query="What have I learned about drilling?",
    )
    assert len(results) == 1
    event_repo.search_by_topic.assert_called()
