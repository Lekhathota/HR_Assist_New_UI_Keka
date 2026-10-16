"""
"Send Assessment" from the Talent page and a candidate's All Details view.

One workflow for both entry points: pick a JD and generate (or reuse) a validated AI
assessment as a DRAFT. Nothing is emailed here: the recruiter reviews, edits and validates
it in the Preview Assessment dialog and sends it from there (assessment_service.send_assessment).
An explicit resend of an assessment that was already sent re-emails the same link.
Works for candidates rejected at resume screening; it never changes their hiring stage.

Duplicate protection:
- a lease per candidate/JD stops concurrent requests from generating twice;
- the client's request_id makes a retried request return the stored outcome;
- an attempt that was already emailed (or whose delivery is uncertain) is only
  re-sent when the recruiter explicitly asks, and always reuses the same link.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any

import database as db
from assessment import repository as assessment_repo
from assessment.models import DEFAULT_PASSING_SCORE, AssessmentStatus
from assessment.utilities import (
    assessment_link,
    generate_access_token,
    normalize_access_token,
    token_is_expired,
    utc_now,
    validate_public_assessment_link,
)
from email_utils import is_valid_email, normalize_email
from services.assessment_service import (
    AssessmentServiceError,
    _build_invite_email,
    _candidate_selected_for_jd,
    _prepare_assessment_send,
    _result_payload,
    generate_assessment,
)
from services.interview_service import EmailDeliveryUnknown, send_email

DEFAULT_TIME_LIMIT_MINUTES = 90
# Generation runs up to three AI attempts; the lease must outlive a slow request.
SEND_LEASE_SECONDS = 600
_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,80}$")

LIFECYCLE_LABELS = {
    "generated": "Assessment generated",
    "delivery_failed": "Email delivery failed",
    "delivery_unknown": "Email delivery uncertain",
    "awaiting_response": "Email sent · awaiting candidate",
    "in_progress": "In progress",
    "submitted": "Submitted · being evaluated",
    "evaluated": "Evaluated",
    "terminated": "Terminated",
    "expired": "Link expired",
}


class AssessmentWorkflowError(AssessmentServiceError):
    """Error with a machine-readable code the UI uses to choose the next step."""

    def __init__(self, message: str, *, code: str, status_code: int = 400, **extra: Any) -> None:
        super().__init__(message, status_code=status_code)
        self.code = code
        self.extra = extra

    def payload(self) -> dict[str, Any]:
        return {"error": str(self), "code": self.code, **self.extra}


def _lifecycle(row: dict[str, Any]) -> str:
    status = str(row.get("status") or "")
    delivery = str(row.get("email_delivery_status") or "")
    if status == AssessmentStatus.DRAFT:
        return "delivery_failed" if delivery == "failed" else "generated"
    if status == AssessmentStatus.SENT:
        if token_is_expired(row.get("token_expires_at")):
            return "expired"
        return "delivery_unknown" if delivery in {"unknown", "sending"} else "awaiting_response"
    if status == AssessmentStatus.IN_PROGRESS:
        return "in_progress"
    if status == AssessmentStatus.COMPLETED:
        return "submitted"
    if status in {AssessmentStatus.PASSED, AssessmentStatus.FAILED}:
        return "evaluated"
    if status == AssessmentStatus.TERMINATED:
        return "terminated"
    return "generated"


def assessment_view(row: dict[str, Any], jds: dict[int, dict] | None = None) -> dict[str, Any]:
    """Recruiter-facing summary of one assessment attempt (no answer key, no prompts)."""
    jd_id = int(row.get("jd_id") or 0)
    jd = (jds or {}).get(jd_id) or db.get_jd_by_id(jd_id, include_raw_text=False) or {}
    status = str(row.get("status") or "")
    token = normalize_access_token(str(row.get("access_token") or ""))
    link = ""
    if token and status in AssessmentStatus.candidate_accessible_states():
        try:
            link = assessment_link(token)
        except ValueError:
            link = ""
    result = _result_payload(assessment_repo.get_result_by_assessment_id(int(row.get("id") or 0)))
    lifecycle = _lifecycle(row)
    return {
        "id": row.get("id"),
        "candidate_id": row.get("candidate_id"),
        "jd_id": jd_id,
        "jd_title": jd.get("title") or row.get("job_role") or "",
        "client_name": jd.get("client_name") or "",
        "title": row.get("title") or "",
        "status": status,
        "lifecycle": lifecycle,
        "lifecycle_label": LIFECYCLE_LABELS[lifecycle],
        "candidate_email": row.get("candidate_email") or "",
        "time_limit_minutes": int(row.get("time_limit_minutes") or 0),
        "passing_score": int(row.get("passing_score") or 0),
        "created_at": row.get("created_at"),
        "sent_at": row.get("sent_at"),
        "email_sent_at": row.get("email_sent_at"),
        "started_at": row.get("started_at"),
        "completed_at": row.get("completed_at"),
        "token_expires_at": row.get("token_expires_at"),
        "email_delivery_status": row.get("email_delivery_status") or ("sent" if row.get("sent_at") else "not_sent"),
        "email_delivery_error": row.get("email_delivery_error") or "",
        "delivery_history": row.get("delivery_history") or [],
        "assessment_link": link,
        "screening_override": bool(row.get("screening_override")),
        "initiated_by": row.get("initiated_by") or "",
        "termination_reason": row.get("termination_reason") or "",
        "result": {
            "status": result.get("status"),
            "percentage": result.get("percentage"),
            "passed": result.get("passed"),
            "pending_review_count": result.get("pending_review_count"),
            "summary": result.get("summary"),
            "scored_at": result.get("scored_at"),
        } if result else None,
    }


def list_candidate_assessments(candidate_id: int) -> dict[str, Any]:
    if not db.get_candidate_by_id(candidate_id):
        raise AssessmentWorkflowError("Candidate not found.", code="candidate_not_found", status_code=404)
    rows = assessment_repo.get_assessments_for_candidate(candidate_id)
    jds: dict[int, dict] = {}
    for jd_id in {int(row.get("jd_id") or 0) for row in rows}:
        jds[jd_id] = db.get_jd_by_id(jd_id, include_raw_text=False) or {}
    latest_created = {}
    for row in rows:
        latest_created.setdefault(int(row.get("jd_id") or 0), row.get("created_at"))
    # Generation failures leave no assessment row; surface the last one per JD until a newer attempt exists.
    failures = []
    for request in assessment_repo.get_send_requests_for_candidate(candidate_id):
        jd_id = int(request.get("jd_id") or 0)
        newer = latest_created.get(jd_id)
        if request.get("state") != "generation_failed" or (newer and str(newer) >= str(request.get("updated_at"))):
            continue
        jd = jds.get(jd_id) or db.get_jd_by_id(jd_id, include_raw_text=False) or {}
        failures.append({"jd_id": jd_id, "jd_title": jd.get("title") or "", "error": request.get("last_error") or "",
                         "at": request.get("updated_at")})
    return {"assessments": [assessment_view(row, jds) for row in rows], "generation_failures": failures}


def _target_email(candidate: dict[str, Any], to_email: str) -> str:
    """The resume/profile email, or the address the recruiter typed to correct it. Never another fallback."""
    supplied = normalize_email(to_email)
    email = supplied or normalize_email(candidate.get("email"))
    if not email:
        raise AssessmentWorkflowError(
            "This candidate has no email address in their resume or profile. Enter the correct address to send the assessment.",
            code="email_missing", status_code=422,
        )
    if not is_valid_email(email):
        raise AssessmentWorkflowError(
            f"“{email}” is not a valid email address. Correct it to send the assessment.",
            code="email_invalid", status_code=422, email=email,
        )
    return email


def _assert_delivery_configured() -> None:
    # Checked before generating so a missing setting does not cost an AI generation.
    if not os.environ.get("SMTP_USER") or not os.environ.get("SMTP_PASS"):
        raise AssessmentWorkflowError("Email is not configured on the server (SMTP_USER / SMTP_PASS). No assessment was generated.",
                                      code="email_not_configured", status_code=503)
    try:
        validate_public_assessment_link(assessment_link(generate_access_token()))
    except ValueError as exc:
        raise AssessmentWorkflowError(str(exc), code="link_not_configured", status_code=503) from exc


def _response(row: dict[str, Any], code: str, message: str) -> dict[str, Any]:
    return {"success": True, "code": code, "message": message, "assessment": assessment_view(row)}


def _deliver(assessment_id: int, *, recruiter: dict[str, Any], to_email: str, request_id: str) -> dict[str, Any]:
    assessment, current_status, token, expires_at, link, from_email, to_email = _prepare_assessment_send(
        assessment_id, recruiter=recruiter, to_email_override=to_email,
    )
    email = _build_invite_email(assessment, link, from_email, expires_at=expires_at, instructions=True)
    if link not in email["body"]:
        raise AssessmentWorkflowError("The candidate test link could not be included in the email.", code="delivery_failed", status_code=500)

    first_send = current_status == AssessmentStatus.DRAFT
    activated = assessment_repo.update_assessment(assessment_id, {
        "status": AssessmentStatus.SENT,
        "access_token": token,
        "token_expires_at": expires_at,
        "candidate_email": to_email,
        "email_delivery_status": "sending",
        "email_delivery_error": "",
        "send_request_id": request_id,
        **({"sent_at": utc_now()} if first_send else {}),
    })
    if not activated:
        raise AssessmentWorkflowError("Could not activate the assessment link. The email was not sent.", code="delivery_failed", status_code=500)

    actor = recruiter.get("username") or ""
    try:
        send_email(to_email, email["subject"], email["body"], from_email, primary_link=link)
    except EmailDeliveryUnknown as exc:
        # The server may have accepted the message: keep the link live and never resend automatically.
        assessment_repo.update_assessment(assessment_id, {"email_delivery_status": "unknown", "email_delivery_error": str(exc)})
        assessment_repo.push_delivery_event(assessment_id, {"status": "unknown", "to_email": to_email, "error": str(exc), "by": actor})
        db.log_audit("Assessment Email Uncertain", actor, f"Delivery of assessment #{assessment_id} to {to_email} could not be confirmed.",
                     int(assessment.get("jd_id") or 0) or None)
        return _response(assessment_repo.get_assessment_by_id(assessment_id) or {}, "delivery_unknown",
                         "The mail server did not confirm delivery. The link is active; check with the candidate or "
                         "copy the link before resending, so they are not emailed twice.")
    except Exception as exc:
        rollback = {"email_delivery_status": "failed", "email_delivery_error": str(exc)}
        if first_send:
            # Nothing reached the candidate: deactivate the link so a retry re-sends this same attempt.
            rollback.update({key: assessment.get(key) for key in ("status", "access_token", "token_expires_at", "sent_at")})
        assessment_repo.update_assessment(assessment_id, rollback)
        assessment_repo.push_delivery_event(assessment_id, {"status": "failed", "to_email": to_email, "error": str(exc), "by": actor})
        raise AssessmentWorkflowError(f"The assessment was generated but the email could not be sent: {exc}",
                                      code="delivery_failed", status_code=502, assessment_id=assessment_id) from exc

    assessment_repo.update_assessment(assessment_id, {"email_delivery_status": "sent", "email_sent_at": utc_now()})
    assessment_repo.push_delivery_event(assessment_id, {"status": "sent", "to_email": to_email, "by": actor})
    db.log_audit("Assessment Sent", actor, f"Sent assessment #{assessment_id} to '{assessment.get('candidate_name') or to_email}'.",
                 int(assessment.get("jd_id") or 0) or None)
    return _response(assessment_repo.get_assessment_by_id(assessment_id) or {}, "sent",
                     f"Assessment sent to {to_email}.")


def send_assessment_to_candidate(
    candidate_id: int,
    *,
    jd_id: int,
    recruiter: dict[str, Any],
    request_id: str = "",
    to_email: str = "",
    resend: bool = False,
) -> dict[str, Any]:
    request_id = str(request_id or "").strip()
    if request_id and not _REQUEST_ID.match(request_id):
        raise AssessmentWorkflowError("Invalid request id.", code="invalid_request")
    request_id = request_id or str(uuid.uuid4())

    candidate = db.get_candidate_by_id(candidate_id)
    if not candidate:
        raise AssessmentWorkflowError("Candidate not found.", code="candidate_not_found", status_code=404)
    jd = db.get_jd_by_id(jd_id, include_raw_text=False)
    if not jd:
        raise AssessmentWorkflowError("The selected job description no longer exists. Choose another JD.", code="invalid_jd", status_code=404)
    if str(jd.get("status") or "") == db.JD_CLOSED:
        raise AssessmentWorkflowError(f"“{jd.get('title')}” is closed. Reopen it or choose another JD.", code="jd_closed", status_code=409)
    email = _target_email(candidate, to_email)

    # A retry of a request that already went out returns its outcome instead of sending again.
    latest = assessment_repo.get_latest_assessment_for_candidate_jd(candidate_id, jd_id)
    if latest and latest.get("send_request_id") == request_id and latest.get("status") != AssessmentStatus.DRAFT:
        response = _response(latest, "replayed", "This request was already processed; no second email was sent.")
        return response

    _assert_delivery_configured()
    if not assessment_repo.claim_send_request(candidate_id, jd_id, request_id, SEND_LEASE_SECONDS):
        raise AssessmentWorkflowError("An assessment for this candidate and JD is already being generated. Wait a moment and refresh.",
                                      code="request_in_progress", status_code=409)

    state, error, assessment_id = "failed", "", None
    try:
        active = assessment_repo.get_active_assessment_for_candidate_jd(candidate_id, jd_id)
        if active:
            assessment_id = int(active["id"])
            status = str(active.get("status") or "")
            lifecycle = _lifecycle(active)
            if status == AssessmentStatus.IN_PROGRESS:
                raise AssessmentWorkflowError("The candidate is taking this assessment now; a new one cannot be sent.",
                                              code="attempt_in_progress", status_code=409, assessment=assessment_view(active))
            if status == AssessmentStatus.COMPLETED:
                raise AssessmentWorkflowError("The candidate has already submitted this assessment.",
                                              code="attempt_submitted", status_code=409, assessment=assessment_view(active))
            if status == AssessmentStatus.SENT and not resend:
                message = {
                    "delivery_unknown": "Delivery of the previous email could not be confirmed. Resend only if the candidate did not receive it.",
                    "expired": "The assessment link has expired. Resend to reactivate the same assessment with a new deadline.",
                }.get(lifecycle, "This assessment was already emailed to the candidate. Resend the same link?")
                raise AssessmentWorkflowError(message, code="already_sent", status_code=409, assessment=assessment_view(active))
            # DRAFT (e.g. an earlier email failure) or an explicit resend: same attempt, same link, no regeneration.
        else:
            screening_override = not _candidate_selected_for_jd(candidate_id, jd_id)
            try:
                generated = generate_assessment(
                    recruiter_id=int(recruiter["id"]),
                    candidate_id=candidate_id,
                    jd_id=jd_id,
                    passing_score=DEFAULT_PASSING_SCORE,
                    time_limit_minutes=DEFAULT_TIME_LIMIT_MINUTES,
                    require_selected=False,
                    provenance={"source": "send_assessment", "screening_override": screening_override,
                                "initiated_by": recruiter.get("username") or ""},
                )
            except AssessmentServiceError as exc:
                state, error = "generation_failed", str(exc)
                raise AssessmentWorkflowError(f"Assessment generation failed: {exc}", code="generation_failed", status_code=502) from exc
            assessment_id = int(generated["assessment"]["id"])
            if not _is_complete(generated):
                assessment_repo.delete_assessment_cascade(assessment_id)
                state, error, assessment_id = "generation_failed", "Generated assessment was incomplete.", None
                raise AssessmentWorkflowError("The generated assessment was incomplete and was discarded. Please retry.",
                                              code="generation_failed", status_code=502)
        current = assessment_repo.get_assessment_by_id(int(assessment_id)) or {}
        if current.get("status") == AssessmentStatus.DRAFT:
            # Generated (or an earlier unsent draft): the recruiter reviews it before anything is emailed.
            if email and normalize_email(email) != normalize_email(current.get("candidate_email") or ""):
                assessment_repo.update_assessment(int(assessment_id), {"candidate_email": normalize_email(email)})
                current = assessment_repo.get_assessment_by_id(int(assessment_id)) or current
            state = "draft_ready"
            return _response(current, "draft_ready", "The assessment was generated as a draft. Review it in the preview, then send it.")
        response = _deliver(assessment_id, recruiter=recruiter, to_email=email, request_id=request_id)
        state = response["code"]
        return response
    except AssessmentWorkflowError as exc:
        if state == "failed":
            state, error = exc.code, str(exc)
        raise
    finally:
        assessment_repo.finish_send_request(candidate_id, jd_id, request_id, state=state, error=error, assessment_id=assessment_id)


def _is_complete(generated: dict[str, Any]) -> bool:
    """Questions, scoring and instructions must all be present before a link is issued."""
    questions = generated.get("questions") or []
    assessment = generated.get("assessment") or {}
    if not questions or int(assessment.get("time_limit_minutes") or 0) <= 0 or int(assessment.get("passing_score") or 0) <= 0:
        return False
    for question in questions:
        if not str(question.get("question_text") or "").strip() or int(question.get("points") or 0) <= 0:
            return False
        question_type = getattr(question.get("question_type"), "value", question.get("question_type"))
        if question_type == "mcq" and len(question.get("options") or []) < 2:
            return False
    return True
