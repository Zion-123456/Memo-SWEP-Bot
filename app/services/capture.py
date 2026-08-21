"""Capture service — orchestrates memory capture (store, persist, rollback)."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

import structlog

from app.core.exceptions import DomainValidationError
from app.models.attachment import FileType
from app.models.event import Event, PayloadType, ProcessingStatus, SourceType
from app.repositories.attachment import AttachmentRepository
from app.repositories.event import EventRepository
from app.storage.exceptions import StorageError
from app.storage.provider import StorageProvider

logger = structlog.get_logger(__name__)


@dataclass
class MediaPayload:
    """Represents a media item to be downloaded and attached to an Event."""

    file_bytes: bytes
    filename: str
    content_type: str
    file_type: FileType
    telegram_file_id: str
    duration_seconds: int | None = None
    width: int | None = None
    height: int | None = None


@dataclass
class CaptureRequest:
    """Request payload for capturing a new memory."""

    user_id: uuid.UUID
    event_date: date
    payload_type: PayloadType
    source_type: SourceType = SourceType.telegram
    raw_text: str | None = None
    media_items: list[MediaPayload] = field(default_factory=list)
    payload_metadata: dict[str, Any] | None = None
    captured_at: datetime | None = None
    media_group_id: str | None = None

    @property
    def raw_content(self) -> str | None:
        """Backward-compatible alias for the planned Sprint 2 naming."""
        return self.raw_text

    @raw_content.setter
    def raw_content(self, value: str | None) -> None:
        self.raw_text = value


@dataclass
class CaptureResult:
    """Result payload after capturing a memory."""

    event: Event
    attachments_count: int


class CaptureService:
    """Unified service for capturing student memories into Events and Attachments."""

    def __init__(
        self,
        event_repo: EventRepository,
        attachment_repo: AttachmentRepository,
        storage_provider: StorageProvider,
    ) -> None:
        self._event_repo = event_repo
        self._attachment_repo = attachment_repo
        self._storage = storage_provider

    async def _rollback_capture(self, stored_urls: list[str]) -> None:
        """Rollback the current transaction and clean up any staged files."""
        await self._event_repo.session.rollback()
        for storage_url in reversed(stored_urls):
            try:
                await self._storage.delete(storage_url)
            except Exception as cleanup_exc:  # pragma: no cover - best effort cleanup
                logger.warning(
                    "capture.cleanup_failed",
                    storage_url=storage_url,
                    error=str(cleanup_exc),
                )

    async def capture(self, req: CaptureRequest) -> CaptureResult:
        """Capture a memory, store media files, and persist records atomically.

        Args:
            req: CaptureRequest containing user_id, payload_type, text, and media.

        Returns:
            CaptureResult with persisted Event and attachment count.
        """
        if not req.raw_text and not req.media_items:
            raise DomainValidationError("Cannot capture an empty memory without text or attachments.")

        resolved_payload_type = (
            PayloadType.multimodal
            if req.media_group_id and len(req.media_items) > 1
            else req.payload_type
        )
        payload_metadata = dict(req.payload_metadata or {})
        if req.media_group_id:
            payload_metadata.setdefault("telegram_media_group_id", req.media_group_id)

        saved_attachments_count = 0
        stored_urls: list[str] = []
        date_folder = req.event_date.strftime("%Y/%m/%d")
        event: Event | None = None

        try:
            event = await self._event_repo.create(
                {
                    "user_id": req.user_id,
                    "event_date": req.event_date,
                    "captured_at": req.captured_at or datetime.now(timezone.utc),
                    "source_type": req.source_type,
                    "payload_type": resolved_payload_type,
                    "raw_text": req.raw_text,
                    "status": ProcessingStatus.pending,
                    "payload_metadata": payload_metadata or None,
                }
            )

            for item in req.media_items:
                checksum = hashlib.sha256(item.file_bytes).hexdigest()
                storage_url = await self._storage.store(
                    data=item.file_bytes,
                    filename=item.filename,
                    content_type=item.content_type,
                    subfolder=date_folder,
                )
                stored_urls.append(storage_url)

                await self._attachment_repo.create(
                    {
                        "event_id": event.id,
                        "file_type": item.file_type,
                        "telegram_file_id": item.telegram_file_id,
                        "storage_url": storage_url,
                        "original_filename": item.filename,
                        "mime_type": item.content_type,
                        "file_size": len(item.file_bytes),
                        "duration_seconds": item.duration_seconds,
                        "width": item.width,
                        "height": item.height,
                        "checksum": checksum,
                        "downloaded_at": datetime.now(timezone.utc),
                    }
                )
                saved_attachments_count += 1

            logger.info(
                "capture.success",
                event_id=str(event.id),
                user_id=str(req.user_id),
                payload_type=resolved_payload_type.value,
                attachments=saved_attachments_count,
            )
            return CaptureResult(event=event, attachments_count=saved_attachments_count)

        except DomainValidationError:
            raise
        except Exception as exc:
            await self._rollback_capture(stored_urls)
            logger.error(
                "capture.failed",
                event_id=str(event.id) if event else None,
                user_id=str(req.user_id),
                error=str(exc),
            )
            if isinstance(exc, StorageError):
                raise
            raise StorageError("Capture transaction failed.", details=str(exc)) from exc
