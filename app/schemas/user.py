"""Pydantic schemas for User request and response shapes.

Schemas are deliberately kept separate from ORM models. This decoupling means
the API surface can evolve independently of the database schema — a common
requirement as the product grows.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class UserBase(BaseModel):
    """Fields shared across all User schema variants."""

    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    university: str = Field(..., min_length=1, max_length=500)
    department: str = Field(..., min_length=1, max_length=500)
    programme: str = Field(..., min_length=1, max_length=500)
    company: str = Field(..., min_length=1, max_length=500)
    supervisor: str | None = Field(default=None, max_length=500)
    start_date: date
    end_date: date


class UserCreate(UserBase):
    """Schema for creating a new User from the onboarding flow."""

    telegram_id: int = Field(..., gt=0)


class UserUpdate(BaseModel):
    """Schema for updating an existing User profile.

    All fields are optional — only provided fields are applied.
    """

    first_name: str | None = Field(default=None, min_length=1, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    university: str | None = Field(default=None, min_length=1, max_length=500)
    department: str | None = Field(default=None, min_length=1, max_length=500)
    programme: str | None = Field(default=None, min_length=1, max_length=500)
    company: str | None = Field(default=None, min_length=1, max_length=500)
    supervisor: str | None = Field(default=None, max_length=500)
    start_date: date | None = None
    end_date: date | None = None


class UserResponse(UserBase):
    """Full User representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    telegram_id: int
    created_at: datetime
    updated_at: datetime
