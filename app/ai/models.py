"""Structured analysis result produced by the AI memory extraction pipeline.

The dataclass is the *single* typed representation of an AI analysis. It is
constructed exclusively from validated provider output via :meth:`from_dict`,
which coerces and sanitises the raw JSON so that callers can never observe
invented or wrongly-typed fields.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Self

_STRING_LIST_FIELDS = (
    "activities",
    "skills",
    "tools",
    "projects",
    "people",
    "problems",
    "solutions",
    "lessons",
    "entities",
)


@dataclass
class MemoryAnalysis:
    """Validated, structured analysis of a single memory.

    Every field is optional because the extractor must return empty values
    when information is unavailable rather than inventing it.
    """

    summary: str | None = None
    activities: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    solutions: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    confidence: float | None = None
    model_used: str | None = None
    processed_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self:
        """Build a validated analysis from a (possibly partial) provider JSON dict.

        Unknown keys are ignored, missing list fields default to ``[]``, and
        scalar fields default to ``None``. This is the boundary that guarantees
        callers never see hallucinated/mistyped data.
        """
        data = data or {}
        kwargs: dict[str, Any] = {}
        for name in _STRING_LIST_FIELDS:
            value = data.get(name)
            if isinstance(value, list):
                kwargs[name] = [str(item).strip() for item in value if item is not None]
            else:
                kwargs[name] = []
        kwargs["summary"] = _coerce_str(data.get("summary"))
        confidence = _coerce_float(data.get("confidence"))
        kwargs["confidence"] = confidence if confidence is not None else None
        kwargs["model_used"] = _coerce_str(data.get("model_used"))
        kwargs["processed_at"] = _coerce_str(data.get("processed_at"))
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON/DB-friendly dict (includes processing metadata)."""
        return asdict(self)


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if 0.0 <= number <= 1.0:
        return number
    return None
