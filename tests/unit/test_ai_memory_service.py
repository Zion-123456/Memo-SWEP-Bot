"""Unit tests for AiMemoryService — fully mocked provider & session."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.exceptions import AIProviderError, AIValidationError
from app.ai.models import MemoryAnalysis
from app.models.attachment import Attachment, FileType
from app.models.event import Event, PayloadType, ProcessingStatus, SourceType
from app.services.ai_memory import AiMemoryService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeProvider:
    """Test double for AIProvider — no real API calls."""

    def __init__(self, analysis: MemoryAnalysis | None = None):
        self.provider_name = "groq"
        self.default_model = "openai/gpt-oss-120b"
        self._analysis = analysis or MemoryAnalysis(summary="Default analysis")
        self.transcribe_audio = AsyncMock(return_value="transcribed text")
        self.generate_reflection = AsyncMock(return_value="Great work today!")
        self.analyze_memory = AsyncMock(side_effect=self._fake_analyze)

    async def _fake_analyze(self, memory: str) -> MemoryAnalysis:
        """Mimic GroqProvider: empty input returns default; otherwise set metadata."""
        if not memory or not memory.strip():
            return MemoryAnalysis(summary=None)
        analysis = self._analysis
        analysis.model_used = self.default_model
        analysis.processed_at = datetime.now(timezone.utc).isoformat()
        return analysis


def _make_event(
    *,
    payload_type: PayloadType = PayloadType.text,
    raw_text: str | None = "Raw memory text",
    status: ProcessingStatus = ProcessingStatus.pending,
    ai_analysis: dict | None = None,
    attachments: list[Attachment] | None = None,
    is_deleted: bool = False,
    retry_count: int = 0,
) -> Event:
    """Build an Event ORM instance for tests."""
    return Event(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        event_date=date.today(),
        captured_at=datetime.now(timezone.utc),
        source_type=SourceType.telegram,
        payload_type=payload_type,
        raw_text=raw_text,
        status=status,
        payload_metadata=None,
        ai_analysis=ai_analysis,
        processing_retry_count=retry_count,
        is_deleted=is_deleted,
        attachments=attachments or [],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _patch_repo(event: Event | None) -> MagicMock:
    """Create a mock EventRepository that returns the given event."""
    mock_repo = MagicMock()
    mock_repo.get_by_id_with_attachments = AsyncMock(return_value=event)
    return mock_repo


def _make_session_factory() -> MagicMock:
    """Create a mock session factory that yields a mock session."""
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    return MagicMock(return_value=mock_session)


def _make_service(
    provider: FakeProvider | None = None,
    event: Event | None = None,
    enabled: bool = True,
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> tuple[AiMemoryService, MagicMock, MagicMock, MagicMock]:
    """Build a service with all deps mocked. Returns (service, mock_session, mock_repo, mock_storage)."""
    event = event or _make_event()
    sf = _make_session_factory()
    mock_session = sf.return_value
    mock_repo = _patch_repo(event)
    provider = provider or FakeProvider()
    mock_storage = AsyncMock()

    service = AiMemoryService(
        ai_provider=provider,
        session_factory=sf,
        storage_provider=mock_storage,
        enabled=enabled,
        max_attempts=max_attempts,
        base_delay=base_delay,
    )
    return service, mock_session, mock_repo, mock_storage


def _run_with_mocked_repo(service: AiMemoryService, mock_repo: MagicMock):
    """Context manager patching EventRepository to return the mock repo.

    Since AiMemoryService creates ``EventRepository(session)`` internally,
    we patch the class so the mock repo is returned regardless of session.
    """
    return patch("app.services.ai_memory.EventRepository", return_value=mock_repo)


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_success_sets_processed_status_and_analysis() -> None:
    """On success: status → processed, ai_analysis populated, raw_text intact."""
    analysis = MemoryAnalysis(
        summary="Motor wiring analysis",
        skills=["electrical"],
        tools=["multimeter"],
        confidence=0.9,
    )
    event = _make_event()
    service, mock_session, mock_repo, _ = _make_service(provider=FakeProvider(analysis=analysis))
    mock_repo.get_by_id_with_attachments = AsyncMock(return_value=event)

    with _run_with_mocked_repo(service, mock_repo):
        await service.process(event.id)

    assert event.status == ProcessingStatus.processed
    assert event.ai_analysis is not None
    assert event.ai_analysis["summary"] == "Motor wiring analysis"
    assert event.ai_analysis["skills"] == ["electrical"]
    assert event.ai_analysis["provider"] == "groq"
    assert event.ai_analysis["model_used"] == "openai/gpt-oss-120b"
    assert event.raw_text == "Raw memory text"  # raw text preserved
    mock_session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_process_empty_memory_returns_default_analysis() -> None:
    """Empty raw_text + no voice → provider called but returns default analysis."""
    event = _make_event(raw_text="")
    service, _, mock_repo, _ = _make_service()
    provider = service._provider  # FakeProvider
    mock_repo.get_by_id_with_attachments = AsyncMock(return_value=event)

    with _run_with_mocked_repo(service, mock_repo):
        await service.process(event.id)

    # Provider IS called (with empty string), but returns a default analysis
    provider.analyze_memory.assert_awaited_once()
    assert provider.analyze_memory.call_args[0][0] == ""
    assert event.status == ProcessingStatus.processed
    assert event.ai_analysis is not None


@pytest.mark.asyncio
async def test_process_event_not_found_returns_silently() -> None:
    """Missing event → process returns without error."""
    service, _, mock_repo, _ = _make_service()
    mock_repo.get_by_id_with_attachments = AsyncMock(return_value=None)

    with _run_with_mocked_repo(service, mock_repo):
        await service.process(uuid.uuid4())

    service._provider.analyze_memory.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_deleted_event_returns_silently() -> None:
    """Deleted event → process returns without calling provider."""
    event = _make_event(is_deleted=True)
    service, _, mock_repo, _ = _make_service()
    mock_repo.get_by_id_with_attachments = AsyncMock(return_value=event)

    with _run_with_mocked_repo(service, mock_repo):
        await service.process(event.id)

    service._provider.analyze_memory.assert_not_awaited()
    assert event.status == ProcessingStatus.pending  # unchanged


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_already_processed_is_idempotent() -> None:
    """Already-processed events with analysis are skipped."""
    event = _make_event(
        status=ProcessingStatus.processed,
        ai_analysis={"summary": "existing"},
    )
    service, _, mock_repo, _ = _make_service()
    mock_repo.get_by_id_with_attachments = AsyncMock(return_value=event)

    with _run_with_mocked_repo(service, mock_repo):
        await service.process(event.id)

    service._provider.analyze_memory.assert_not_awaited()


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_provider_error_marks_failed_preserves_raw() -> None:
    """AI provider error → status failed, raw_text untouched."""
    event = _make_event(raw_text="Important raw memory")
    provider = FakeProvider()
    provider.analyze_memory = AsyncMock(
        side_effect=AIProviderError("timeout", category="timeout", retryable=True)
    )
    service, _, mock_repo, _ = _make_service(
        provider=provider,
        event=event,
        max_attempts=1,
    )

    call_count = 0
    def repo_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # First call: return the event (in _process_once)
        # Subsequent calls: return same event (in _record_failure)
        return mock_repo

    with patch("app.services.ai_memory.EventRepository", side_effect=repo_side_effect):
        await service.process(event.id)

    assert event.status == ProcessingStatus.failed
    assert event.raw_text == "Important raw memory"  # preserved
    assert event.ai_analysis is not None
    assert event.ai_analysis["failure_category"] == "timeout"


@pytest.mark.asyncio
async def test_process_validation_error_marks_failed_no_retry() -> None:
    """Invalid JSON → failed immediately, no retry."""
    event = _make_event()
    provider = FakeProvider()
    provider.analyze_memory = AsyncMock(side_effect=AIValidationError("bad json"))
    service, _, mock_repo, _ = _make_service(
        provider=provider, event=event, max_attempts=3
    )

    def repo_side_effect(*args, **kwargs):
        return mock_repo

    with patch("app.services.ai_memory.EventRepository", side_effect=repo_side_effect):
        await service.process(event.id)

    assert event.status == ProcessingStatus.failed
    assert event.ai_analysis["failure_category"] == "validation_error"
    provider.analyze_memory.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_retryable_error_retries_then_fails() -> None:
    """Retryable errors are retried up to max_attempts, then marked failed."""
    event = _make_event()
    provider = FakeProvider()
    provider.analyze_memory = AsyncMock(
        side_effect=AIProviderError("network", category="network", retryable=True)
    )
    service, _, mock_repo, _ = _make_service(
        provider=provider, event=event, max_attempts=3, base_delay=0.01
    )

    with _run_with_mocked_repo(service, mock_repo), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        await service.process(event.id)

    assert provider.analyze_memory.await_count == 3
    assert event.status == ProcessingStatus.failed
    assert event.processing_retry_count == 3


@pytest.mark.asyncio
async def test_process_non_retryable_error_fails_immediately() -> None:
    """Non-retryable provider errors mark failed without retry."""
    event = _make_event()
    provider = FakeProvider()
    provider.analyze_memory = AsyncMock(
        side_effect=AIProviderError("bad request", category="provider_error", retryable=False)
    )
    service, _, mock_repo, _ = _make_service(
        provider=provider, event=event, max_attempts=3
    )

    with _run_with_mocked_repo(service, mock_repo):
        await service.process(event.id)

    assert provider.analyze_memory.await_count == 1
    assert event.status == ProcessingStatus.failed


@pytest.mark.asyncio
async def test_process_unexpected_error_marks_failed() -> None:
    """Unexpected exceptions are caught and recorded as failed."""
    event = _make_event()
    provider = FakeProvider()
    provider.analyze_memory = AsyncMock(side_effect=RuntimeError("unexpected"))
    service, _, mock_repo, _ = _make_service(
        provider=provider, event=event, max_attempts=1
    )

    with _run_with_mocked_repo(service, mock_repo):
        await service.process(event.id)

    assert event.status == ProcessingStatus.failed
    assert event.ai_analysis["failure_category"] == "unexpected"


# ---------------------------------------------------------------------------
# Disabled service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_service_noops() -> None:
    """When enabled=False, process is a no-op."""
    service, _, _, _ = _make_service(enabled=False)
    await service.process(uuid.uuid4())
    service._provider.analyze_memory.assert_not_awaited()


# ---------------------------------------------------------------------------
# Voice transcription
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_event_transcribes_and_preserves_original() -> None:
    """Voice event with no raw_text: transcribes, stores transcript, preserves attachment."""
    event_id = uuid.uuid4()
    storage_url = "2025/08/05/voice_abc.ogg"
    attachment = Attachment(
        id=uuid.uuid4(),
        event_id=event_id,
        file_type=FileType.voice,
        telegram_file_id="tg_file_id",
        storage_url=storage_url,
        original_filename="voice_abc.ogg",
        mime_type="audio/ogg",
        file_size=1024,
    )
    event = _make_event(
        payload_type=PayloadType.voice,
        raw_text=None,
        attachments=[attachment],
    )
    provider = FakeProvider()
    provider.transcribe_audio = AsyncMock(
        return_value="I was debugging the conveyor motor today."
    )
    service, _, mock_repo, mock_storage = _make_service(
        provider=provider, event=event
    )
    mock_repo.get_by_id_with_attachments = AsyncMock(return_value=event)
    mock_storage.read = AsyncMock(return_value=b"fake-audio-bytes")

    with patch("app.services.ai_memory.StorageProvider", return_value=mock_storage):
        with _run_with_mocked_repo(service, mock_repo):
            await service.process(event_id)

    # Transcript stored in raw_text
    assert event.raw_text == "I was debugging the conveyor motor today."
    # Original audio attachment preserved
    assert event.attachments[0].storage_url == storage_url
    assert event.attachments[0].file_type == FileType.voice
    # Provider called for transcription and analysis
    provider.transcribe_audio.assert_awaited_once()
    provider.analyze_memory.assert_awaited_once()
    assert event.status == ProcessingStatus.processed


@pytest.mark.asyncio
async def test_voice_transcription_failure_marks_failed_preserves_raw() -> None:
    """Voice transcription failure → failed, raw_text stays None, attachment preserved."""
    event_id = uuid.uuid4()
    attachment = Attachment(
        id=uuid.uuid4(),
        event_id=event_id,
        file_type=FileType.voice,
        telegram_file_id="tg_file_id",
        storage_url="voice.ogg",
        original_filename="voice.ogg",
        mime_type="audio/ogg",
        file_size=1024,
    )
    event = _make_event(
        payload_type=PayloadType.voice,
        raw_text=None,
        attachments=[attachment],
    )
    provider = FakeProvider()
    provider.transcribe_audio = AsyncMock(
        side_effect=AIProviderError("timeout", category="timeout", retryable=True)
    )
    service, _, mock_repo, mock_storage = _make_service(
        provider=provider, event=event, max_attempts=1
    )
    mock_repo.get_by_id_with_attachments = AsyncMock(return_value=event)
    mock_storage.read = AsyncMock(return_value=b"fake-audio")

    with patch("asyncio.sleep", new_callable=AsyncMock), \
         _run_with_mocked_repo(service, mock_repo):
        await service.process(event_id)

    assert event.status == ProcessingStatus.failed
    assert event.raw_text is None  # not modified
    assert event.attachments[0].storage_url == "voice.ogg"  # preserved


@pytest.mark.asyncio
async def test_voice_event_with_existing_caption_skips_transcription() -> None:
    """Voice event that already has a caption → no transcription, uses caption."""
    event_id = uuid.uuid4()
    attachment = Attachment(
        id=uuid.uuid4(),
        event_id=event_id,
        file_type=FileType.voice,
        telegram_file_id="tg_file_id",
        storage_url="voice.ogg",
        original_filename="voice.ogg",
        mime_type="audio/ogg",
        file_size=1024,
    )
    event = _make_event(
        payload_type=PayloadType.voice,
        raw_text="User provided caption",
        attachments=[attachment],
    )
    provider = FakeProvider()
    service, _, mock_repo, _ = _make_service(provider=provider, event=event)
    mock_repo.get_by_id_with_attachments = AsyncMock(return_value=event)

    with _run_with_mocked_repo(service, mock_repo):
        await service.process(event_id)

    provider.transcribe_audio.assert_not_awaited()
    assert event.raw_text == "User provided caption"  # preserved
    assert event.status == ProcessingStatus.processed


# ---------------------------------------------------------------------------
# AI failure preserves raw (general case)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_failure_preserves_raw_text() -> None:
    """Regardless of failure type, the raw_text must not be modified."""
    raw = "This is super important raw data that must survive."
    event = _make_event(raw_text=raw)
    provider = FakeProvider()
    provider.analyze_memory = AsyncMock(
        side_effect=AIProviderError("network", category="network", retryable=True)
    )
    service, _, mock_repo, _ = _make_service(
        provider=provider, event=event, max_attempts=2, base_delay=0.01
    )

    with _run_with_mocked_repo(service, mock_repo), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        await service.process(event.id)

    assert event.raw_text == raw
    assert event.status == ProcessingStatus.failed


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_transitions_pending_to_processing_to_processed() -> None:
    """Event status progresses: pending → processing → processed."""
    event = _make_event(status=ProcessingStatus.pending)
    provider = FakeProvider(analysis=MemoryAnalysis(summary="test"))
    service, _, mock_repo, _ = _make_service(provider=provider, event=event)
    mock_repo.get_by_id_with_attachments = AsyncMock(return_value=event)

    with _run_with_mocked_repo(service, mock_repo):
        await service.process(event.id)

    assert event.status == ProcessingStatus.processed


@pytest.mark.asyncio
async def test_status_transitions_pending_to_failed() -> None:
    """Event status goes to failed on terminal error."""
    event = _make_event(status=ProcessingStatus.pending)
    provider = FakeProvider()
    provider.analyze_memory = AsyncMock(
        side_effect=AIValidationError("bad json")
    )
    service, _, mock_repo, _ = _make_service(provider=provider, event=event)
    mock_repo.get_by_id_with_attachments = AsyncMock(return_value=event)

    with _run_with_mocked_repo(service, mock_repo):
        await service.process(event.id)

    assert event.status == ProcessingStatus.failed


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------


def test_schedule_disabled_does_not_create_task() -> None:
    """schedule() returns without creating a task when AI is disabled."""
    service, _, _, _ = _make_service(enabled=False)

    with patch("asyncio.get_running_loop", side_effect=RuntimeError):
        service.schedule(uuid.uuid4())  # no exception


@pytest.mark.asyncio
async def test_schedule_creates_task_when_enabled() -> None:
    """schedule() fires a background task when AI is enabled and loop is running."""
    service, _, _, _ = _make_service(enabled=True)
    created: list = []

    mock_loop = MagicMock()
    mock_loop.create_task = lambda coro: created.append(coro) or MagicMock()

    with patch("asyncio.get_running_loop", return_value=mock_loop):
        service.schedule(uuid.uuid4())

    assert len(created) == 1
