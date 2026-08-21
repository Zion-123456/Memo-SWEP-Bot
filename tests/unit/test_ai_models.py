"""Unit tests for AI memory models and hallucination-prevention."""

from __future__ import annotations

from app.ai.models import MemoryAnalysis, _coerce_float, _coerce_str


# ---------------------------------------------------------------------------
# from_dict / to_dict round-trip
# ---------------------------------------------------------------------------


def test_from_dict_full_valid_data() -> None:
    """A well-formed provider response is parsed into a MemoryAnalysis."""
    data = {
        "summary": "Wired a three-phase motor starter.",
        "activities": ["motor wiring"],
        "skills": ["electrical"],
        "tools": ["multimeter"],
        "projects": ["SWEP placement"],
        "people": ["supervisor"],
        "problems": ["starter kept tripping"],
        "solutions": ["checked overload relay"],
        "lessons": ["always verify voltage first"],
        "entities": ["motor", "starter"],
        "confidence": 0.9,
        "model_used": "openai/gpt-oss-120b",
        "processed_at": "2026-08-09T03:00:00+00:00",
    }
    analysis = MemoryAnalysis.from_dict(data)
    assert analysis.summary == "Wired a three-phase motor starter."
    assert analysis.activities == ["motor wiring"]
    assert analysis.skills == ["electrical"]
    assert analysis.confidence == 0.9
    assert analysis.model_used == "openai/gpt-oss-120b"


def test_from_dict_missing_fields_default_empty() -> None:
    """Missing list fields default to ``[]``, missing scalars to ``None``."""
    analysis = MemoryAnalysis.from_dict({"summary": "Partial data"})
    assert analysis.summary == "Partial data"
    assert analysis.activities == []
    assert analysis.skills == []
    assert analysis.confidence is None
    assert analysis.model_used is None


def test_from_dict_none_input() -> None:
    """``None`` input yields an all-default analysis."""
    analysis = MemoryAnalysis.from_dict(None)
    assert analysis.summary is None
    assert analysis.activities == []
    assert analysis.skills == []
    assert analysis.confidence is None


def test_from_dict_unknown_keys_ignored() -> None:
    """Unknown keys (hallucinated fields) are silently dropped."""
    data = {
        "summary": "OK",
        "invented_field": "should be ignored",
        "company": "Acme Corp",  # must not survive
        "plc_model": "XYZ-123",  # must not survive
    }
    analysis = MemoryAnalysis.from_dict(data)
    result = analysis.to_dict()
    assert "invented_field" not in result
    assert "company" not in result
    assert "plc_model" not in result


def test_from_dict_non_list_fields_become_empty() -> None:
    """If a list field is wrongly typed as a scalar, it becomes ``[]``."""
    analysis = MemoryAnalysis.from_dict({"activities": "not a list"})
    assert analysis.activities == []


def test_from_dict_list_items_coerced_to_str() -> None:
    """Non-string list items are coerced to strings."""
    analysis = MemoryAnalysis.from_dict({"skills": [123, None, True]})
    assert analysis.skills == ["123", "True"]


def test_to_dict_round_trip() -> None:
    """``to_dict`` produces a serialisable dict with all fields."""
    analysis = MemoryAnalysis(
        summary="test",
        activities=["a"],
        skills=["b"],
        confidence=0.5,
    )
    d = analysis.to_dict()
    assert d["summary"] == "test"
    assert d["activities"] == ["a"]
    assert d["skills"] == ["b"]
    assert d["confidence"] == 0.5

    restored = MemoryAnalysis.from_dict(d)
    assert restored.summary == "test"
    assert restored.activities == ["a"]


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def test_coerce_str_none() -> None:
    assert _coerce_str(None) is None


def test_coerce_str_empty() -> None:
    assert _coerce_str("") is None
    assert _coerce_str("   ") is None


def test_coerce_str_value() -> None:
    assert _coerce_str("hello") == "hello"
    assert _coerce_str("  trimmed  ") == "trimmed"


def test_coerce_float_none() -> None:
    assert _coerce_float(None) is None


def test_coerce_float_valid_range() -> None:
    assert _coerce_float(0.0) == 0.0
    assert _coerce_float(1.0) == 1.0
    assert _coerce_float(0.5) == 0.5


def test_coerce_float_out_of_range() -> None:
    assert _coerce_float(1.5) is None
    assert _coerce_float(-0.1) is None


def test_coerce_float_invalid() -> None:
    assert _coerce_float("abc") is None
    assert _coerce_float(None) is None


# ---------------------------------------------------------------------------
# Hallucination prevention — the conveyor motor case
# ---------------------------------------------------------------------------


def test_conveyor_motor_no_invented_specifications() -> None:
    """The extractor must not fabricate voltage, PLC model, sensor type, etc."""
    provider_json = {
        "summary": "Debugged a conveyor motor starter circuit.",
        "activities": ["wired conveyor motor starter"],
        "skills": ["electrical wiring"],
        "tools": ["multimeter"],
        "projects": ["industrial automation placement"],
        "problems": ["starter relay kept tripping"],
        "solutions": ["replaced the overload relay"],
        "lessons": ["check overload before powering"],
        "entities": ["conveyor", "motor", "starter"],
        "confidence": 0.85,
        "model_used": "openai/gpt-oss-120b",
        "processed_at": "2026-08-09T03:00:00+00:00",
        "company": "Acme Corp",
        "plc_model": "Siemens S7-1200",
        "voltage": "480V",
        "sensor_type": "photoelectric",
    }
    analysis = MemoryAnalysis.from_dict(provider_json)
    result = analysis.to_dict()

    # Known fields preserved
    assert "conveyor" in analysis.entities
    assert "motor" in analysis.entities

    # Invented fields must NOT be present
    assert "company" not in result
    assert "plc_model" not in result
    assert "voltage" not in result
    assert "sensor_type" not in result
