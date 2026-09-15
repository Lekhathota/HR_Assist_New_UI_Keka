"""
Domain models and constants for the Assessment module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AssessmentStatus(str, Enum):
    """Lifecycle states for an assessment assignment."""

    NOT_CREATED = "NOT_CREATED"
    DRAFT = "DRAFT"
    SENT = "SENT"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    PASSED = "PASSED"
    FAILED = "FAILED"

    @classmethod
    def terminal_states(cls) -> frozenset[str]:
        return frozenset({cls.PASSED, cls.FAILED})

    @classmethod
    def submitted_states(cls) -> frozenset[str]:
        """States where the candidate can no longer access or edit answers."""
        return frozenset({cls.COMPLETED, cls.PASSED, cls.FAILED})

    @classmethod
    def editable_states(cls) -> frozenset[str]:
        return frozenset({cls.DRAFT})

    @classmethod
    def candidate_accessible_states(cls) -> frozenset[str]:
        return frozenset({cls.SENT, cls.IN_PROGRESS})


class QuestionType(str, Enum):
    MCQ = "mcq"
    SHORT_ANSWER = "short_answer"
    TRUE_FALSE = "true_false"
    CODING = "coding"
    SQL = "sql"


DEFAULT_PASSING_SCORE = 70
DEFAULT_QUESTION_COUNT = 10
DEFAULT_TOKEN_TTL_DAYS = 7

# Fixed AI generation blueprint
MCQ_COUNT = 10
CODING_COUNT = 2
SQL_COUNT = 1
TOTAL_GENERATED_QUESTIONS = MCQ_COUNT + CODING_COUNT + SQL_COUNT


@dataclass
class AssessmentDocument:
    """MongoDB assessments collection document shape."""

    id: int
    candidate_id: int
    jd_id: int
    recruiter_id: int
    status: str = AssessmentStatus.DRAFT
    title: str = ""
    candidate_name: str = ""
    candidate_email: str = ""
    job_role: str = ""
    access_token: str = ""
    token_expires_at: str | None = None
    passing_score: int = DEFAULT_PASSING_SCORE
    time_limit_minutes: int = 60
    sent_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssessmentDocument:
        return cls(
            id=int(data.get("id") or 0),
            candidate_id=int(data.get("candidate_id") or 0),
            jd_id=int(data.get("jd_id") or 0),
            recruiter_id=int(data.get("recruiter_id") or 0),
            status=str(data.get("status") or AssessmentStatus.DRAFT),
            title=str(data.get("title") or ""),
            candidate_name=str(data.get("candidate_name") or ""),
            candidate_email=str(data.get("candidate_email") or ""),
            job_role=str(data.get("job_role") or ""),
            access_token=str(data.get("access_token") or ""),
            token_expires_at=data.get("token_expires_at"),
            passing_score=int(data.get("passing_score") or DEFAULT_PASSING_SCORE),
            time_limit_minutes=int(data.get("time_limit_minutes") or 60),
            sent_at=data.get("sent_at"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class QuestionDocument:
    """MongoDB questions collection document shape."""

    id: int
    assessment_id: int
    question_text: str
    question_type: str = QuestionType.MCQ
    options: list[str] = field(default_factory=list)
    correct_answer: str = ""
    points: int = 10
    skill_tag: str = ""
    sort_order: int = 0
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuestionDocument:
        return cls(
            id=int(data.get("id") or 0),
            assessment_id=int(data.get("assessment_id") or 0),
            question_text=str(data.get("question_text") or ""),
            question_type=str(data.get("question_type") or QuestionType.MCQ),
            options=list(data.get("options") or []),
            correct_answer=str(data.get("correct_answer") or ""),
            points=int(data.get("points") or 10),
            skill_tag=str(data.get("skill_tag") or ""),
            sort_order=int(data.get("sort_order") or 0),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class CandidateAnswerDocument:
    """MongoDB candidate_answers collection document shape."""

    id: int
    assessment_id: int
    question_id: int
    answer: str = ""
    is_final: bool = False
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class AssessmentResultDocument:
    """MongoDB assessment_results collection document shape."""

    id: int
    assessment_id: int
    candidate_id: int
    jd_id: int
    total_points: int = 0
    earned_points: int = 0
    score_percentage: float = 0.0
    passed: bool = False
    status: str = AssessmentStatus.FAILED
    question_results: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    scored_at: str | None = None
    created_at: str | None = None
