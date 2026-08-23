"""Load and resolve the static SWEP MVP context files.

The loader deliberately keeps shared context separate from a student's
personal experience. It is used to retrieve safe memory prompts and to give
the AI verified background, never to prove that a student performed an act.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "swep"


class SwepContext:
    """In-memory read-only view over the four Memo SWEP JSON artifacts."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self.buildings = self._load("building_context.json")
        self.requirements = self._load("logbook_requirements.json")
        self.personalization = self._load("personalization_rules.json")
        self.generation = self._load("generation_context.json")

    def _load(self, filename: str) -> dict[str, Any]:
        path = self.data_dir / filename
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else {}

    def building_options(self) -> list[tuple[str, str]]:
        return [
            (str(item.get("building_id", "")), str(item.get("building_name", "")))
            for item in self.buildings.get("buildings", [])
            if item.get("building_id") and item.get("building_name")
        ]

    def get_building(self, building_id: str) -> dict[str, Any] | None:
        for item in self.buildings.get("buildings", []):
            if item.get("building_id") == building_id:
                return item
        return None

    def find_building(self, text: str) -> dict[str, Any] | None:
        needle = text.strip().lower()
        for item in self.buildings.get("buildings", []):
            name = str(item.get("building_name", "")).lower()
            ident = str(item.get("building_id", "")).lower()
            if needle == ident or needle == name or needle in name:
                return item
        return None

    @staticmethod
    def phase_for_date(day: date) -> str:
        """Return the MVP SWEP phase for the known 2026 programme timeline."""
        if day <= date(2026, 7, 28):
            return "initial_orientation"
        if day <= date(2026, 8, 17):
            return "department_rotation"
        if day <= date(2026, 8, 21):
            return "second_phase_orientation"
        return "specialized_project"

    def safe_building_context(self, building_id: str) -> dict[str, Any]:
        """Return only context useful for generation; identity is retained."""
        item = self.get_building(building_id) or {}
        return {
            "building_id": item.get("building_id"),
            "building_name": item.get("building_name"),
            "rotation_type": item.get("rotation_type"),
            "confidence": item.get("confidence"),
            "topics_taught": item.get("topics_taught", []),
            "activities_or_demonstrations": item.get("activities_or_demonstrations", []),
            "equipment_processes_or_technologies": item.get(
                "equipment_processes_or_technologies", []
            ),
            "facilitators": item.get("facilitators", []),
            "key_things_students_observed": item.get("key_things_students_observed", []),
            "source_context_notes": item.get("source_context_notes", []),
            "critical_rule": (
                "This is shared context only. Do not state that the student performed,
                "
                "used, observed, or completed any item unless the student confirms it."
            ),
        }

    def output_sections(self) -> list[dict[str, str]]:
        return list(self.requirements.get("final_output", {}).get("sections", []))

    def question_limits(self) -> dict[str, Any]:
        return dict(self.requirements.get("question_limits", {}))

    def generation_principles(self) -> dict[str, Any]:
        return dict(self.generation.get("generation_context", {}).get("generation_principles", {}))

    def prompt_bundle(
        self,
        *,
        day: str,
        phase: str,
        building: dict[str, Any] | None,
        student_input: str,
        personal_answers: list[str],
    ) -> dict[str, Any]:
        return {
            "date": day,
            "swep_phase": phase,
            "selected_building": building or {},
            "shared_building_context": self.safe_building_context(
                str(building.get("building_id")) if building else ""
            ) if building else {},
            "logbook_requirements": self.requirements.get("daily_logbook", {}),
            "personalization_rules": self.personalization,
            "generation_context": self.generation.get("generation_context", {}),
            "student_input": student_input,
            "personal_answers": personal_answers,
        }
