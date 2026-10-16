"""
Architecture for coding and SQL evaluation.

On submit every coding/SQL answer is executed against its visible and hidden test
cases (see assessment/code_execution/grader.py): SQL in a SQLite sandbox, code in
Judge0. Marks follow the weights of the tests that pass and the question's scoring
rules (assessment/code_execution/coding_config.py); source code is never compared
with the reference. When the sandbox cannot run the code the answer is recorded as
an infrastructure "execution_error" with no marks decided, so it can be re-graded;
questions without tests fall back to "pending_review".
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
    points_possible: float
    points_earned: float = 0
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
    """Executes the answer against the question's test cases and scores it by the tests that pass."""

    def __init__(self, fallback: CodingEvaluator | None = None) -> None:
        self.fallback = fallback or StubCodingEvaluator()

    def evaluate(self, question: dict[str, Any], answer: str, language: str = "") -> CodingEvaluationResult:
        from assessment.code_execution.coding_config import enabled_cases, score_outcomes
        from assessment.code_execution.grader import grade_answer, outcome_dicts
        from assessment.code_execution.judge0 import ExecutionUnavailable

        given_answer = str(answer or "").strip()
        raw_type = question.get("question_type") or QuestionType.CODING
        question_type = raw_type.value if hasattr(raw_type, "value") else str(raw_type)
        points = float(question.get("points") or 0)
        question_id = int(question.get("id") or 0)
        if not given_answer:
            empty = self.fallback.evaluate(question, answer, language)
            empty.metadata = {**score_outcomes(question, []), "result_status": "not_answered", "language": language}
            return empty
        try:
            graded = grade_answer(question, given_answer, language)
        except ValueError as exc:  # e.g. a language not allowed for this question
            return CodingEvaluationResult(
                question_id=question_id, question_type=question_type, answer=given_answer,
                points_possible=points, feedback=str(exc), evaluation_method="auto", evaluation_status="scored",
                metadata={**score_outcomes(question, []), "result_status": "not_passed", "language": language},
            )
        except ExecutionUnavailable as exc:
            if not enabled_cases(question):
                pending = self.fallback.evaluate(question, answer, language)
                pending.review_notes = str(exc)
                return pending
            # The sandbox failed: nothing is known about the answer, so no marks or verdict are recorded.
            return CodingEvaluationResult(
                question_id=question_id, question_type=question_type, answer=given_answer, points_possible=points,
                feedback="The code could not be executed because of an infrastructure problem. It will be re-graded.",
                evaluation_method="executed" if question_type == "coding" else "sql_executed",
                evaluation_status="execution_error", review_notes=str(exc),
                metadata={"result_status": "execution_error", "error_kind": "infrastructure", "retryable": True,
                          "qualification": "pending", "language": language, "tests_total": len(enabled_cases(question)),
                          "tests_passed": 0, "max_marks": points, "marks": 0, "error": str(exc)[:500]},
            )
        score = score_outcomes(question, graded.outcomes)
        summary = graded.summary()
        feedback = (f"Passed {score['tests_passed']}/{score['tests_total']} tests "
                    f"({summary['hidden_passed']}/{summary['hidden_total']} hidden): {score['marks']:g}/{score['max_marks']:g} marks.")
        if score["error_kind"] == "compile_error":
            feedback = "The code did not compile. " + feedback
        return CodingEvaluationResult(
            question_id=question_id, question_type=question_type, answer=given_answer,
            points_possible=points, points_earned=score["marks"],
            is_correct=score["result_status"] == "passed", feedback=feedback,
            evaluation_method=graded.method, evaluation_status="scored", review_notes=graded.feedback,
            metadata={**summary, **score, "tests": outcome_dicts(graded)},
        )


DEFAULT_CODING_EVALUATOR: CodingEvaluator = AutoCodingEvaluator()
