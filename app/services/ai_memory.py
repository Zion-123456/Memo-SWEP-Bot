"""AI Memory Intelligence service (Sprint 3).

Orchestrates asynchronous AI processing of captured memories:

    CAPTURE -> PRESERVE RAW INPUT -> AI PROCESSING -> STRUCTURED MEMORY

This service contains **no Telegram-specific logic**. Each ``process`` call is a
self-contained unit of work with its own database session, so it can be fired
from a fire-and-forget ``asyncio.create_task`` (the MVP scheduler) today and
later moved to a real worker queue (RQ / Celery / Dramatiq) without changing
the processing boundary.

Invariants enforced here:

* The raw memory (``Event.raw_text``) is **never** deleted or overwritten by
  AI failure. Voice transcripts are only *added* to ``raw_text`` when the audio
  has no caption yet; the original audio attachment is always preserved.
  PDF text extraction similarly only *adds* extracted text to ``raw_text``;
  the original PDF attachment is always preserved.
* AI processing failures mark the event ``failed`` (and remain retryable) but
  leave the captured memory fully intact.
* Provider calls are retried with exponential backoff for retryable errors.
* No API keys or raw memories are logged.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.exceptions import AIError, AIProviderError, AIValidationError
from app.ai.models import MemoryAnalysis
from app.ai.provider import AIProvider
from app.documents.exceptions import DocumentExtractionError, DocumentUnsupportedError
from app.documents.extractor import DocumentTextExtractor
from app.documents.models import DocumentExtractionResult
from app.models.attachment import FileType
from app.models.event import Event, PayloadType, ProcessingStatus
from app.repositories.event import EventRepository
from app.storage.provider import StorageProvider

logger = structlog.get_logger(__name__)

_MAX_ERROR_LEN = 500


class AiMemoryService:
    """Processes captured events through an :class:`AIProvider` asynchronously.

    Args:
       ai_provider: The backend that performs LLM analysis / transcription.
       session_factory: Used to open short-lived sessions for each processing
           step (independent of any request/session that captured the event).
       storage_provider: Used to read media attachments for transcription
           and document text extraction.
       enabled: Master switch; when falsy, ``process``/``schedule`` no-op.
       max_attempts: Number of processing attempts before marking failed.
       base_delay: Base seconds for exponential backoff between retries.
       document_extractor: Optional document text extractor for PDF
           document intelligence. When ``None``, document events simply
           skip PDF text extraction (graceful degradation).
    """

    def __init__(
        self,
        ai_provider: AIProvider,
        session_factory: async_sessionmaker[AsyncSession],
        storage_provider: StorageProvider,
        *,
        enabled: bool = False,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        document_extractor: DocumentTextExtractor | None = None,
        longitudinal_service: Any | None = None,
    ) -> None:
        self._provider = ai_provider
        self._session_factory = session_factory
        self._storage = storage_provider
        self._enabled = enabled
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._doc_extractor = document_extractor
        self._longitudinal = longitudinal_service

    @property
    def enabled(self) -> bool:
        """Whether AI processing is active for this service."""
        return self._enabled

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    # ------------------------------------------------------------------
    # Scheduling (non-blocking entry point)
    # ------------------------------------------------------------------
    def schedule(self, event_id: uuid.UUID) -> None:
        """Fire-and-forget a processing task for an event.

        Must be called from within a running event loop (i.e. after the
        capture transaction has committed). No-ops when AI is disabled or no
        loop is running.
        """
        if not self._enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._safe_process(event_id))

    async def _safe_process(self, event_id: uuid.UUID) -> None:
        """Wrap ``process`` so a background task can never crash the loop."""
        try:
            await self.process(event_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "ai.process_unhandled_failure",
                event_id=str(event_id),
                error_category=type(exc).__name__,
            )

    # ------------------------------------------------------------------
    # Main processing loop
    # ------------------------------------------------------------------
    async def process(self, event_id: uuid.UUID) -> None:
        """Process an event through the AI pipeline with retries.

        Never raises: all failures are recorded on the event as ``failed``.
        """
        if not self._enabled:
            return

        for attempt in range(self._max_attempts):
            try:
                await self._process_once(event_id, attempt)
                return
            except AIValidationError:
                # Invalid JSON won't be fixed by retrying.
                await self._record_failure(
                    event_id, "validation_error", "Invalid AI JSON.", attempt + 1
                )
                return
            except AIProviderError as exc:
                if not exc.retryable or attempt == self._max_attempts - 1:
                    await self._record_failure(
                        event_id, exc.category, str(exc)[:_MAX_ERROR_LEN], attempt + 1
                    )
                    return
                await asyncio.sleep(self._base_delay * (2**attempt))
            except Exception as exc:
                await self._record_failure(
                    event_id, "unexpected", str(exc)[:_MAX_ERROR_LEN], attempt + 1
                )
                return

    async def _process_once(self, event_id: uuid.UUID, attempt: int) -> None:
        started = time.monotonic()
        async with self._session_factory() as session:
            event_repo = EventRepository(session)
            event = await event_repo.get_by_id_with_attachments(event_id)
            if event is None or event.is_deleted:
                return  # Nothing to process.

            # Idempotent: skip events that are already fully analysed.
            if event.status == ProcessingStatus.processed and event.ai_analysis:
                return

            # Mark processing (visible to observers while AI runs).
            event.status = ProcessingStatus.processing
            event.processing_retry_count = (event.processing_retry_count or 0) + 1
            await session.commit()

            # 1. Obtain the text to analyse: raw text, transcript for voice,
            #    or extracted text for documents.
            text = event.raw_text
            doc_metadata: dict[str, Any] = {}
            if not text and event.payload_type == PayloadType.voice:
                text = await self._transcribe_event(event)
                if text:
                    event.raw_text = text
                    await session.commit()

            if not text and event.payload_type == PayloadType.document:
                extraction = await self._extract_document_text(event)
                if extraction.text:
                    text = extraction.text
                    event.raw_text = text
                    await session.commit()
                    doc_metadata = {
                        "page_count": extraction.page_count,
                        "character_count": extraction.character_count,
                        "extraction_method": extraction.extraction_method,
                        "has_text": extraction.has_text,
                    }
                    if extraction.metadata:
                        doc_metadata.update(extraction.metadata)
                elif not extraction.has_text:
                    # Scanned/image-only PDF — no text to analyse, do NOT
                    # send empty text to the AI (prevents hallucination).
                    event.ai_analysis = {
                        "provider": self._provider.provider_name,
                        "model_used": self._provider.default_model,
                        "failure_category": "document_text_unavailable",
                        "processing_seconds": _elapsed(started),
                        **dict(extraction.metadata or {}),
                    }
                    event.status = ProcessingStatus.processed
                    await session.commit()
                    logger.info(
                        "ai.document_no_text_processed",
                        event_id=str(event.id),
                        reason="no_extractable_text",
                    )
                    return

            # 2. Analyse (may raise AIProviderError / AIValidationError).
            #    Document AI follows strict grounding rules: extract ONLY
            #    information explicitly present in the text.
            analysis = await self._provider.analyze_memory(text or "")
            analysis_dict = _analysis_to_dict(
                analysis,
                provider=self._provider.provider_name,
                processing_seconds=_elapsed(started),
            )
            if doc_metadata:
                analysis_dict.update(doc_metadata)

            # 3. Persist structured analysis and mark processed.
            event.ai_analysis = analysis_dict
            event.status = ProcessingStatus.processed
            await session.commit()
            logger.info(
                "ai.processed",
                event_id=str(event.id),
                provider=self._provider.provider_name,
                has_summary=analysis.summary is not None,
            )

            # Sprint 4: schedule longitudinal analysis after successful processing.
            if self._longitudinal is not None:
                self._longitudinal.schedule_after_capture(event.user_id)

    async def _transcribe_event(self, event: Event) -> str:
        """Transcribe a voice event's audio attachment.

        The original audio attachment is never modified here; only its derived
        transcript is returned so the caller may store it in ``raw_text``.
        """
        audio = next(
            (
                a
                for a in event.attachments
                if a.file_type in (FileType.voice, FileType.audio)
            ),
            None,
        )
        if audio is None or not audio.storage_url:
            return ""

        try:
            file_bytes = await self._storage.read(audio.storage_url)
        except Exception as exc:
            logger.warning(
                "ai.transcription_storage_failed",
                event_id=str(event.id),
                error_category=type(exc).__name__,
            )
            raise AIProviderError(
                "Could not read audio attachment for transcription.",
                category="storage",
                retryable=False,
            ) from exc

        filename = audio.original_filename or f"voice_{event.id}.ogg"
        mime_type = audio.mime_type or "audio/ogg"
        try:
            transcript = await self._provider.transcribe_audio(
                file_bytes, filename=filename, mime_type=mime_type
            )
        except AIError as exc:
            logger.warning(
                "ai.transcription_failed",
                event_id=str(event.id),
                category=type(exc).__name__,
            )
            raise AIProviderError(
                "Voice transcription failed.",
                category="transcription",
                retryable=getattr(exc, "retryable", True),
            ) from exc

        logger.info(
            "ai.transcribed",
            event_id=str(event.id),
            chars=len(transcript or ""),
        )
        return transcript or ""

    async def _extract_document_text(self, event: Event) -> DocumentExtractionResult:
        """Extract text from a document attachment (PDF).

        The original document attachment is never modified or deleted here;
        only the *derived* text is returned so the caller may store it in
        ``raw_text``. If no document extractor is configured, or the document
        has no PDF attachment, returns an empty result.

        For scanned-image PDFs (no extractable text), returns a result with
        ``has_text=False`` so the caller can skip sending empty text to the AI.
        """
        if self._doc_extractor is None:
            logger.debug(
                "ai.document_extraction_skipped",
                event_id=str(event.id),
                reason="no_document_extractor",
            )
            return DocumentExtractionResult(
                has_text=False,
                extraction_method="",
                error="document_text_unavailable",
            )

        doc_attachment = next(
            (
                a
                for a in event.attachments
                if a.file_type == FileType.document
                and (a.mime_type or "").startswith("application/pdf")
            ),
            None,
        )
        if doc_attachment is None or not doc_attachment.storage_url:
            logger.debug(
                "ai.document_extraction_skipped",
                event_id=str(event.id),
                reason="no_pdf_attachment",
            )
            return DocumentExtractionResult(
                has_text=False,
                extraction_method="",
                error="document_text_unavailable",
            )

        try:
            file_bytes = await self._storage.read(doc_attachment.storage_url)
        except Exception as exc:
            logger.warning(
                "ai.document_extraction_storage_failed",
                event_id=str(event.id),
                error_category=type(exc).__name__,
            )
            raise AIProviderError(
                "Could not read document attachment for extraction.",
                category="storage",
                retryable=False,
            ) from exc

        filename = doc_attachment.original_filename or f"document_{event.id}.pdf"
        try:
            result = await self._doc_extractor.extract(
                file_bytes,
                filename=filename,
                mime_type=doc_attachment.mime_type or "application/pdf",
            )
        except DocumentUnsupportedError as exc:
            logger.info(
                "ai.document_no_text",
                event_id=str(event.id),
                reason=str(exc),
            )
            return DocumentExtractionResult(
                has_text=False,
                extraction_method=self._doc_extractor.extractor_name,
                error="document_text_unavailable",
            )
        except DocumentExtractionError as exc:
            logger.warning(
                "ai.document_extraction_failed",
                event_id=str(event.id),
                error_category=type(exc).__name__,
            )
            raise AIProviderError(
                "Document text extraction failed.",
                category="extraction",
                retryable=True,
            ) from exc

        logger.info(
            "ai.document_extracted",
            event_id=str(event.id),
            page_count=result.page_count,
            chars=result.character_count,
            has_text=result.has_text,
        )
        return result

    async def _record_failure(
        self,
        event_id: uuid.UUID,
        category: str,
        error: str,
        attempts: int,
    ) -> None:
        """Record an AI failure on the event without touching the raw memory."""
        async with self._session_factory() as session:
            event_repo = EventRepository(session)
            event = await event_repo.get_by_id_with_attachments(event_id)
            if event is None or event.is_deleted:
                return
            # A prior successful pass may have processed the event meanwhile.
            if event.status == ProcessingStatus.processed and event.ai_analysis:
                return
            event.status = ProcessingStatus.failed
            event.ai_analysis = {
                "provider": self._provider.provider_name,
                "model_used": self._provider.default_model,
                "failure_category": category,
                "error": error[:_MAX_ERROR_LEN],
                "retry_count": attempts,
                "processed_at": datetime.now(UTC).isoformat(),
            }
            await session.commit()
            logger.warning(
                "ai.process_failed",
                event_id=str(event.id),
                category=category,
                attempts=attempts,
            )


def _analysis_to_dict(
    analysis: MemoryAnalysis,
    *,
    provider: str,
    processing_seconds: float,
) -> dict[str, object]:
    """Serialise a :class:`MemoryAnalysis` to a JSONB-safe dict."""
    data: dict[str, object] = analysis.to_dict()
    data["provider"] = provider
    data["processing_seconds"] = round(processing_seconds, 3)
    # Guarantee JSON/DB serialisable types (drop any stray non-scalar).
    return {key: value for key, value in data.items() if _is_json_scalar(value)}


def _is_json_scalar(value: object) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(isinstance(item, str) for item in value)
    return False


def _elapsed(started: float) -> float:
    return time.monotonic() - started
