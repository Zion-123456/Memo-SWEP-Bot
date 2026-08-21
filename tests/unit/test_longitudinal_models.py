"""Unit tests for longitudinal AI models validation."""

from __future__ import annotations

from app.ai.longitudinal_models import (
    KnowledgeTopicAnalysis,
    LongitudinalAnalysisResult,
    MemoryConnectionCandidate,
    MemoryQueryAnswer,
    ProgressNarrative,
    TopicEvidence,
    WeeklyReflectionContent,
)


def test_topic_evidence_requires_event_id_and_summary() -> None:
    assert TopicEvidence.from_dict({"event_id": "abc"}) is None
    assert TopicEvidence.from_dict({"summary": "learned drilling"}) is None
    ev = TopicEvidence.from_dict(
        {"event_id": "abc", "summary": "Learned drilling basics", "event_date": "2026-01-01"}
    )
    assert ev is not None
    assert ev.event_id == "abc"


def test_longitudinal_result_rejects_topics_without_evidence() -> None:
    result = LongitudinalAnalysisResult.from_dict(
        {
            "topics": [
                {
                    "topic": "Drilling",
                    "evidence": [],
                }
            ],
            "connections": [],
        }
    )
    assert result.topics == []


def test_longitudinal_result_accepts_valid_topic() -> None:
    result = LongitudinalAnalysisResult.from_dict(
        {
            "topics": [
                {
                    "topic": "Drilling",
                    "status": "developing",
                    "trend": "growing",
                    "evidence": [
                        {
                            "event_id": "e1",
                            "summary": "Learned drilling basics",
                            "event_date": "2026-01-01",
                        }
                    ],
                    "progression": ["Fundamentals", "Application"],
                }
            ],
            "connections": [
                {
                    "source_event_id": "e1",
                    "target_event_id": "e2",
                    "connection_type": "EXPANDS",
                    "explanation": "Second memory builds on first",
                }
            ],
        }
    )
    assert len(result.topics) == 1
    assert result.topics[0].topic == "Drilling"
    assert len(result.connections) == 1


def test_progress_narrative_insufficient_evidence_message() -> None:
    text = ProgressNarrative(insufficient_evidence=True).to_telegram_text()
    assert "enough captured evidence" in text.lower()


def test_weekly_reflection_insufficient_evidence_message() -> None:
    text = WeeklyReflectionContent(insufficient_evidence=True).to_telegram_text(memory_count=0, active_days=0)
    assert "not enough memories" in text.lower()



def test_memory_query_answer_from_dict() -> None:
    answer = MemoryQueryAnswer.from_dict(
        {
            "answer": "You learned about drilling.",
            "evidence_event_ids": ["e1"],
            "insufficient_evidence": False,
        }
    )
    assert answer.answer.startswith("You learned")
    assert answer.evidence_event_ids == ["e1"]


def test_connection_candidate_requires_all_fields() -> None:
    assert MemoryConnectionCandidate.from_dict({"source_event_id": "a"}) is None
