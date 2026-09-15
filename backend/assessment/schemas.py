"""
Request and response validation for Assessment API payloads.
"""

from __future__ import annotations

from typing import Any

from assessment.models import (
    CODING_COUNT,
    DEFAULT_PASSING_SCORE,
    MCQ_COUNT,
    QuestionType,
    SQL_COUNT,
    TOTAL_GENERATED_QUESTIONS,
)


class SchemaValidationError(ValueError):
    """Raised when an API payload fails validation."""


VALID_QUESTION_TYPES = {
    QuestionType.MCQ,
    QuestionType.SHORT_ANSWER,
    QuestionType.TRUE_FALSE,
    QuestionType.CODING,
    QuestionType.SQL,
}


def _require_int(value: Any, field_name: str, *, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SchemaValidationError(f"{field_name} must be a valid integer.") from exc
    if parsed < minimum:
        raise SchemaValidationError(f"{field_name} must be at least {minimum}.")
    return parsed


def _optional_int(value: Any, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    if value is None or value == "":
        return default
    parsed = _require_int(value, "value", minimum=minimum)
    if maximum is not None and parsed > maximum:
        raise SchemaValidationError(f"Value must be at most {maximum}.")
    return parsed


def _require_str(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    text = str(value or "").strip()
    if not text and not allow_empty:
        raise SchemaValidationError(f"{field_name} is required.")
    return text


def _optional_str(value: Any) -> str:
    return str(value or "").strip()


def _validate_question_type(question_type: str) -> str:
    qt = _optional_str(question_type) or QuestionType.MCQ
    if qt not in VALID_QUESTION_TYPES:
        allowed = ", ".join(sorted(VALID_QUESTION_TYPES))
        raise SchemaValidationError(f"question_type must be one of: {allowed}.")
    return qt


def validate_generate_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SchemaValidationError("Request body must be a JSON object.")
    return {
        "candidate_id": _require_int(data.get("candidate_id"), "candidate_id"),
        "jd_id": _require_int(data.get("jd_id"), "jd_id"),
        "passing_score": _optional_int(data.get("passing_score"), DEFAULT_PASSING_SCORE, minimum=1, maximum=100),
        "time_limit_minutes": _optional_int(data.get("time_limit_minutes"), 90, minimum=5, maximum=480),
        "title": _optional_str(data.get("title")),
        "mcq_count": MCQ_COUNT,
        "coding_count": CODING_COUNT,
        "sql_count": SQL_COUNT,
        "total_questions": TOTAL_GENERATED_QUESTIONS,
    }


def validate_save_draft_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SchemaValidationError("Request body must be a JSON object.")
    patch: dict[str, Any] = {}
    if "title" in data:
        patch["title"] = _require_str(data.get("title"), "title")
    if "passing_score" in data:
        patch["passing_score"] = _optional_int(data.get("passing_score"), DEFAULT_PASSING_SCORE, minimum=1, maximum=100)
    if "time_limit_minutes" in data:
        patch["time_limit_minutes"] = _optional_int(data.get("time_limit_minutes"), 90, minimum=5, maximum=480)
    if not patch:
        raise SchemaValidationError("At least one field is required to save the draft.")
    return patch


def validate_question_create_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SchemaValidationError("Request body must be a JSON object.")
    question_type = _validate_question_type(data.get("question_type"))
    options = data.get("options") or []
    if not isinstance(options, list):
        raise SchemaValidationError("options must be a list.")
    options = [str(item).strip() for item in options if str(item).strip()]
    if question_type == QuestionType.MCQ and len(options) < 2:
        raise SchemaValidationError("MCQ questions require at least two options.")
    if question_type == QuestionType.TRUE_FALSE and not options:
        options = ["True", "False"]
    return {
        "assessment_id": _require_int(data.get("assessment_id"), "assessment_id"),
        "question_text": _require_str(data.get("question_text"), "question_text"),
        "question_type": question_type,
        "options": options,
        "correct_answer": _optional_str(data.get("correct_answer")),
        "starter_code": _optional_str(data.get("starter_code")),
        "points": _optional_int(data.get("points"), 10, minimum=1, maximum=100),
        "skill_tag": _optional_str(data.get("skill_tag")),
        "sort_order": _optional_int(data.get("sort_order"), 0, minimum=0, maximum=999),
    }


def validate_question_update_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SchemaValidationError("Request body must be a JSON object.")
    patch: dict[str, Any] = {}
    if "question_text" in data:
        patch["question_text"] = _require_str(data.get("question_text"), "question_text")
    if "question_type" in data:
        patch["question_type"] = _validate_question_type(data.get("question_type"))
    if "options" in data:
        options = data.get("options")
        if not isinstance(options, list):
            raise SchemaValidationError("options must be a list.")
        patch["options"] = [str(item).strip() for item in options if str(item).strip()]
    if "correct_answer" in data:
        patch["correct_answer"] = _optional_str(data.get("correct_answer"))
    if "starter_code" in data:
        patch["starter_code"] = _optional_str(data.get("starter_code"))
    if "points" in data:
        patch["points"] = _optional_int(data.get("points"), 10, minimum=1, maximum=100)
    if "skill_tag" in data:
        patch["skill_tag"] = _optional_str(data.get("skill_tag"))
    if "sort_order" in data:
        patch["sort_order"] = _optional_int(data.get("sort_order"), 0, minimum=0, maximum=999)
    if not patch:
        raise SchemaValidationError("At least one field is required to update a question.")
    return patch


def validate_save_answer_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SchemaValidationError("Request body must be a JSON object.")
    return {
        "token": _require_str(data.get("token"), "token"),
        "question_id": _require_int(data.get("question_id"), "question_id"),
        "answer": _require_str(data.get("answer"), "answer", allow_empty=True),
    }


def validate_submit_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SchemaValidationError("Request body must be a JSON object.")
    answers = data.get("answers")
    normalized_answers: list[dict[str, Any]] = []
    if answers is not None:
        if not isinstance(answers, list):
            raise SchemaValidationError("answers must be a list.")
        for item in answers:
            if not isinstance(item, dict):
                raise SchemaValidationError("Each answer entry must be an object.")
            normalized_answers.append(
                {
                    "question_id": _require_int(item.get("question_id"), "question_id"),
                    "answer": _require_str(item.get("answer"), "answer", allow_empty=True),
                }
            )
    return {
        "token": _require_str(data.get("token"), "token"),
        "answers": normalized_answers,
    }


def validate_send_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"subject": "", "body": "", "regenerate_email": True, "to_email": ""}
    return {
        "subject": _optional_str(data.get("subject")),
        "body": _optional_str(data.get("body")),
        "regenerate_email": bool(data.get("regenerate_email", True)),
        "to_email": _optional_str(data.get("to_email")),
    }
