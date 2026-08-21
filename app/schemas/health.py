"""Pydantic schemas for API health check responses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ServiceHealth(BaseModel):
    """Health status for a single downstream dependency."""

    status: Literal["ok", "degraded", "unavailable"]
    latency_ms: float | None = Field(
        default=None,
        description="Round-trip latency in milliseconds.",
    )
    detail: str | None = Field(
        default=None,
        description="Human-readable detail, populated on failure.",
    )


class HealthResponse(BaseModel):
    """Structured health check response returned by GET /health."""

    status: Literal["ok", "degraded", "unavailable"]
    version: str
    checks: dict[str, ServiceHealth]
