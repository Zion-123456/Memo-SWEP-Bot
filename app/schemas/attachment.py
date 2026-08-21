"""Pydantic schemas for Attachment response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.attachment import FileType


class AttachmentResponse(BaseModel):
    """Full Attachment representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    file_type: FileType
    telegram_file_id: str
    storage_url: str | None = None
    original_filename: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    duration_seconds: int | None = None
    width: int | None = None
    height: int | None = None
    checksum: str | None = None
    downloaded_at: datetime | None = None
    created_at: datetime
