"""Reflection / insight prompt.

Used to produce short, student-facing insight strings (e.g. for /insights or an
optional smart confirmation). Reflection is derived from already-validated
structured analysis and the raw memory; it never re-grounds facts from thin air.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.models import MemoryAnalysis

REFLECTION_SYSTEM_PROMPT = """You are Memo, a concise memory-reflection assistant.
Your job is to write a single, friendly, 1-2 sentence insight string that an AI
could infer from a student's already-structured memory analysis.
- Do NOT invent facts absent from the analysis/memory.
- Mention only skills, tools, activities, or lessons already present.
- Keep it short and warm.
- Return only the insight string, no JSON, no commentary."""


def build_reflection_messages(
    memory: str,
    analysis: MemoryAnalysis | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build chat messages for generating a short insight string.

    Args:
        memory: The student's raw memory text (context only).
        analysis: Either a :class:`MemoryAnalysis` or its dict form.

    Returns:
        A list of ``{"role": ..., "content": ...}`` messages.
    """
    if isinstance(analysis, MemoryAnalysis):
        analysis = analysis.to_dict()
    analysis_text = json.dumps(analysis or {}, ensure_ascii=False)
    user_content = (
        "Write a single concise (1-2 sentence) insight string about what this "
        "student worked on, using only the structured analysis provided. "
        "Do not invent anything.\n\n"
        f"ANALYSIS JSON:\n```json\n{analysis_text}\n```\n\n"
        f"RAW MEMORY:\n\"\"\"\n{memory}\n\"\"\""
    )
    return [
        {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
