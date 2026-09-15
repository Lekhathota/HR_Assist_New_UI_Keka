"""
Automatic scoring for MCQ, true/false, and short-answer questions.
"""

from __future__ import annotations

from typing import Any

from assessment.models import QuestionType
from assessment.utilities import normalize_answer


def _question_type_value(question: dict[str, Any]) -> str:
    raw_type = question.get("question_type") or QuestionType.MCQ
    return raw_type.value if hasattr(raw_type, "value") else str(raw_type)


def evaluate_auto_scored_question(question: dict[str, Any], answer: str) -> dict[str, Any]:
    """Score questions that can be evaluated automatically without AI review."""
    points = int(question.get("points") or 0)
    question_type = _question_type_value(question)
    correct_answer = str(question.get("correct_answer") or "").strip()
    given_answer = str(answer or "").strip()
    earned = 0
    is_correct = False

    if not given_answer:
        feedback = "No answer provided."
    elif question_type in {QuestionType.MCQ.value, QuestionType.TRUE_FALSE.value}:
        is_correct = normalize_answer(given_answer) == normalize_answer(correct_answer)
        earned = points if is_correct else 0
        feedback = "Correct." if is_correct else "Incorrect."
    elif question_type == QuestionType.SHORT_ANSWER.value:
        if not correct_answer:
            earned = points
            is_correct = True
            feedback = "Open-ended response recorded."
        else:
            is_correct = normalize_answer(given_answer) == normalize_answer(correct_answer)
            earned = points if is_correct else 0
            feedback = "Correct." if is_correct else "Incorrect."
    else:
        feedback = "Question type is not auto-scored."

    return {
        "question_id": int(question.get("id") or 0),
        "question_type": question_type,
        "answer": given_answer,
        "is_correct": is_correct,
        "points_possible": points,
        "points_earned": earned,
        "feedback": feedback,
        "evaluation_method": "auto",
        "evaluation_status": "scored",
    }
