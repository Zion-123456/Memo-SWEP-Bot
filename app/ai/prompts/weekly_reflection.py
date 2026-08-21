"""Prompt for weekly reflection generation."""

from __future__ import annotations

import json
from typing import Any


def build_weekly_reflection_messages(
    evidence: dict[str, Any],
) -> list[dict[str, str]]:
    """Build chat messages for weekly reflection."""
    evidence_json = json.dumps(evidence, ensure_ascii=False)
    system = (
        "You summarize a student's week based ONLY on their captured memories "
        "from that week.\n\n"
        "STRICT RULES:\n"
        "- ONLY use information in the supplied evidence.\n"
        "- NEVER invent activities, learning, or progress.\n"
        "- If fewer than 2 meaningful memories, set insufficient_evidence true.\n\n"
        "Return JSON:\n"
        "{\n"
        '  "insufficient_evidence": boolean,\n'
        '  "summary": string,\n'
        '  "learned": [string],\n'
        '  "worked_on": [string],\n'
        '  "problems": [string],\n'
        '  "insights": [string],\n'
        '  "recurring_themes": [string],\n'
        '  "progress_notes": [string]\n'
        "}"
    )
    user = f"Generate a weekly reflection from:\n\n{evidence_json}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
