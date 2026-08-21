"""Pydantic schemas for Sprint 4 growth and intelligence API."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class TopicEvidenceSchema(BaseModel):
    event_id: str
    event_date: str | None = None
    summary: str


class KnowledgeTopicResponse(BaseModel):
    id: uuid.UUID
    topic: str
    category: str | None = None
    first_seen: date
    last_seen: date
    memory_count: int
    status: str
    trend: str
    evidence: list[TopicEvidenceSchema] = Field(default_factory=list)
    progression: list[str] | None = None

    model_config = {"from_attributes": True}


class KnowledgeTopicsListResponse(BaseModel):
    user_id: uuid.UUID
    topics: list[KnowledgeTopicResponse]
    total: int


class MemoryConnectionResponse(BaseModel):
    id: uuid.UUID
    source_event_id: uuid.UUID
    target_event_id: uuid.UUID
    connection_type: str
    explanation: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MemoryConnectionsListResponse(BaseModel):
    user_id: uuid.UUID
    connections: list[MemoryConnectionResponse]
    total: int


class ProgressNarrativeResponse(BaseModel):
    user_id: uuid.UUID
    title: str
    overview: str
    learning: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    recent_direction: str | None = None
    evidence: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False


class WeeklyReflectionResponse(BaseModel):
    user_id: uuid.UUID
    week_start: date
    week_end: date
    summary: str
    learned: list[str] = Field(default_factory=list)
    worked_on: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    recurring_themes: list[str] = Field(default_factory=list)
    progress_notes: list[str] = Field(default_factory=list)
    memory_count: int = 0
    active_days: int = 0
    insufficient_evidence: bool = False


class MemoryQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    time_range: str | None = None
    topic: str | None = None


class MemoryQueryResponse(BaseModel):
    user_id: uuid.UUID
    query: str
    answer: str
    insufficient_evidence: bool = False
