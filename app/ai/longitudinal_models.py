"""Structured models for Sprint 4 longitudinal memory intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self


@dataclass
class TopicEvidence:
    """Traceable evidence for a knowledge topic."""

    event_id: str
    event_date: str | None
    summary: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self | None:
        event_id = data.get("event_id")
        summary = data.get("summary")
        if not event_id or not summary:
            return None
        return cls(
            event_id=str(event_id),
            event_date=_coerce_str(data.get("event_date")),
            summary=str(summary).strip(),
        )


@dataclass
class KnowledgeTopicAnalysis:
    """A topic identified across multiple memories."""

    topic: str
    category: str | None = None
    status: str = "developing"
    trend: str = "growing"
    evidence: list[TopicEvidence] = field(default_factory=list)
    progression: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self | None:
        topic = _coerce_str(data.get("topic"))
        if not topic:
            return None
        evidence = []
        for item in data.get("evidence") or []:
            if isinstance(item, dict):
                ev = TopicEvidence.from_dict(item)
                if ev:
                    evidence.append(ev)
        progression = [
            str(step).strip()
            for step in (data.get("progression") or [])
            if step is not None and str(step).strip()
        ]
        return cls(
            topic=topic,
            category=_coerce_str(data.get("category")),
            status=_coerce_str(data.get("status")) or "developing",
            trend=_coerce_str(data.get("trend")) or "growing",
            evidence=evidence,
            progression=progression,
        )


@dataclass
class MemoryConnectionCandidate:
    """A proposed connection between two memories."""

    source_event_id: str
    target_event_id: str
    connection_type: str
    explanation: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self | None:
        source = data.get("source_event_id")
        target = data.get("target_event_id")
        explanation = _coerce_str(data.get("explanation"))
        conn_type = _coerce_str(data.get("connection_type"))
        if not source or not target or not explanation or not conn_type:
            return None
        return cls(
            source_event_id=str(source),
            target_event_id=str(target),
            connection_type=conn_type.upper(),
            explanation=explanation,
        )


@dataclass
class LongitudinalAnalysisResult:
    """Validated output from longitudinal AI analysis."""

    topics: list[KnowledgeTopicAnalysis] = field(default_factory=list)
    connections: list[MemoryConnectionCandidate] = field(default_factory=list)
    insight_summary: str | None = None
    insufficient_evidence: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        topics = []
        for item in data.get("topics") or []:
            if isinstance(item, dict):
                topic = KnowledgeTopicAnalysis.from_dict(item)
                if topic and topic.evidence:
                    topics.append(topic)
        connections = []
        for item in data.get("connections") or []:
            if isinstance(item, dict):
                conn = MemoryConnectionCandidate.from_dict(item)
                if conn:
                    connections.append(conn)
        return cls(
            topics=topics,
            connections=connections,
            insight_summary=_coerce_str(data.get("insight_summary")),
            insufficient_evidence=bool(data.get("insufficient_evidence")),
        )


@dataclass
class ProgressNarrative:
    """Evidence-based progress narrative sections."""

    title: str = "Your Progress So Far"
    overview: str = ""
    learning: list[str] = field(default_factory=list)
    activities: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    recent_direction: str | None = None
    evidence: list[str] = field(default_factory=list)
    insufficient_evidence: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            title=_coerce_str(data.get("title")) or "Your Progress So Far",
            overview=_coerce_str(data.get("overview")) or "",
            learning=_string_list(data.get("learning")),
            activities=_string_list(data.get("activities")),
            changes=_string_list(data.get("changes")),
            recent_direction=_coerce_str(data.get("recent_direction")),
            evidence=_string_list(data.get("evidence")),
            insufficient_evidence=bool(data.get("insufficient_evidence")),
        )

    def to_telegram_text(self) -> str:
        if self.insufficient_evidence or not self.overview:
            return (
                "📈 Your Progress So Far\n\n"
                "There isn't enough captured evidence yet to describe your "
                "progress. Keep telling Memo what you're learning and working on."
            )
        lines = [f"📈 {self.title}", "", self.overview, ""]
        if self.learning:
            lines.append("📚 What you've been learning:")
            lines.extend(f"  • {item}" for item in self.learning)
            lines.append("")
        if self.activities:
            lines.append("🔧 What you've been doing:")
            lines.extend(f"  • {item}" for item in self.activities)
            lines.append("")
        if self.changes:
            lines.append("🔗 What has changed:")
            lines.extend(f"  • {item}" for item in self.changes)
            lines.append("")
        if self.recent_direction:
            lines.append(f"🧭 Recent direction: {self.recent_direction}")
            lines.append("")
        if self.evidence:
            lines.append("📝 Evidence from your memories:")
            lines.extend(f"  • {item}" for item in self.evidence[:8])
        return "\n".join(lines).strip()


@dataclass
class WeeklyReflectionContent:
    """Structured weekly reflection."""

    summary: str = ""
    learned: list[str] = field(default_factory=list)
    worked_on: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    recurring_themes: list[str] = field(default_factory=list)
    progress_notes: list[str] = field(default_factory=list)
    insufficient_evidence: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            summary=_coerce_str(data.get("summary")) or "",
            learned=_string_list(data.get("learned")),
            worked_on=_string_list(data.get("worked_on")),
            problems=_string_list(data.get("problems")),
            insights=_string_list(data.get("insights")),
            recurring_themes=_string_list(data.get("recurring_themes")),
            progress_notes=_string_list(data.get("progress_notes")),
            insufficient_evidence=bool(data.get("insufficient_evidence")),
        )

    def to_telegram_text(
        self,
        *,
        memory_count: int,
        active_days: int,
        document_count: int = 0,
    ) -> str:
        if self.insufficient_evidence:
            return (
                "🗓 Your Week with Memo\n\n"
                "Not enough memories this week to generate a reflection yet. "
                "Keep capturing what you learn and work on — I'll summarize "
                "your week once there's enough to work with."
            )
        lines = ["🗓 Your Week with Memo", "", self.summary, ""]
        lines.append("Captured:")
        lines.append(f"  • {memory_count} memories")
        lines.append(f"  • {active_days} active days")
        if document_count:
            lines.append(f"  • {document_count} documents")
        lines.append("")
        if self.recurring_themes:
            lines.append("Themes:")
            lines.extend(f"  • {theme}" for theme in self.recurring_themes)
            lines.append("")
        if self.learned:
            lines.append("📚 Learned:")
            lines.extend(f"  • {item}" for item in self.learned)
            lines.append("")
        if self.worked_on:
            lines.append("🔧 Worked on:")
            lines.extend(f"  • {item}" for item in self.worked_on)
            lines.append("")
        if self.problems:
            lines.append("⚠️ Problems:")
            lines.extend(f"  • {item}" for item in self.problems)
            lines.append("")
        if self.progress_notes:
            lines.append("📈 Progress:")
            lines.extend(f"  • {item}" for item in self.progress_notes)
        return "\n".join(lines).strip()


@dataclass
class MemoryQueryAnswer:
    """Grounded answer to a memory query."""

    answer: str
    evidence_event_ids: list[str] = field(default_factory=list)
    insufficient_evidence: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        answer = _coerce_str(data.get("answer")) or ""
        ids = [
            str(item)
            for item in (data.get("evidence_event_ids") or [])
            if item is not None
        ]
        return cls(
            answer=answer,
            evidence_event_ids=ids,
            insufficient_evidence=bool(data.get("insufficient_evidence")),
        )


@dataclass
class ProactiveInsight:
    """An insight Memo can proactively surface."""

    message: str
    topics: list[str] = field(default_factory=list)
    evidence_event_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self | None:
        message = _coerce_str(data.get("message"))
        if not message:
            return None
        return cls(
            message=message,
            topics=_string_list(data.get("topics")),
            evidence_event_ids=[
                str(item)
                for item in (data.get("evidence_event_ids") or [])
                if item is not None
            ],
        )


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if item is not None and str(item).strip()]
