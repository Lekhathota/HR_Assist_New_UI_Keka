"""
Architecture for coding and SQL evaluation.

Production flow (future):
  1. Candidate submits assessment.
  2. MCQs are scored immediately.
  3. Coding/SQL answers are queued for AI or manual review via CodingEvaluator.
  4. A follow-up job calls CodingEvaluator.evaluate() and merges points into the result.

This module provides the interface and a stub implementation used until AI review is wired.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from assessment.models import QuestionType


@dataclass
class CodingEvaluationResult:
    question_id: int
    question_type: str
    answer: str
    points_possible: int
    points_earned: int = 0
    is_correct: bool = False
    feedback: str = ""
    evaluation_method: str = "pending_ai"
    evaluation_status: str = "pending_review"
    review_notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question_type": self.question_type,
            "answer": self.answer,
            "is_correct": self.is_correct,
            "points_possible": self.points_possible,
            "points_earned": self.points_earned,
            "feedback": self.feedback,
            "evaluation_method": self.evaluation_method,
            "evaluation_status": self.evaluation_status,
            "review_notes": self.review_notes,
            "metadata": self.metadata,
        }


class CodingEvaluator(ABC):
    """Contract for coding/SQL answer evaluation backends."""

    @abstractmethod
    def evaluate(self, question: dict[str, Any], answer: str) -> CodingEvaluationResult:
        """Evaluate a single coding or SQL response."""


class StubCodingEvaluator(CodingEvaluator):
    """
    Placeholder evaluator: records the answer and marks it for future AI/manual review.
    Does not award points until a real evaluator is plugged in.
    """

    def evaluate(self, question: dict[str, Any], answer: str) -> CodingEvaluationResult:
        question_id = int(question.get("id") or 0)
        raw_type = question.get("question_type") or QuestionType.CODING
        question_type = raw_type.value if hasattr(raw_type, "value") else str(raw_type)
        points = int(question.get("points") or 0)
        given_answer = str(answer or "").strip()

        if not given_answer:
            return CodingEvaluationResult(
                question_id=question_id,
                question_type=question_type,
                answer="",
                points_possible=points,
                feedback="No answer provided.",
                evaluation_status="skipped",
                evaluation_method="auto",
            )

        return CodingEvaluationResult(
            question_id=question_id,
            question_type=question_type,
            answer=given_answer,
            points_possible=points,
            points_earned=0,
            is_correct=False,
            feedback="Response recorded. Pending AI or manual review.",
            evaluation_method="pending_ai",
            evaluation_status="pending_review",
            metadata={"review_queue": True},
        )


# Default evaluator instance; swap for an AI-backed implementation in production.
DEFAULT_CODING_EVALUATOR: CodingEvaluator = StubCodingEvaluator()
