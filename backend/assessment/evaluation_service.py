"""
Assessment evaluation orchestration.

MCQ / true-false / short-answer questions are scored automatically on submit.
Coding and SQL questions are executed against their visible and hidden test cases
through CodingEvaluator (AutoCodingEvaluator by default).

Sections are scored separately:
  mcq     -> every non-executable question (MCQ, true/false, short answer)
  coding  -> coding and SQL questions (scored from executed test results)
The overall score is points-based unless the assessment's scoring policy sets section
weights. The policy can make the coding section mandatory, so a high MCQ score cannot
compensate for failing the coding requirements.
"""

from __future__ import annotations

import math
from typing import Any

from assessment.evaluators.coding_evaluator import DEFAULT_CODING_EVALUATOR, CodingEvaluator
from assessment.evaluators.mcq_evaluator import evaluate_auto_scored_question
from assessment.models import QuestionType

EXECUTABLE = {QuestionType.CODING.value, QuestionType.SQL.value}
SECTIONS = ("mcq", "coding")
DEFAULT_SCORING_POLICY: dict[str, Any] = {
    "section_weights": None,              # None: overall = points earned / points possible
    "min_mcq_score": 0.0,                 # % of the MCQ section
    "min_coding_score": 0.0,              # % of the coding section (applies when coding is mandatory)
    "coding_section_mandatory": False,    # coding requirements must be met regardless of the MCQ score
    "require_coding_qualification": False,  # every coding question must meet its own qualification criteria
}


def _question_type_value(question: dict[str, Any]) -> str:
    raw_type = question.get("question_type") or QuestionType.MCQ
    return raw_type.value if hasattr(raw_type, "value") else str(raw_type)


def _percent(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number between 0 and 100.") from None
    if math.isnan(number) or not 0 <= number <= 100:
        raise ValueError(f"{label} must be between 0 and 100.")
    return number


def normalize_scoring_policy(data: Any) -> dict[str, Any]:
    """Validate an assessment scoring policy (raises ValueError); missing keys keep their defaults."""
    if data is None:
        return dict(DEFAULT_SCORING_POLICY)
    if not isinstance(data, dict):
        raise ValueError("The scoring policy must be an object.")
    policy = dict(DEFAULT_SCORING_POLICY)
    weights = data.get("section_weights")
    if weights is not None:
        if not isinstance(weights, dict) or set(weights) - set(SECTIONS):
            raise ValueError("Section weights must give a percentage for mcq and coding.")
        parsed = {key: _percent(weights.get(key, 0), f"{key.upper()} weight") for key in SECTIONS}
        if abs(sum(parsed.values()) - 100) > 0.01:
            raise ValueError(f"Section weights must add up to 100% (they add up to {sum(parsed.values()):g}%).")
        policy["section_weights"] = parsed
    for key, label in (("min_mcq_score", "Minimum MCQ score"), ("min_coding_score", "Minimum coding score")):
        if key in data:
            policy[key] = _percent(data[key], label)
    for key in ("coding_section_mandatory", "require_coding_qualification"):
        if key in data:
            if not isinstance(data[key], bool):
                raise ValueError(f"{key.replace('_', ' ').capitalize()} must be true or false.")
            policy[key] = data[key]
    return policy


def evaluate_question(
    question: dict[str, Any],
    answer: str,
    *,
    language: str = "",
    coding_evaluator: CodingEvaluator | None = None,
) -> dict[str, Any]:
    question_type = _question_type_value(question)
    if question_type in EXECUTABLE:
        evaluator = coding_evaluator or DEFAULT_CODING_EVALUATOR
        return evaluator.evaluate(question, answer, language).to_dict()
    return evaluate_auto_scored_question(question, answer)


def _section_of(result: dict[str, Any]) -> str:
    return "coding" if result.get("question_type") in EXECUTABLE else "mcq"


def evaluate_assessment(
    questions: list[dict[str, Any]],
    answers_by_question: dict[int, str],
    *,
    passing_score: int,
    languages_by_question: dict[int, str] | None = None,
    coding_evaluator: CodingEvaluator | None = None,
    scoring_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate all answers; compute section scores, the overall score and the pass decision.

    The pass decision compares the reported (rounded) overall percentage with the passing
    score, plus any section requirements in the scoring policy. When an answer could not be
    executed because of an infrastructure failure, needs_retry is set and passed stays False
    without the candidate being failed: the caller records the result as awaiting re-grading.
    """
    policy = normalize_scoring_policy(scoring_policy)
    question_results: list[dict[str, Any]] = []
    sections = {key: {"earned": 0.0, "possible": 0.0, "count": 0} for key in SECTIONS}
    pending_review_count = execution_error_count = 0

    for question in questions:
        question_id = int(question.get("id") or 0)
        answer = answers_by_question.get(question_id, "")
        language = (languages_by_question or {}).get(question_id, "")
        result = evaluate_question(question, answer, language=language, coding_evaluator=coding_evaluator)
        question_results.append(result)
        section = sections[_section_of(result)]
        section["count"] += 1
        section["possible"] += float(result.get("points_possible") or 0)
        section["earned"] += float(result.get("points_earned") or 0)
        if result.get("evaluation_status") == "pending_review":
            pending_review_count += 1
        if result.get("evaluation_status") == "execution_error":
            execution_error_count += 1

    for section in sections.values():
        section["earned"] = round(section["earned"], 2)
        section["possible"] = round(section["possible"], 2)
        section["percentage"] = round(section["earned"] / section["possible"] * 100, 2) if section["possible"] else None

    total_points = round(sum(s["possible"] for s in sections.values()), 2)
    earned_points = round(sum(s["earned"] for s in sections.values()), 2)
    present = [key for key in SECTIONS if sections[key]["possible"] > 0]
    weights = policy["section_weights"]
    if weights and present and sum(weights[key] for key in present) > 0:
        weight_sum = sum(weights[key] for key in present)
        applied = {key: weights[key] / weight_sum * 100 for key in present}
        score_percentage = round(sum(sections[key]["percentage"] * applied[key] / 100 for key in present), 2)
        pass_basis = "weighted"
    else:
        applied = None
        score_percentage = round(earned_points / total_points * 100, 2) if total_points else 0.0
        pass_basis = "overall"

    coding_rows = [r for r in question_results if _section_of(r) == "coding"]
    checks = [{"rule": "overall", "label": f"Overall score at least {float(passing_score):g}%",
               "required": float(passing_score), "actual": score_percentage, "met": score_percentage >= float(passing_score)}]
    if sections["mcq"]["count"] and policy["min_mcq_score"] > 0:
        actual = sections["mcq"]["percentage"] or 0.0
        checks.append({"rule": "min_mcq_score", "label": f"MCQ score at least {policy['min_mcq_score']:g}%",
                       "required": policy["min_mcq_score"], "actual": actual, "met": actual >= policy["min_mcq_score"]})
    if coding_rows and policy["coding_section_mandatory"]:
        if policy["min_coding_score"] > 0:
            actual = sections["coding"]["percentage"] or 0.0
            checks.append({"rule": "min_coding_score", "label": f"Coding score at least {policy['min_coding_score']:g}%",
                           "required": policy["min_coding_score"], "actual": actual, "met": actual >= policy["min_coding_score"]})
        if policy["require_coding_qualification"]:
            qualified = sum(1 for r in coding_rows if (r.get("metadata") or {}).get("qualification") == "qualified")
            checks.append({"rule": "coding_qualification", "label": "Every coding question meets its qualification criteria",
                           "required": len(coding_rows), "actual": qualified, "met": qualified == len(coding_rows)})
    needs_retry = execution_error_count > 0
    passed = not needs_retry and all(check["met"] for check in checks)
    mcq_percentage = sections["mcq"]["percentage"] or 0.0

    return {
        "score": earned_points,
        "total_points": total_points,
        "earned_points": earned_points,
        "score_percentage": score_percentage,
        "percentage": score_percentage,
        "mcq_percentage": mcq_percentage,
        "coding_percentage": sections["coding"]["percentage"],
        "auto_earned_points": sections["mcq"]["earned"],
        "auto_total_points": sections["mcq"]["possible"],
        "pending_review_count": pending_review_count,
        "execution_error_count": execution_error_count,
        "needs_retry": needs_retry,
        "passed": passed,
        "pass_basis": pass_basis,
        "scoring_policy": policy,
        "applied_section_weights": applied,
        "qualification_checks": checks,
        "question_results": question_results,
        "evaluation_breakdown": {
            "sections": sections,
            "auto_scored": {
                "earned_points": sections["mcq"]["earned"],
                "total_points": sections["mcq"]["possible"],
                "percentage": mcq_percentage,
            },
            "pending_review": {
                "count": pending_review_count,
                "status": "pending_review" if pending_review_count else "none",
            },
            "execution_errors": {"count": execution_error_count, "retryable": needs_retry},
        },
    }
