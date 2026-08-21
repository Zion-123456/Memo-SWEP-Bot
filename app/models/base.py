"""SQLAlchemy declarative base and shared model mixins."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all Memo ORM models.

    All models inherit from this class which provides the metadata registry
    used by Alembic for migration generation.
    """

    # Allow SQLAlchemy to infer Python → SQL type mappings from annotations.
    type_annotation_map: dict[type[Any], Any] = {}


class TimestampMixin:
    """Mixin that adds timezone-aware ``created_at`` and ``updated_at`` columns.

    ``created_at`` is set once at INSERT time via a server-side default.
    ``updated_at`` is set at INSERT and refreshed on every UPDATE via a
    server-side ``onupdate`` expression.

    Both columns are non-nullable and stored with timezone information so they
    represent unambiguous moments in time regardless of the server locale.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
