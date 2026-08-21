"""Prompt for longitudinal memory analysis across multiple events."""

from __future__ import annotations

import json
from typing import Any


def build_longitudinal_messages(memories: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build chat messages for cross-memory analysis."""
    memory_json = json.dumps(memories, ensure_ascii=False)
    system = (
        "You analyze a student's captured memories over time to identify "
        "topics, progression, and meaningful connections.\n\n"
        "STRICT RULES:\n"
        "- ONLY use information explicitly present in the supplied memories.\n"
        "- NEVER invent experiences, skills, tools, problems, achievements, "
        "dates, or relationships.\n"
        "- Every topic MUST include evidence referencing event_id and summary "
        "from actual memories.\n"
        "- Only create connections when there is clear thematic or conceptual "
        "overlap between specific memories.\n"
        "- Do NOT connect every memory — only meaningful relationships.\n"
        "- If evidence is insufficient, set insufficient_evidence to true and "
        "return empty topics/connections.\n\n"
        "Return JSON with this schema:\n"
        "{\n"
        '  "insufficient_evidence": boolean,\n'
        '  "insight_summary": string or null,\n'
        '  "topics": [\n'
        "    {\n"
        '      "topic": string,\n'
        '      "category": string or null,\n'
        '      "status": "emerging" | "developing" | "established",\n'
        '      "trend": "new" | "growing" | "stable" | "declining",\n'
        '      "evidence": [{"event_id": string, "event_date": string, '
        '"summary": string}],\n'
        '      "progression": [string]\n'
        "    }\n"
        "  ],\n"
        '  "connections": [\n'
        "    {\n"
        '      "source_event_id": string,\n'
        '      "target_event_id": string,\n'
        '      "connection_type": "CONTINUES" | "EXPANDS" | "REFLECTS" | '
        '"SOLVES" | "FOLLOWS_FROM" | "RELATES_TO",\n'
        '      "explanation": string\n'
        "    }\n"
        "  ]\n"
        "}"
    )
    user = f"Analyze these memories chronologically:\n\n{memory_json}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
