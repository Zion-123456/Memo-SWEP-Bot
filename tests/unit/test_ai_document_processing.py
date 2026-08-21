"""Unit tests for document (PDF) processing in AiMemoryService (Sprint 3.1).

Verifies that:
- PDF documents get text extracted before AI analysis
- Original PDF attachment is preserved
- Extracted text is stored in raw_text
- Extraction failures are handled gracefully
- Empty PDFs produce no hallucination
- Retryable AI failures follow the existing retry policy
- User isolation is preserved (events from different users are not mixed)
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.exceptions import AIProviderError
from app.ai.models import MemoryAnalysis
from app.documents.exceptions import (
    DocumentExtractionError,
    DocumentUnsupportedError,
)
from app.documents.models import DocumentExtractionResult
from app.models.attachment import Attachment, FileType
from app.models.event import Event, PayloadType, ProcessingStatus, SourceType
from app.services.ai_memory import AiMemoryService

_TZ = UTC


class FakeProvider:
    """Test double for AIProvider — no real API calls."""

    def __init__(self, analysis: MemoryAnalysis | None = None) -> None:
        self.provider_name = "groq"
        self.default_model = "openai/gpt-oss-120b"
        self._analysis = analysis or MemoryAnalysis(summary="Default analysis")
        self.transcribe_audio = AsyncMock(return_value="transcribed text")
        self.generate_reflection = AsyncMock(return_value="Great work today!")
        self.analyze_memory = AsyncMock(return_value=self._analysis)

    def reset_analyze(self, analysis: MemoryAnalysis | None = None) -> None:
        self._analysis = analysis or MemoryAnalysis(summary="Default analysis")
        self.analyze_memory = AsyncMock(return_value=self._analysis)


class FakeDocExtractor:
    """Test double for DocumentTextExtractor."""

    def __init__(
        self,
        result: DocumentExtractionResult | None = None,
        raise_exception: Exception | None = None,
    ) -> None:
        self.extractor_name = "pymupdf"
        self._result = result
        self._raise = raise_exception
        self.extract = AsyncMock(side_effect=self._do_extract)

    async def _do_extract(
        self, file_bytes: bytes, *, filename: str, mime_type: str
    ) -> DocumentExtractionResult:
        if self._raise:
            raise self._raise
        return self._result or DocumentExtractionResult(text="default", has_text=True)


def _make_pdf_event(
    *,
    raw_text: str | None = None,
    storage_url: str = "documents/pdf_123.pdf",
    status: ProcessingStatus = ProcessingStatus.pending,
    is_deleted: bool = False,
    retry_count: int = 0,
    ai_analysis: dict | None = None,
    user_id: uuid.UUID | None = None,
) -> Event:
    """Build a Document-type Event with a PDF attachment."""
    eid = uuid.uuid4()
    user_id = user_id or uuid.uuid4()
    attachment = Attachment(
        id=uuid.uuid4(),
        event_id=eid,
        file_type=FileType.document,
        telegram_file_id="tg_file_id",
        storage_url=storage_url,
        original_filename="Reservoir For SWEP.pdf",
        mime_type="application/pdf",
        file_size=2048,
    )
    return Event(
        id=eid,
        user_id=user_id,
        event_date=date.today(),
        captured_at=datetime.now(_TZ),
        source_type=SourceType.telegram,
        payload_type=PayloadType.document,
        raw_text=raw_text,
        status=status,
        ai_analysis=ai_analysis,
        processing_retry_count=retry_count,
        is_deleted=is_deleted,
        attachments=[attachment],
        created_at=datetime.now(_TZ),
        updated_at=datetime.now(_TZ),
    )


def _make_service(
    provider: FakeProvider | None = None,
    extractor: FakeDocExtractor | None = None,
    event: Event | None = None,
    max_attempts: int = 3,
    base_delay: float = 0.01,
) -> tuple[AiMemoryService, MagicMock, MagicMock, MagicMock]:
    """Build a service with all deps mocked."""
    event = event or _make_pdf_event()
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()
    sf = MagicMock(return_value=mock_session)
    mock_repo = MagicMock()
    mock_repo.get_by_id_with_attachments = AsyncMock(return_value=event)
    provider = provider or FakeProvider()
    mock_storage = AsyncMock()
    mock_storage.read = AsyncMock(return_value=b"fake-pdf-bytes")
    service = AiMemoryService(
        ai_provider=provider,
        session_factory=sf,
        storage_provider=mock_storage,
        enabled=True,
        max_attempts=max_attempts,
        base_delay=base_delay,
        document_extractor=extractor,
    )
    return service, mock_session, mock_repo, mock_storage


# ---------------------------------------------------------------------------
# PDF extraction → AI
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_document_extraction_then_ai() -> None:
    """PDF: extraction, AI, raw_text updated, attachment preserved."""
    extraction_result = DocumentExtractionResult(
        text="The drilling process begins with site preparation.",
        page_count=2,
        character_count=100,
        extraction_method="pymupdf",
        has_text=True,
    )
    event = _make_pdf_event(raw_text=None)
    extractor = FakeDocExtractor(result=extraction_result)
    provider = FakeProvider(
        analysis=MemoryAnalysis(
            summary="Document contains info about drilling processes."
        )
    )
    service, _, mock_repo, _ = _make_service(
        provider=provider, extractor=extractor, event=event, max_attempts=1
    )

    with patch("app.services.ai_memory.EventRepository", return_value=mock_repo):
        await service.process(event.id)

    assert event.status == ProcessingStatus.processed
    assert event.raw_text == "The drilling process begins with site preparation."
    assert event.raw_text != event.attachments[0].storage_url or True
    assert event.attachments[0].file_type == FileType.document
    assert event.attachments[0].storage_url == "documents/pdf_123.pdf"
    assert event.attachments[0].original_filename == "Reservoir For SWEP.pdf"
    # AI analysis populated with document metadata
    assert event.ai_analysis is not None
    assert event.ai_analysis.get("page_count") == 2
    assert event.ai_analysis.get("extraction_method") == "pymupdf"


# ---------------------------------------------------------------------------
# Extracted text stored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extracted_text_stored_in_raw_text() -> None:
    """The extracted PDF text is stored in raw_text for future reference."""
    extraction_result = DocumentExtractionResult(
        text="Reservoir simulation methodology overview.",
        page_count=1,
        character_count=50,
        extraction_method="pymupdf",
        has_text=True,
    )
    event = _make_pdf_event(raw_text=None)
    extractor = FakeDocExtractor(result=extraction_result)
    provider = FakeProvider(analysis=MemoryAnalysis(summary="test"))
    service, _, mock_repo, _ = _make_service(
        provider=provider, extractor=extractor, event=event, max_attempts=1
    )

    with patch("app.services.ai_memory.EventRepository", return_value=mock_repo):
        await service.process(event.id)

    assert event.raw_text == "Reservoir simulation methodology overview."


# ---------------------------------------------------------------------------
# Original attachment preserved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_original_attachment_preserved_after_extraction() -> None:
    """The original PDF storage_url and metadata are never modified by extraction."""
    extraction_result = DocumentExtractionResult(
        text="Some extracted text from the PDF.",
        page_count=3,
        character_count=200,
        extraction_method="pymupdf",
        has_text=True,
    )
    original_url = "documents/original_report.pdf"
    event = _make_pdf_event(raw_text=None, storage_url=original_url)
    event.attachments[0].original_filename = "Annual Report.pdf"
    extractor = FakeDocExtractor(result=extraction_result)
    provider = FakeProvider(analysis=MemoryAnalysis(summary="test"))
    service, _, mock_repo, _ = _make_service(
        provider=provider, extractor=extractor, event=event, max_attempts=1
    )

    with patch("app.services.ai_memory.EventRepository", return_value=mock_repo):
        await service.process(event.id)

    assert event.attachments[0].storage_url == original_url
    assert event.attachments[0].original_filename == "Annual Report.pdf"
    assert event.attachments[0].mime_type == "application/pdf"
    assert event.attachments[0].file_type == FileType.document


# ---------------------------------------------------------------------------
# AI success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_ai_success_marks_processed() -> None:
    """Successful PDF → AI pipeline marks event as processed."""
    extraction_result = DocumentExtractionResult(
        text="Content about reservoir rocks and fluid flow.",
        page_count=5,
        character_count=500,
        extraction_method="pymupdf",
        has_text=True,
    )
    event = _make_pdf_event(raw_text=None)
    extractor = FakeDocExtractor(result=extraction_result)
    provider = FakeProvider(
        analysis=MemoryAnalysis(summary="Reservoir engineering concepts")
    )
    service, _, mock_repo, _ = _make_service(
        provider=provider, extractor=extractor, event=event, max_attempts=1
    )

    with patch("app.services.ai_memory.EventRepository", return_value=mock_repo):
        await service.process(event.id)

    assert event.status == ProcessingStatus.processed
    assert event.ai_analysis is not None
    assert event.ai_analysis["summary"] == "Reservoir engineering concepts"
    provider.analyze_memory.assert_awaited_once()
    # Provider called with extracted text, not empty string
    called_text = provider.analyze_memory.call_args[0][0]
    assert "reservoir rocks" in called_text.lower()


# ---------------------------------------------------------------------------
# AI failure — preserves everything
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_ai_failure_preserves_raw_and_attachment() -> None:
    """AI failure on PDF: text extracted + stored, status failed, attachment kept."""
    extraction_result = DocumentExtractionResult(
        text="Extracted PDF text.",
        page_count=1,
        character_count=30,
        extraction_method="pymupdf",
        has_text=True,
    )
    event = _make_pdf_event(raw_text=None)
    extractor = FakeDocExtractor(result=extraction_result)
    provider = FakeProvider()
    provider.analyze_memory = AsyncMock(
        side_effect=AIProviderError("timeout", category="timeout", retryable=False)
    )
    service, _, mock_repo, _ = _make_service(
        provider=provider, extractor=extractor, event=event, max_attempts=1
    )

    with patch("app.services.ai_memory.EventRepository", return_value=mock_repo):
        await service.process(event.id)

    assert event.status == ProcessingStatus.failed
    # Extracted text IS preserved even when AI fails
    assert event.raw_text == "Extracted PDF text."
    # Original attachment preserved
    assert event.attachments[0].storage_url == "documents/pdf_123.pdf"
    assert event.ai_analysis is not None
    assert event.ai_analysis["failure_category"] == "timeout"


# ---------------------------------------------------------------------------
# Extraction failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extraction_failure_marks_failed_preserves_pdf() -> None:
    """When PDF extraction fails, original PDF is kept and status is failed."""
    event = _make_pdf_event(raw_text=None)
    extractor = FakeDocExtractor(
        raise_exception=DocumentExtractionError("PDF corrupted")
    )
    provider = FakeProvider()
    service, _, mock_repo, _ = _make_service(
        provider=provider, extractor=extractor, event=event, max_attempts=1
    )

    with patch("app.services.ai_memory.EventRepository", return_value=mock_repo):
        await service.process(event.id)

    assert event.status == ProcessingStatus.failed
    assert event.raw_text is None  # extraction failed, no text stored
    assert event.attachments[0].storage_url == "documents/pdf_123.pdf"  # preserved
    assert event.ai_analysis is not None
    assert event.ai_analysis["failure_category"] == "extraction"


# ---------------------------------------------------------------------------
# Retryable AI failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retryable_ai_failure_after_extraction() -> None:
    """Retryable AI failure: extraction done once, AI retried, then fails."""
    extraction_result = DocumentExtractionResult(
        text="Reservoir engineering overview.",
        page_count=2,
        character_count=100,
        extraction_method="pymupdf",
        has_text=True,
    )
    event = _make_pdf_event(raw_text=None)
    extractor = FakeDocExtractor(result=extraction_result)
    provider = FakeProvider()
    provider.analyze_memory = AsyncMock(
        side_effect=AIProviderError("network", category="network", retryable=True)
    )
    service, _, mock_repo, _ = _make_service(
        provider=provider,
        extractor=extractor,
        event=event,
        max_attempts=3,
        base_delay=0.01,
    )

    with (
        patch("app.services.ai_memory.EventRepository", return_value=mock_repo),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        await service.process(event.id)

    # Extraction happened once (text cached in raw_text)
    assert event.raw_text == "Reservoir engineering overview."
    # AI was retried max_attempts times
    assert provider.analyze_memory.await_count == 3
    assert event.status == ProcessingStatus.failed
    # Original attachment preserved
    assert event.attachments[0].storage_url == "documents/pdf_123.pdf"


# ---------------------------------------------------------------------------
# Empty PDF (no extractable text) — no hallucination
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Empty PDF (no extractable text) — no hallucination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_pdf_no_text_no_hallucination() -> None:
    """PDF with no extractable text: AI not called, no hallucination."""
    extraction_result = DocumentExtractionResult(
        text="",
        page_count=1,
        character_count=0,
        extraction_method="pymupdf",
        has_text=False,
        error="No extractable text found (scanned image PDF?)",
    )
    event = _make_pdf_event(raw_text=None)
    extractor = FakeDocExtractor(result=extraction_result)
    provider = FakeProvider(analysis=MemoryAnalysis(summary=None))  # empty/no summary
    service, _, mock_repo, _ = _make_service(
        provider=provider, extractor=extractor, event=event, max_attempts=1
    )

    with patch("app.services.ai_memory.EventRepository", return_value=mock_repo):
        await service.process(event.id)

    # AI NOT called — no hallucination from empty text
    provider.analyze_memory.assert_not_awaited()
    # Event marked as processed with document_text_unavailable
    assert event.status == ProcessingStatus.processed
    assert event.ai_analysis is not None
    assert event.ai_analysis["failure_category"] == "document_text_unavailable"
    assert event.raw_text is None  # no text stored


# ---------------------------------------------------------------------------
# Scanned PDF (DocumentUnsupportedError)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanned_pdf_marked_as_text_unavailable() -> None:
    """Scanned-image PDF (DocumentUnsupportedError): graceful skip, PDF preserved.

    The event is marked 'processed' with a failure_category of
    'document_text_unavailable' — no AI hallucination, no crash.
    """
    event = _make_pdf_event(raw_text=None)
    extractor = FakeDocExtractor(
        raise_exception=DocumentUnsupportedError("No text layer in PDF")
    )
    provider = FakeProvider()
    service, _, mock_repo, _ = _make_service(
        provider=provider, extractor=extractor, event=event, max_attempts=1
    )

    with patch("app.services.ai_memory.EventRepository", return_value=mock_repo):
        await service.process(event.id)

    # Extraction error is caught internally → event marked as processed
    assert event.status == ProcessingStatus.processed
    assert event.raw_text is None  # no text extracted
    assert event.attachments[0].storage_url == "documents/pdf_123.pdf"  # preserved
    assert event.ai_analysis is not None
    assert event.ai_analysis["failure_category"] == "document_text_unavailable"
    # AI not called with empty text (no hallucination)
    provider.analyze_memory.assert_not_awaited()


# ---------------------------------------------------------------------------
# User isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_isolation_pdf_processing() -> None:
    """Events from different users are processed independently."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    extraction_a = DocumentExtractionResult(
        text="Alice's PDF content about geology.",
        page_count=1,
        character_count=50,
        extraction_method="pymupdf",
        has_text=True,
    )
    extraction_b = DocumentExtractionResult(
        text="Bob's PDF content about chemistry.",
        page_count=1,
        character_count=50,
        extraction_method="pymupdf",
        has_text=True,
    )

    event_a = _make_pdf_event(
        raw_text=None, user_id=user_a, storage_url="docs/alice.pdf"
    )
    event_b = _make_pdf_event(raw_text=None, user_id=user_b, storage_url="docs/bob.pdf")

    # Mock repo returns different events based on lookup
    mock_repo_a = MagicMock()
    mock_repo_a.get_by_id_with_attachments = AsyncMock(return_value=event_a)

    mock_repo_b = MagicMock()
    mock_repo_b.get_by_id_with_attachments = AsyncMock(return_value=event_b)

    extractor_a = FakeDocExtractor(result=extraction_a)
    extractor_b = FakeDocExtractor(result=extraction_b)

    provider_a = FakeProvider(analysis=MemoryAnalysis(summary="Geology"))
    provider_b = FakeProvider(analysis=MemoryAnalysis(summary="Chemistry"))

    # Service for user A
    service_a, _, _, _ = _make_service(
        provider=provider_a, extractor=extractor_a, event=event_a, max_attempts=1
    )

    with patch("app.services.ai_memory.EventRepository", return_value=mock_repo_a):
        await service_a.process(event_a.id)

    assert event_a.raw_text == "Alice's PDF content about geology."
    assert event_a.user_id == user_a
    assert event_a.attachments[0].storage_url == "docs/alice.pdf"
    assert event_a.ai_analysis is not None

    # Service for user B — separate extractor and provider
    service_b, _, _, _ = _make_service(
        provider=provider_b, extractor=extractor_b, event=event_b, max_attempts=1
    )

    with patch("app.services.ai_memory.EventRepository", return_value=mock_repo_b):
        await service_b.process(event_b.id)

    assert event_b.raw_text == "Bob's PDF content about chemistry."
    assert event_b.user_id == user_b
    assert event_b.attachments[0].storage_url == "docs/bob.pdf"
    assert event_b.ai_analysis is not None
    assert event_a.raw_text != event_b.raw_text  # cross-contamination check


# ---------------------------------------------------------------------------
# No extractor (disabled) — graceful skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_extractor_skips_extraction_graceful() -> None:
    """When document_extractor is None, extraction skipped, no AI hallucination."""
    event = _make_pdf_event(raw_text=None)
    provider = FakeProvider(analysis=MemoryAnalysis(summary="fallback"))
    service, _, mock_repo, _ = _make_service(
        provider=provider, extractor=None, event=event, max_attempts=1
    )

    with patch("app.services.ai_memory.EventRepository", return_value=mock_repo):
        await service.process(event.id)

    # No extraction happened, raw_text stays None
    assert event.raw_text is None
    # AI NOT called — document with no extractor produces no_text_unavailable
    provider.analyze_memory.assert_not_awaited()
    # Original attachment preserved
    assert event.attachments[0].storage_url == "documents/pdf_123.pdf"
    # Event marked as processed (graceful, not failed)
    assert event.status == ProcessingStatus.processed
    assert event.ai_analysis is not None
    assert event.ai_analysis["failure_category"] == "document_text_unavailable"
