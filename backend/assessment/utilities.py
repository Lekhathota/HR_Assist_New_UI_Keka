"""
Assessment helpers: tokens, status transitions, scoring, and response shaping.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from assessment.models import AssessmentStatus, QuestionType

_CANDIDATE_TEST_PATH = "/assessment"
_TOKEN_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_access_token() -> str:
    """Create a secure UUID v4 access token for candidate assessment links."""
    return str(uuid.uuid4())


def token_expiry(days: int | None = None) -> datetime:
    ttl_days = days
    if ttl_days is None:
        try:
            ttl_days = int(os.environ.get("ASSESSMENT_TOKEN_TTL_DAYS", "7"))
        except ValueError:
            ttl_days = 7
    return utc_now() + timedelta(days=max(1, ttl_days))


def candidate_test_base_url() -> str:
    """Base URL used only for candidate assessment test links (never the recruiter app/dev URL)."""
    return (
        os.environ.get("CANDIDATE_TEST_BASE_URL")
        or os.environ.get("ASSESSMENT_PUBLIC_URL")
        or f"http://{os.environ.get('FLASK_HOST', '127.0.0.1')}:{os.environ.get('PORT', '5000')}"
    ).rstrip("/")


def normalize_access_token(token: str | None) -> str:
    cleaned = str(token or "").strip().strip("<>").lower()
    if not cleaned or cleaned in {"token", "access_token", "your-token"}:
        return ""
    if _TOKEN_RE.match(cleaned):
        return cleaned
    return ""


def is_candidate_test_url(url: str | None) -> bool:
    value = str(url or "").strip()
    if not value:
        return False
    return bool(re.match(r"^https?://[^/\s]+/assessment/[0-9a-f-]{36}$", value, re.IGNORECASE))


def assessment_link(token: str) -> str:
    clean_token = normalize_access_token(token)
    if not clean_token:
        raise ValueError("A valid assessment access token is required to build the candidate test link.")
    return f"{candidate_test_base_url()}{_CANDIDATE_TEST_PATH}/{clean_token}"


def assert_status_transition(current: str, target: str) -> None:
    allowed: dict[str, set[str]] = {
        AssessmentStatus.DRAFT: {AssessmentStatus.SENT},
        AssessmentStatus.SENT: {AssessmentStatus.IN_PROGRESS, AssessmentStatus.COMPLETED},
        AssessmentStatus.IN_PROGRESS: {AssessmentStatus.COMPLETED, AssessmentStatus.PASSED, AssessmentStatus.FAILED},
        AssessmentStatus.COMPLETED: {AssessmentStatus.PASSED, AssessmentStatus.FAILED},
    }
    if current == target:
        return
    next_states = allowed.get(current, set())
    if target not in next_states:
        raise ValueError(f"Cannot transition assessment from {current} to {target}.")


def token_is_expired(expires_at: Any) -> bool:
    if not expires_at:
        return False
    if isinstance(expires_at, datetime):
        expiry = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
    else:
        raw = str(expires_at).replace("Z", "+00:00")
        try:
            expiry = datetime.fromisoformat(raw)
        except ValueError:
            return False
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
    return utc_now() > expiry


def normalize_answer(value: str) -> str:
    return str(value or "").strip().lower()


def score_question(question: dict[str, Any], answer: str) -> dict[str, Any]:
    points = int(question.get("points") or 0)
    raw_type = question.get("question_type") or QuestionType.MCQ
    question_type = raw_type.value if hasattr(raw_type, "value") else str(raw_type)
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
    elif question_type in {QuestionType.CODING.value, QuestionType.SQL.value}:
        if given_answer.strip():
            earned = points
            is_correct = True
            feedback = "Response recorded for manual review."
        else:
            feedback = "No answer provided."
    else:
        feedback = "Unsupported question type."

    return {
        "question_id": int(question.get("id") or 0),
        "answer": given_answer,
        "is_correct": is_correct,
        "points_possible": points,
        "points_earned": earned,
        "feedback": feedback,
    }


def score_assessment(
    questions: list[dict[str, Any]],
    answers_by_question: dict[int, str],
    *,
    passing_score: int | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the evaluation service."""
    from assessment.evaluation_service import evaluate_assessment

    result = evaluate_assessment(
        questions,
        answers_by_question,
        passing_score=passing_score if passing_score is not None else 70,
    )
    return {
        "total_points": result["total_points"],
        "earned_points": result["earned_points"],
        "score_percentage": result["score_percentage"],
        "question_results": result["question_results"],
    }


def recruiter_question_payload(question: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": question.get("id"),
        "assessment_id": question.get("assessment_id"),
        "question_text": question.get("question_text") or "",
        "question_type": question.get("question_type") or QuestionType.MCQ,
        "options": question.get("options") or [],
        "correct_answer": question.get("correct_answer") or "",
        "starter_code": question.get("starter_code") or "",
        "points": int(question.get("points") or 0),
        "skill_tag": question.get("skill_tag") or "",
        "sort_order": int(question.get("sort_order") or 0),
        "created_at": question.get("created_at"),
        "updated_at": question.get("updated_at"),
    }


def candidate_question_payload(question: dict[str, Any]) -> dict[str, Any]:
    payload = recruiter_question_payload(question)
    payload.pop("correct_answer", None)
    return payload


def parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def compute_assessment_duration_minutes(assessment: dict[str, Any]) -> int | None:
    """Minutes between started_at and completed_at when both are present."""
    started = parse_iso_datetime(assessment.get("started_at"))
    completed = parse_iso_datetime(assessment.get("completed_at"))
    if not started or not completed:
        return None
    return max(0, int((completed - started).total_seconds() // 60))


def compute_link_status(assessment: dict[str, Any]) -> str:
    """Human-readable assessment link state for recruiter views."""
    status = str(assessment.get("status") or AssessmentStatus.NOT_CREATED)
    if status in {AssessmentStatus.NOT_CREATED, AssessmentStatus.DRAFT}:
        return "Not Sent"
    if status in {AssessmentStatus.COMPLETED, AssessmentStatus.PASSED, AssessmentStatus.FAILED}:
        return "Submitted"
    if token_is_expired(assessment.get("token_expires_at")):
        return "Expired"
    if assessment.get("access_token"):
        return "Active"
    return "Inactive"


def remaining_seconds(assessment: dict[str, Any]) -> int | None:
    """Seconds left based on started_at + time_limit_minutes. None if not started."""
    started = parse_iso_datetime(assessment.get("started_at"))
    if not started:
        return None
    limit_minutes = int(assessment.get("time_limit_minutes") or 0)
    if limit_minutes <= 0:
        return None
    deadline = started + timedelta(minutes=limit_minutes)
    return max(0, int((deadline - utc_now()).total_seconds()))


def candidate_assessment_payload(assessment: dict[str, Any], *, questions: list[dict[str, Any]]) -> dict[str, Any]:
    """Public-facing assessment metadata for the candidate UI."""
    base = assessment_summary_payload(assessment, questions=questions, include_token=False)
    base["candidate_name"] = assessment.get("candidate_name") or ""
    base["time_limit_minutes"] = int(assessment.get("time_limit_minutes") or 60)
    base["started_at"] = assessment.get("started_at")
    base["remaining_seconds"] = remaining_seconds(assessment)
    return base


def assessment_summary_payload(
    assessment: dict[str, Any],
    *,
    questions: list[dict[str, Any]] | None = None,
    include_token: bool = False,
) -> dict[str, Any]:
    payload = {
        "id": assessment.get("id"),
        "candidate_id": assessment.get("candidate_id"),
        "jd_id": assessment.get("jd_id"),
        "recruiter_id": assessment.get("recruiter_id"),
        "status": assessment.get("status") or AssessmentStatus.NOT_CREATED,
        "title": assessment.get("title") or "",
        "candidate_name": assessment.get("candidate_name") or "",
        "candidate_email": assessment.get("candidate_email") or "",
        "job_role": assessment.get("job_role") or "",
        "passing_score": int(assessment.get("passing_score") or 0),
        "time_limit_minutes": int(assessment.get("time_limit_minutes") or 0),
        "sent_at": assessment.get("sent_at"),
        "started_at": assessment.get("started_at"),
        "completed_at": assessment.get("completed_at"),
        "created_at": assessment.get("created_at"),
        "updated_at": assessment.get("updated_at"),
        "question_count": len(questions or []),
    }
    if include_token:
        token = normalize_access_token(str(assessment.get("access_token") or ""))
        payload["access_token"] = token
        payload["token_expires_at"] = assessment.get("token_expires_at")
        payload["assessment_link"] = assessment_link(token) if token else ""
    return payload
