"""Prompt for evidence-based progress narratives."""

from __future__ import annotations

import json
from typing import Any


def build_progress_narrative_messages(
    evidence: dict[str, Any],
) -> list[dict[str, str]]:
    """Build chat messages for progress narrative generation."""
    evidence_json = json.dumps(evidence, ensure_ascii=False)
    system = (
        "You write a concise, evidence-based progress narrative for a student "
        "based ONLY on their captured memories and derived topics.\n\n"
        "STRICT RULES:\n"
        "- ONLY use information in the supplied evidence.\n"
        "- NEVER invent experiences, skills, achievements, or progress.\n"
        "- Reference specific evidence from memories.\n"
        "- Do NOT use numeric skill scores or percentages.\n"
        "- If evidence is insufficient, set insufficient_evidence to true.\n"
        "- Write naturally — not like a generic AI summary.\n\n"
        "Return JSON:\n"
        "{\n"
        '  "insufficient_evidence": boolean,\n'
        '  "title": string,\n'
        '  "overview": string,\n'
        '  "learning": [string],\n'
        '  "activities": [string],\n'
        '  "changes": [string],\n'
        '  "recent_direction": string or null,\n'
        '  "evidence": [string]\n'
        "}"
    )
    user = f"Generate a progress narrative from this evidence:\n\n{evidence_json}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
