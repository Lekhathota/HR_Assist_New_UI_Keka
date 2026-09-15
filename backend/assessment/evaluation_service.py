"""
Assessment evaluation orchestration.

MCQ / true-false / short-answer questions are scored automatically on submit.
Coding and SQL questions are routed through CodingEvaluator (stub until AI review is enabled).
"""

from __future__ import annotations

from typing import Any

from assessment.evaluators.coding_evaluator import DEFAULT_CODING_EVALUATOR, CodingEvaluator
from assessment.evaluators.mcq_evaluator import evaluate_auto_scored_question
from assessment.models import QuestionType


def _question_type_value(question: dict[str, Any]) -> str:
    raw_type = question.get("question_type") or QuestionType.MCQ
    return raw_type.value if hasattr(raw_type, "value") else str(raw_type)


def evaluate_question(
    question: dict[str, Any],
    answer: str,
    *,
    coding_evaluator: CodingEvaluator | None = None,
) -> dict[str, Any]:
    question_type = _question_type_value(question)
    if question_type in {QuestionType.CODING.value, QuestionType.SQL.value}:
        evaluator = coding_evaluator or DEFAULT_CODING_EVALUATOR
        return evaluator.evaluate(question, answer).to_dict()
    return evaluate_auto_scored_question(question, answer)


def evaluate_assessment(
    questions: list[dict[str, Any]],
    answers_by_question: dict[int, str],
    *,
    passing_score: int = 70,
    coding_evaluator: CodingEvaluator | None = None,
) -> dict[str, Any]:
    """
    Evaluate all answers and compute aggregate score, percentage, and pass/fail.

    Pass/fail is based on auto-scored questions (MCQ block) when coding/SQL answers
    are still pending review; otherwise uses the overall percentage.
    """
    question_results: list[dict[str, Any]] = []
    total_points = 0
    earned_points = 0
    auto_total = 0
    auto_earned = 0
    pending_review_count = 0

    for question in questions:
        question_id = int(question.get("id") or 0)
        answer = answers_by_question.get(question_id, "")
        result = evaluate_question(question, answer, coding_evaluator=coding_evaluator)
        question_results.append(result)

        points_possible = int(result.get("points_possible") or 0)
        points_earned = int(result.get("points_earned") or 0)
        total_points += points_possible
        earned_points += points_earned

        if result.get("evaluation_status") == "pending_review":
            pending_review_count += 1
        else:
            auto_total += points_possible
            auto_earned += points_earned

    score_percentage = round((earned_points / total_points) * 100, 2) if total_points else 0.0
    mcq_percentage = round((auto_earned / auto_total) * 100, 2) if auto_total else 0.0

    if pending_review_count > 0 and auto_total > 0:
        passed = mcq_percentage >= passing_score
        pass_basis = "mcq_auto"
    else:
        passed = score_percentage >= passing_score
        pass_basis = "overall"

    return {
        "score": earned_points,
        "total_points": total_points,
        "earned_points": earned_points,
        "score_percentage": score_percentage,
        "percentage": score_percentage,
        "mcq_percentage": mcq_percentage,
        "auto_earned_points": auto_earned,
        "auto_total_points": auto_total,
        "pending_review_count": pending_review_count,
        "passed": passed,
        "pass_basis": pass_basis,
        "question_results": question_results,
        "evaluation_breakdown": {
            "auto_scored": {
                "earned_points": auto_earned,
                "total_points": auto_total,
                "percentage": mcq_percentage,
            },
            "pending_review": {
                "count": pending_review_count,
                "status": "pending_ai" if pending_review_count else "none",
            },
        },
    }
