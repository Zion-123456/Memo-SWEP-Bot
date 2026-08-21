"""Pydantic schemas for Event request and response shapes."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.models.event import EventSource, PayloadType, ProcessingStatus
from app.schemas.attachment import AttachmentResponse


class EventCreate(BaseModel):
    """Schema for creating a new Event."""

    user_id: uuid.UUID
    event_date: date | None = Field(default=None, description="Defaults to today if omitted.")
    source_type: EventSource = Field(default=EventSource.api)
    payload_type: PayloadType = Field(default=PayloadType.text)
    raw_text: str | None = Field(default=None)
    raw_content: str | None = Field(default=None)
    payload_metadata: dict[str, Any] | None = Field(default=None)


class EventResponse(BaseModel):
    """Full Event representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    event_date: date
    captured_at: datetime
    source_type: EventSource
    payload_type: PayloadType
    raw_text: str | None
    status: ProcessingStatus
    payload_metadata: dict[str, Any] | None
    ai_analysis: dict[str, Any] | None
    is_deleted: bool
    attachments: list[AttachmentResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def raw_content(self) -> str | None:
        return self.raw_text

    @computed_field
    @property
    def processing_status(self) -> ProcessingStatus:
        return self.status


class EventListResponse(BaseModel):
    """Paginated list of Events."""

    items: list[EventResponse]
    total: int
    page: int
    page_size: int


class EventDeleteResponse(BaseModel):
    """Confirmation payload for Event deletion."""

    id: uuid.UUID
    message: str = "Event soft-deleted successfully."


class UserInsight(BaseModel):
    """A single AI-processed event summary for insights views."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_date: date
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    solutions: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)
    confidence: float | None = None

    @field_validator("skills", "tools", "problems", "solutions", "lessons", mode="before")
    @classmethod
    def _ensure_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(i) for i in v]
        return []


class UserInsightsResponse(BaseModel):
    """Aggregated AI insights for a user."""

    user_id: uuid.UUID
    total_memories: int
    analyzed_memories: int
    insights: list[UserInsight]
