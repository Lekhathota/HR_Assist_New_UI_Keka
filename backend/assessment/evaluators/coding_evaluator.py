"""
Architecture for coding and SQL evaluation.

On submit every coding/SQL answer is graded automatically against its visible
and hidden test cases (see assessment/code_execution/grader.py): SQL runs in a
SQLite sandbox, code runs in Judge0 when configured and is otherwise
AI-estimated. Points are awarded per test passed. Only when no grader at all
is available does an answer fall back to "pending_review".
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
    def evaluate(self, question: dict[str, Any], answer: str, language: str = "") -> CodingEvaluationResult:
        """Evaluate a single coding or SQL response."""


class StubCodingEvaluator(CodingEvaluator):
    """
    Placeholder evaluator: records the answer and marks it for future AI/manual review.
    Does not award points until a real evaluator is plugged in.
    """

    def evaluate(self, question: dict[str, Any], answer: str, language: str = "") -> CodingEvaluationResult:
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


class AutoCodingEvaluator(CodingEvaluator):
    """Runs the answer against the question's test cases and awards points per test passed."""

    def __init__(self, fallback: CodingEvaluator | None = None) -> None:
        self.fallback = fallback or StubCodingEvaluator()

    def evaluate(self, question: dict[str, Any], answer: str, language: str = "") -> CodingEvaluationResult:
        from assessment.code_execution.grader import grade_answer, outcome_dicts
        from assessment.code_execution.judge0 import ExecutionUnavailable

        given_answer = str(answer or "").strip()
        if not given_answer:
            return self.fallback.evaluate(question, answer, language)
        raw_type = question.get("question_type") or QuestionType.CODING
        question_type = raw_type.value if hasattr(raw_type, "value") else str(raw_type)
        points = int(question.get("points") or 0)
        try:
            graded = grade_answer(question, given_answer, language)
        except ValueError as exc:  # e.g. a language not allowed for this question
            return CodingEvaluationResult(
                question_id=int(question.get("id") or 0), question_type=question_type, answer=given_answer,
                points_possible=points, feedback=str(exc), evaluation_method="auto", evaluation_status="scored",
            )
        except ExecutionUnavailable as exc:
            pending = self.fallback.evaluate(question, answer, language)
            pending.review_notes = f"Automatic grading unavailable: {exc}"
            return pending
        earned = int(round(points * graded.score_fraction))
        summary = graded.summary()
        if graded.total:
            feedback = f"Passed {graded.passed}/{graded.total} tests ({summary['hidden_passed']}/{summary['hidden_total']} hidden)."
        else:
            feedback = f"AI-estimated score {round(graded.score_fraction * 100)}%."
        if graded.method == "ai_estimated":
            feedback += " AI-estimated (code was not executed)."
        return CodingEvaluationResult(
            question_id=int(question.get("id") or 0), question_type=question_type, answer=given_answer,
            points_possible=points, points_earned=earned,
            is_correct=graded.score_fraction >= 0.999, feedback=feedback,
            evaluation_method=graded.method, evaluation_status="scored", review_notes=graded.feedback,
            metadata={**summary, "tests": outcome_dicts(graded)},
        )


DEFAULT_CODING_EVALUATOR: CodingEvaluator = AutoCodingEvaluator()
