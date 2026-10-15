"""
Business logic for the Assessment module.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Any

import database as db
from assessment import proctoring_media
from assessment import repository as assessment_repo
from assessment.models import (
    ASSESSMENT_STAGE_LABELS,
    AssessmentStatus,
    DEFAULT_PASSING_SCORE,
    QuestionType,
    TOTAL_GENERATED_QUESTIONS,
    max_assessment_questions,
)
from assessment.schemas import SchemaValidationError
from assessment.generation import normalized_jd, requirement_catalog, validate_exam
from assessment.code_execution.preparation import prepare_executable_questions
from assessment.evaluation_service import evaluate_assessment
from assessment.utilities import (
    assert_status_transition,
    assessment_link,
    assessment_summary_payload,
    candidate_assessment_payload,
    candidate_question_payload,
    compute_assessment_duration_minutes,
    compute_link_status,
    generate_access_token,
    is_candidate_test_url,
    normalize_access_token,
    recruiter_question_payload,
    remaining_seconds,
    token_expiry,
    token_is_expired,
    parse_iso_datetime,
    utc_now,
    validate_public_assessment_link,
)
from email_utils import normalize_email
from services.interview_service import default_from_email, send_email
from services.json_parser import parse_json_response
from services.llm_service import LLMService
from services.prompt_service import PromptService


class AssessmentServiceError(ValueError):
    """Domain error surfaced to API callers."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _result_payload(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    return {
        "id": result.get("id"),
        "assessment_id": result.get("assessment_id"),
        "candidate_id": result.get("candidate_id"),
        "jd_id": result.get("jd_id"),
        "total_points": result.get("total_points"),
        "earned_points": result.get("earned_points"),
        "score": result.get("score") if result.get("score") is not None else result.get("earned_points"),
        "score_percentage": result.get("score_percentage"),
        "percentage": result.get("percentage") if result.get("percentage") is not None else result.get("score_percentage"),
        "mcq_percentage": result.get("mcq_percentage"),
        "passed": result.get("passed"),
        "status": result.get("status"),
        "question_results": result.get("question_results") or [],
        "evaluation_breakdown": result.get("evaluation_breakdown") or {},
        "pending_review_count": result.get("pending_review_count") or 0,
        "pass_basis": result.get("pass_basis"),
        "summary": result.get("summary") or "",
        "scored_at": result.get("scored_at"),
        "created_at": result.get("created_at"),
    }


def _assessment_meta(row: dict[str, Any]) -> dict[str, Any]:
    duration = compute_assessment_duration_minutes(row)
    return {
        "sent_at": row.get("sent_at"),
        "started_at": row.get("started_at"),
        "completed_at": row.get("completed_at"),
        "assessment_duration_minutes": duration,
        "link_status": compute_link_status(row),
    }


def record_candidate_outcome(assessment: dict[str, Any], status: str) -> None:
    """Propagate a final assessment status to the candidate's hiring stage.

    Every way an attempt ends (submission, re-grade, either kind of termination)
    goes through here so the Talent pages and the hiring process stay in step.
    """
    candidate_id = int(assessment.get("candidate_id") or 0)
    if not candidate_id:
        return
    if assessment.get("screening_override"):
        # Sent to a candidate who was not selected at screening: the recruiter reviews
        # the result and decides; the hiring stage is never moved automatically.
        db.log_audit("Assessment Result Ready", "",
                     f"Assessment #{assessment.get('id')} finished as {status}; awaiting recruiter review "
                     "(sent outside resume screening, hiring stage unchanged).",
                     int(assessment.get("jd_id") or 0) or None)
        return
    db.update_candidate(candidate_id, {"hiring_stage": ASSESSMENT_STAGE_LABELS.get(status, status.title())})
    if status == AssessmentStatus.PASSED:
        from services.hiring_process_service import advance_after_assessment
        advance_after_assessment(candidate_id, int(assessment.get("jd_id") or 0))


def _lookup_payload(row: dict[str, Any]) -> dict[str, Any]:
    assessment_id = int(row.get("id") or 0)
    result_row = assessment_repo.get_result_by_assessment_id(assessment_id)
    result = _result_payload(result_row)
    status = str(row.get("status") or AssessmentStatus.NOT_CREATED)
    return {
        "assessment": assessment_summary_payload(
            row,
            questions=assessment_repo.get_questions_for_assessment(assessment_id),
            include_token=False,
        ),
        "status": status,
        "result": result,
        "score": result.get("score") if result else None,
        "percentage": result.get("percentage") if result else None,
        "assessment_result": result.get("status") if result else None,
        "eligible_for_interview": status == AssessmentStatus.PASSED,
        **_assessment_meta(row),
    }


def is_assessment_passed_for_candidate_jd(candidate_id: int, jd_id: int) -> bool:
    row = assessment_repo.get_latest_assessment_for_candidate_jd(candidate_id, jd_id)
    return bool(row and str(row.get("status") or "") == AssessmentStatus.PASSED)


def is_eligible_for_interview(candidate_id: int, jd_id: int) -> bool:
    return _candidate_selected_for_jd(candidate_id, jd_id) and is_assessment_passed_for_candidate_jd(
        candidate_id, jd_id
    )


def enrich_candidates_with_assessments(candidates: list[dict[str, Any]], jd_id: int) -> list[dict[str, Any]]:
    if not candidates:
        return candidates
    latest_rows = {
        int(row.get("candidate_id") or 0): row
        for row in assessment_repo.get_latest_assessments_for_jd(jd_id)
    }
    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = int(candidate.get("id") or 0)
        row = latest_rows.get(candidate_id)
        patch = {
            "assessment_status": AssessmentStatus.NOT_CREATED,
            "assessment_score": None,
            "assessment_percentage": None,
            "assessment_result": None,
            "eligible_for_interview": False,
            "sent_at": None,
            "started_at": None,
            "completed_at": None,
            "assessment_duration_minutes": None,
            "link_status": "Not Sent",
        }
        if row:
            lookup = _lookup_payload(row)
            patch.update(
                {
                    "assessment_id": row.get("id"),
                    "assessment_status": lookup.get("status"),
                    "assessment_score": lookup.get("score"),
                    "assessment_percentage": lookup.get("percentage"),
                    "assessment_result": lookup.get("assessment_result"),
                    "eligible_for_interview": lookup.get("eligible_for_interview"),
                    "sent_at": lookup.get("sent_at"),
                    "started_at": lookup.get("started_at"),
                    "completed_at": lookup.get("completed_at"),
                    "assessment_duration_minutes": lookup.get("assessment_duration_minutes"),
                    "link_status": lookup.get("link_status"),
                }
            )
        enriched.append({**candidate, **patch})
    return enriched


def assessment_pipeline_snapshot(limit: int = 25) -> list[dict[str, Any]]:
    """Selected candidates across JDs with assessment progress for the dashboard."""
    mongo = db._database()
    comparisons = list(
        mongo.comparisons.find({"status": "Selected"}).sort("comparison_date", -1).limit(limit)
    )
    pipeline: list[dict[str, Any]] = []
    for comp in comparisons:
        candidate_id = int(comp.get("candidate_id") or 0)
        jd_id = int(comp.get("jd_id") or 0)
        if not candidate_id or not jd_id:
            continue
        candidate = db.get_candidate_by_id(candidate_id) or {}
        jd = db.get_jd_by_id(jd_id, include_raw_text=False) or {}
        assessment_row = assessment_repo.get_latest_assessment_for_candidate_jd(candidate_id, jd_id)
        interviews = db.get_interviews({"candidate_id": candidate_id, "jd_id": jd_id})
        latest_interview = interviews[-1] if interviews else None
        lookup = _lookup_payload(assessment_row) if assessment_row else {
            "status": AssessmentStatus.NOT_CREATED,
            "score": None,
            "percentage": None,
            "assessment_result": None,
            "eligible_for_interview": False,
            "assessment": None,
            "result": None,
            "sent_at": None,
            "started_at": None,
            "completed_at": None,
            "assessment_duration_minutes": None,
            "link_status": "Not Sent",
        }
        pipeline.append(
            {
                "candidate_id": candidate_id,
                "candidate_name": candidate.get("name") or "",
                "candidate_email": candidate.get("email") or "",
                "candidate_phone": candidate.get("phone") or "",
                "jd_id": jd_id,
                "jd_title": jd.get("title") or "",
                "match_score": int(comp.get("match_score") or 0),
                "assessment_id": assessment_row.get("id") if assessment_row else None,
                "assessment_status": lookup.get("status"),
                "assessment_score": lookup.get("score"),
                "assessment_percentage": lookup.get("percentage"),
                "assessment_result": lookup.get("assessment_result"),
                "eligible_for_interview": lookup.get("eligible_for_interview"),
                "sent_at": lookup.get("sent_at"),
                "started_at": lookup.get("started_at"),
                "completed_at": lookup.get("completed_at"),
                "assessment_duration_minutes": lookup.get("assessment_duration_minutes"),
                "link_status": lookup.get("link_status"),
                "termination_reason": (assessment_row or {}).get("termination_reason") or "",
                "interview": latest_interview,
                "interview_id": latest_interview.get("id") if latest_interview else None,
                "interview_status": latest_interview.get("status") if latest_interview else "",
            }
        )
    return pipeline


def _candidate_selected_for_jd(candidate_id: int, jd_id: int) -> bool:
    for candidate in db.get_candidates_for_jd(jd_id, "Selected"):
        if int(candidate.get("id") or 0) == int(candidate_id):
            return True
    return False


def _load_context(candidate_id: int, jd_id: int, *, require_selected: bool = True) -> dict[str, Any]:
    candidate = db.get_candidate_by_id(candidate_id)
    jd = db.get_jd_by_id(jd_id, include_raw_text=True)
    if not candidate:
        raise AssessmentServiceError("Candidate not found.")
    if not jd:
        raise AssessmentServiceError("Job description not found.")
    if require_selected and not _candidate_selected_for_jd(candidate_id, jd_id):
        raise AssessmentServiceError("Only selected candidates can receive assessments.")
    # The send-anyway path validates (or takes the recruiter's corrected) address itself.
    if require_selected and not candidate.get("email"):
        raise AssessmentServiceError("Candidate email is missing.")
    candidate = {**candidate, "email": normalize_email(candidate.get("email"))}
    return {"candidate": candidate, "jd": jd}


def _generate_questions_with_ai(jd: dict, *, previous_questions=None):
    """Generate for a posted job only; candidate details are assignment metadata."""
    context = normalized_jd(jd)
    if not (context["posted_jd_text"] or context["skills"] or context["responsibilities"] or context["structured_requirements"]):
        raise AssessmentServiceError("The posted JD has no requirements to assess. Add the complete JD first.")
    prompt_service = PromptService()
    feedback = ""
    catalog = requirement_catalog(context)
    try:
        llm = LLMService(model=os.getenv("ASSESSMENT_MODEL") or "gpt-4.1", temperature=0.6)
    except Exception as exc:
        raise AssessmentServiceError("AI assessment generation is unavailable. Check the configured AI service; no generic exam was created.") from exc
    for attempt in range(3):
        try:
            prompt = prompt_service.render(
                "assessment_generate.jinja", jd_data=context,
                total_questions=TOTAL_GENERATED_QUESTIONS, requirement_catalog=catalog,
                generation_nonce=uuid.uuid4().hex, validation_feedback=feedback,
            )
            exam = parse_json_response(llm.invoke(prompt, temperature=0.6))
            for question in exam.get("questions", []):
                if isinstance(question, dict) and question.get("jd_requirement_id"):
                    ref = question["jd_requirement_id"]
                    if not isinstance(ref, str) or ref not in catalog:
                        raise ValueError("Each jd_requirement_id must reference the supplied JD catalog.")
                    question["jd_requirement"] = catalog[ref]
            strict_tests = attempt < 2  # final attempt keeps questions whose tests are unusable
            rows = validate_exam(exam, context, TOTAL_GENERATED_QUESTIONS, previous_questions or (),
                                 require_tests=strict_tests)
            rows = prepare_executable_questions(rows, strict=strict_tests)
            review = parse_json_response(llm.invoke(prompt_service.render(
                "assessment_validate.jinja", jd_data=context, requirement_catalog=catalog, exam=exam,
            ), temperature=0.0))
            if not isinstance(review, dict) or review.get("valid") is not True or review.get("issues") != []:
                raise ValueError("JD review rejected the exam: " + str(review.get("issues", "invalid review") if isinstance(review, dict) else "invalid review"))
            return {key: exam[key] for key in ("exam_title", "job_title", "experience_required")}, rows
        except (ValueError, TypeError, KeyError) as exc:
            feedback = str(exc)[:2000]
        except Exception as exc:
            raise AssessmentServiceError("AI assessment generation failed. Please retry; the existing draft was preserved.") from exc
    raise AssessmentServiceError("The AI could not produce a complete, validated JD-based exam after three attempts. Please retry. " + feedback)


def _exam_payload(title, job_title, experience, questions):
    return {
        "exam_title": title, "job_title": job_title,
        "experience_required": experience or "Not specified",
        "total_questions": len(questions),
        "skills_covered": list(dict.fromkeys(q.get("skill_tag") for q in questions if q.get("skill_tag"))),
        "questions": [{
            "question_id": q.get("question_id") or f"Q{i+1:03d}",
            "question": q.get("question_text"), "question_type": str(q.get("question_type") or "mcq").upper(),
            "skill": q.get("skill_tag"), "correct_answer": q.get("correct_answer"),
            "options": q.get("options") or [], "starter_code": q.get("starter_code") or "",
            **{key: q.get(key) for key in ("difficulty", "scenario_type", "explanation", "evaluation_focus", "jd_requirement")},
        } for i, q in enumerate(questions)],
    }


def generate_jd_exam(jd_id: int):
    """Generate an unassigned exam without requiring a candidate or resume."""
    jd = db.get_jd_by_id(jd_id, include_raw_text=True)
    if not jd:
        raise AssessmentServiceError("Job description not found.")
    metadata, questions = _generate_questions_with_ai(jd)
    return _exam_payload(metadata["exam_title"], metadata["job_title"], metadata["experience_required"], questions)


def _build_assessment_response(assessment_id: int, *, reused: bool = False) -> dict[str, Any]:
    assessment = assessment_repo.get_assessment_by_id(assessment_id) or {}
    questions = assessment_repo.get_questions_for_assessment(assessment_id)
    return {
        "reused": reused,
        "exam": _exam_payload(assessment.get("title"), assessment.get("job_role"), assessment.get("experience_required"), questions),
        "assessment": assessment_summary_payload(assessment, questions=questions, include_token=False),
        "questions": [recruiter_question_payload(q) for q in questions],
    }


def generate_assessment(
    *,
    recruiter_id: int,
    candidate_id: int,
    jd_id: int,
    passing_score: int,
    time_limit_minutes: int,
    title: str = "",
    require_selected: bool = True,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """require_selected=False is the recruiter's explicit "send assessment anyway" path
    (candidate_assessment_service); provenance is stored on the assessment record."""
    ctx = _load_context(candidate_id, jd_id, require_selected=require_selected)
    candidate = ctx["candidate"]
    jd = ctx["jd"]

    existing = assessment_repo.get_active_assessment_for_candidate_jd(candidate_id, jd_id)
    existing_draft_id = 0
    if existing:
        status = str(existing.get("status") or "")
        if status == AssessmentStatus.DRAFT:
            existing_draft_id = int(existing["id"])
        else:
            raise AssessmentServiceError(
                f"An active assessment already exists (id={existing.get('id')}, status={status})."
            )

    previous_questions = [str(q.get("question_text") or "") for q in assessment_repo.get_recent_questions_for_jd(jd_id, limit=80)]
    generated_exam, generated_questions = _generate_questions_with_ai(
        jd,
        previous_questions=previous_questions,
    )
    assessment_id = assessment_repo.create_assessment(
        {
            "candidate_id": candidate_id,
            "jd_id": jd_id,
            "recruiter_id": recruiter_id,
            "status": AssessmentStatus.DRAFT,
            "title": title or generated_exam["exam_title"],
            "candidate_name": candidate.get("name") or "",
            "candidate_email": normalize_email(candidate.get("email")),
            "job_role": generated_exam["job_title"],
            "experience_required": generated_exam["experience_required"],
            "passing_score": passing_score,
            "time_limit_minutes": time_limit_minutes,
            **(provenance or {}),
        }
    )

    try:
        assessment_repo.create_questions_bulk(
            [{"assessment_id": assessment_id, **question} for question in generated_questions]
        )
    except Exception:
        assessment_repo.delete_assessment_cascade(assessment_id)
        raise
    if existing_draft_id:
        # Recruiter-defined coding questions are not part of the JD exam: keep them on the new draft.
        from services.coding_question_service import carry_over_custom_coding
        try:
            carry_over_custom_coding(existing, assessment_id)
        except Exception:
            assessment_repo.delete_assessment_cascade(assessment_id)
            raise
        assessment_repo.delete_assessment_cascade(existing_draft_id)

    db.log_audit(
        "Assessment Generated",
        "",
        f"AI-generated assessment #{assessment_id} for '{candidate.get('name')}' ({TOTAL_GENERATED_QUESTIONS} questions).",
        jd_id,
    )

    return _build_assessment_response(assessment_id, reused=False)


def lookup_assessment(candidate_id: int, jd_id: int) -> dict[str, Any]:
    row = assessment_repo.get_latest_assessment_for_candidate_jd(candidate_id, jd_id)
    if not row:
        return {
            "assessment": None,
            "status": AssessmentStatus.NOT_CREATED,
            "result": None,
            "score": None,
            "percentage": None,
            "assessment_result": None,
            "eligible_for_interview": False,
            "sent_at": None,
            "started_at": None,
            "completed_at": None,
            "assessment_duration_minutes": None,
            "link_status": "Not Sent",
        }
    return _lookup_payload(row)


def save_assessment_draft(assessment_id: int, patch: dict[str, Any]) -> dict[str, Any]:
    assessment = assessment_repo.get_assessment_by_id(assessment_id)
    if not assessment:
        raise AssessmentServiceError("Assessment not found.")
    if assessment.get("status") not in AssessmentStatus.editable_states():
        raise AssessmentServiceError("Only draft assessments can be saved.")

    if not assessment_repo.update_assessment(assessment_id, patch):
        raise AssessmentServiceError("No changes were applied.")
    return _build_assessment_response(assessment_id)


def get_assessment_detail(assessment_id: int) -> dict[str, Any]:
    assessment = assessment_repo.get_assessment_by_id(assessment_id)
    if not assessment:
        raise AssessmentServiceError("Assessment not found.")
    questions = assessment_repo.get_questions_for_assessment(assessment_id)
    answers = assessment_repo.get_answers_for_assessment(assessment_id)
    return {
        "assessment": assessment_summary_payload(assessment, questions=questions, include_token=True),
        "questions": [recruiter_question_payload(q) for q in questions],
        "answers": answers,
    }


def preview_assessment(assessment_id: int) -> dict[str, Any]:
    assessment = assessment_repo.get_assessment_by_id(assessment_id)
    if not assessment:
        raise AssessmentServiceError("Assessment not found.")
    questions = assessment_repo.get_questions_for_assessment(assessment_id)
    return {
        "assessment": assessment_summary_payload(assessment, questions=questions, include_token=False),
        "questions": [candidate_question_payload(q) for q in questions],
    }


def add_question(payload: dict[str, Any]) -> dict[str, Any]:
    assessment = assessment_repo.get_assessment_by_id(int(payload["assessment_id"]))
    if not assessment:
        raise AssessmentServiceError("Assessment not found.")
    if assessment.get("status") not in AssessmentStatus.editable_states():
        raise AssessmentServiceError("Questions can only be added while the assessment is in DRAFT status.")
    if assessment_repo.count_questions_for_assessment(int(assessment["id"])) >= max_assessment_questions():
        raise AssessmentServiceError(f"An assessment can have at most {max_assessment_questions()} questions.")

    if not payload.get("sort_order"):
        payload["sort_order"] = assessment_repo.count_questions_for_assessment(int(assessment["id"]))

    question_id = assessment_repo.create_question(payload)
    question = assessment_repo.get_question_by_id(question_id) or {}
    return {"question": recruiter_question_payload(question)}


def update_question(question_id: int, patch: dict[str, Any]) -> dict[str, Any]:
    question = assessment_repo.get_question_by_id(question_id)
    if not question:
        raise AssessmentServiceError("Question not found.")
    assessment = assessment_repo.get_assessment_by_id(int(question["assessment_id"]))
    if not assessment:
        raise AssessmentServiceError("Assessment not found.")
    if assessment.get("status") not in AssessmentStatus.editable_states():
        raise AssessmentServiceError("Questions can only be edited while the assessment is in DRAFT status.")

    merged = {**question, **patch}
    if merged.get("test_cases") and merged.get("question_type") in {"sql", "coding"} and (
            {"correct_answer", "sql_schema", "test_cases"} & set(patch)):
        # Expected results must follow the edited reference solution.
        import copy

        try:
            prepared = prepare_executable_questions([copy.deepcopy(merged)])[0]
        except ValueError as exc:
            raise AssessmentServiceError(f"The reference solution does not work with the test cases: {exc}") from exc
        patch = {**patch, "test_cases": prepared["test_cases"], "tests_verified": prepared.get("tests_verified", False)}
    if merged.get("question_type") in {"sql", "coding"} and ({"correct_answer", "sql_schema", "test_cases"} & set(patch)):
        from assessment.code_execution.verification import fingerprint

        patch = {**patch, "verification": None, "config_fingerprint": fingerprint({**question, **patch})}

    if not assessment_repo.update_question(question_id, patch):
        raise AssessmentServiceError("No changes were applied to the question.")
    updated = assessment_repo.get_question_by_id(question_id) or {}
    return {"question": recruiter_question_payload(updated)}


def _reference_question(question_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    question = assessment_repo.get_question_by_id(question_id)
    if not question:
        raise AssessmentServiceError("Question not found.", status_code=404)
    if str(question.get("question_type") or "") not in {"coding", "sql"}:
        raise AssessmentServiceError("Reference solutions apply to coding and SQL questions only.")
    assessment = assessment_repo.get_assessment_by_id(int(question["assessment_id"])) or {}
    return question, assessment


def _reference_payload(question: dict[str, Any], assessment: dict[str, Any]) -> dict[str, Any]:
    from assessment.code_execution.verification import execution_status, reference_language, verification_view

    return {
        "question_id": question.get("id"),
        "question_type": question.get("question_type"),
        "reference_solution": question.get("correct_answer") or "",
        "reference_language": reference_language(question),
        "sql_schema": question.get("sql_schema") or "",
        "order_matters": bool(question.get("order_matters")),
        "test_cases": question.get("test_cases") or [],
        "verification": verification_view(question),
        "editable": assessment.get("status") in AssessmentStatus.editable_states(),
        "execution": execution_status(),
    }


def get_reference_config(question_id: int) -> dict[str, Any]:
    question, assessment = _reference_question(question_id)
    return _reference_payload(question, assessment)


def save_reference_config(question_id: int, data: dict[str, Any], *, actor: str = "") -> dict[str, Any]:
    """Save the reference solution and test cases; any previous verification becomes stale."""
    from assessment.code_execution.languages import normalize_language
    from assessment.code_execution.verification import fingerprint, normalize_test_cases

    question, assessment = _reference_question(question_id)
    if assessment.get("status") not in AssessmentStatus.editable_states():
        raise AssessmentServiceError("Reference solutions and test cases can only be edited while the assessment is in DRAFT status.", status_code=409)
    if not isinstance(data, dict):
        raise AssessmentServiceError("Request body must be a JSON object.")
    qtype = str(question.get("question_type"))
    reference = data.get("reference_solution")
    if not isinstance(reference, str) or not reference.strip():
        raise AssessmentServiceError("reference_solution is required.")
    if len(reference) > 50_000:
        raise AssessmentServiceError("reference_solution is too long (50,000 characters maximum).")
    try:
        cases = normalize_test_cases(qtype, data.get("test_cases", question.get("test_cases") or []))
    except ValueError as exc:
        raise AssessmentServiceError(str(exc)) from exc
    patch: dict[str, Any] = {"correct_answer": reference, "test_cases": cases, "verification": None, "tests_verified": False}
    if qtype == "coding":
        language = normalize_language(data.get("reference_language") or question.get("reference_language") or "python")
        if not language:
            raise AssessmentServiceError("Unsupported reference language. Use Python, JavaScript, Java, C or C++.")
        patch["reference_language"] = language
    else:
        schema = data.get("sql_schema", question.get("sql_schema") or "")
        if not isinstance(schema, str) or "create table" not in schema.lower():
            raise AssessmentServiceError("sql_schema must contain CREATE TABLE statements.")
        patch["sql_schema"] = schema
        patch["order_matters"] = data.get("order_matters", question.get("order_matters")) is True
    patch["config_fingerprint"] = fingerprint({**question, **patch})
    assessment_repo.update_question(question_id, patch)
    db.log_audit("Assessment Reference Updated", actor,
                 f"Updated reference solution and {len(cases)} test case(s) for question #{question_id}.",
                 int(assessment.get("jd_id") or 0) or None)
    if data.get("verify") is True:
        return verify_reference_solution(question_id, actor=actor)
    updated = assessment_repo.get_question_by_id(question_id) or question
    return _reference_payload(updated, assessment)


def verify_reference_solution(question_id: int, *, actor: str = "") -> dict[str, Any]:
    """Execute the reference against enabled tests and record the result."""
    from assessment.code_execution.verification import fingerprint, verify_question

    question, assessment = _reference_question(question_id)
    current = fingerprint(question)
    verification, test_cases = verify_question(question)
    patch: dict[str, Any] = {"verification": verification, "tests_verified": verification["status"] == "verified",
                             "config_fingerprint": current}
    if str(question.get("question_type")) == "sql":
        patch["test_cases"] = test_cases  # expected results computed from the reference query
    if not assessment_repo.update_question_if_unchanged(question_id, question.get("config_fingerprint") or current, patch):
        raise AssessmentServiceError("The solution or test cases changed while verifying. Verify again.", status_code=409)
    updated = assessment_repo.get_question_by_id(question_id) or question
    return _reference_payload(updated, assessment)


def remove_question(question_id: int) -> dict[str, Any]:
    question = assessment_repo.get_question_by_id(question_id)
    if not question:
        raise AssessmentServiceError("Question not found.")
    assessment = assessment_repo.get_assessment_by_id(int(question["assessment_id"]))
    if not assessment:
        raise AssessmentServiceError("Assessment not found.")
    if assessment.get("status") not in AssessmentStatus.editable_states():
        raise AssessmentServiceError("Questions can only be deleted while the assessment is in DRAFT status.")
    if not assessment_repo.delete_question(question_id):
        raise AssessmentServiceError("Question could not be deleted.")
    return {"success": True, "question_id": question_id}


def _company_name() -> str:
    return (os.environ.get("COMPANY_NAME") or "ShimentoX").strip() or "ShimentoX"


def _ensure_assessment_link_in_body(body: str, link: str) -> str:
    """Always return an email body that contains only the validated candidate test URL."""
    if not is_candidate_test_url(link):
        raise AssessmentServiceError("Candidate test link is invalid.")

    generated = (
        "Please open the candidate test link below to begin your assessment.\n"
        "This link is only for taking the test — not the recruiter login page.\n\n"
        f"Candidate Test Link:\n{link}\n"
    )
    return generated


def _build_invite_email(assessment: dict[str, Any], link: str, from_email: str,
                        *, expires_at: datetime | None = None, instructions: bool = False) -> dict[str, str]:
    if not is_candidate_test_url(link):
        raise AssessmentServiceError("Candidate test link is invalid.")

    company = _company_name()
    candidate_name = assessment.get("candidate_name") or "Candidate"
    job_role = assessment.get("job_role") or "the role"
    title = assessment.get("title") or f"{job_role} Assessment"
    time_limit = int(assessment.get("time_limit_minutes") or 60)
    passing_score = int(assessment.get("passing_score") or DEFAULT_PASSING_SCORE)
    subject = f"{company} — Online Assessment Test: {title}"
    body = (
        f"Dear {candidate_name},\n\n"
        f"Thank you for progressing in the hiring process for the {job_role} role at {company}.\n\n"
        f"You are invited to complete your online assessment test.\n"
        f"Open only the candidate test link below (do not use the recruiter application login URL):\n\n"
        f"Candidate Test Link:\n"
        f"{link}\n\n"
        f"Assessment: {title}\n"
        f"Time limit: {time_limit} minutes\n"
        f"Passing score: {passing_score}%\n"
        + (f"Complete by: {expires_at:%d %b %Y, %H:%M} UTC (the link expires after this time)\n" if expires_at else "")
        + "\n"
        + ("Instructions:\n"
           "- Use a laptop or desktop with a stable internet connection, camera and microphone.\n"
           "- The timer starts when you begin and cannot be paused; answers are saved as you go.\n"
           "- Stay on the test tab: leaving it or exiting full screen is recorded and can end the attempt.\n"
           "- The link is personal to you; do not share it.\n\n" if instructions else "")
        + "Please complete the assessment at your earliest convenience.\n\n"
        "Best regards,\n"
        f"{company} Recruitment Team\n"
        f"{from_email}"
    )
    return {"subject": subject, "body": body}


def _generate_invite_email(assessment: dict[str, Any], link: str, from_email: str) -> dict[str, str]:
    """Build assessment invite email with the assessment URL placed directly in the body."""
    return _build_invite_email(assessment, link, from_email)


def _prepare_assessment_send(
    assessment_id: int,
    *,
    recruiter: dict[str, Any],
    to_email_override: str = "",
) -> tuple[dict[str, Any], str, str, datetime, str, str, str]:
    assessment = assessment_repo.get_assessment_by_id(assessment_id)
    if not assessment:
        raise AssessmentServiceError("Assessment not found.")

    current_status = str(assessment.get("status") or "")
    if current_status not in {AssessmentStatus.DRAFT, AssessmentStatus.SENT}:
        raise AssessmentServiceError("Assessment can only be sent from DRAFT status.")

    questions = assessment_repo.get_questions_for_assessment(assessment_id)
    if not questions:
        raise AssessmentServiceError("Assessment must contain at least one question before sending.")

    token = normalize_access_token(str(assessment.get("access_token") or "")) or generate_access_token()
    expires_at = token_expiry()
    try:
        link = assessment_link(token)
        validate_public_assessment_link(link)
    except ValueError as exc:
        raise AssessmentServiceError(str(exc)) from exc
    from_email = default_from_email(recruiter)
    to_email = normalize_email(to_email_override)
    if not to_email:
        to_email = normalize_email(str(assessment.get("candidate_email") or ""))
    if not to_email:
        candidate = db.get_candidate_by_id(int(assessment.get("candidate_id") or 0)) or {}
        to_email = normalize_email(str(candidate.get("email") or ""))
    if not to_email:
        raise AssessmentServiceError("Candidate email is missing.")

    return assessment, current_status, token, expires_at, link, from_email, to_email


def generate_assessment_email(
    assessment_id: int,
    *,
    recruiter: dict[str, Any],
    to_email_override: str = "",
) -> dict[str, Any]:
    assessment, _status, token, expires_at, link, from_email, to_email = _prepare_assessment_send(
        assessment_id,
        recruiter=recruiter,
        to_email_override=to_email_override,
    )

    if not str(assessment.get("access_token") or "").strip():
        assessment_repo.update_assessment(
            assessment_id,
            {"access_token": token, "token_expires_at": expires_at},
        )

    generated = _generate_invite_email(assessment, link, from_email)
    return {
        "from_email": from_email,
        "to_email": to_email,
        "subject": generated["subject"],
        "body": generated["body"],
        "assessment_link": link,
        "candidate_test_link": link,
    }


def send_assessment(
    assessment_id: int,
    *,
    recruiter: dict[str, Any],
    subject: str = "",
    body: str = "",
    regenerate_email: bool = True,
    to_email_override: str = "",
) -> dict[str, Any]:
    assessment, current_status, token, expires_at, link, from_email, to_email = _prepare_assessment_send(
        assessment_id,
        recruiter=recruiter,
        to_email_override=to_email_override,
    )

    generated = _generate_invite_email(assessment, link, from_email)
    subject = generated["subject"]
    body = generated["body"]

    if not is_candidate_test_url(link) or link not in body:
        raise AssessmentServiceError("Candidate test link could not be included in the email.")

    if current_status == AssessmentStatus.DRAFT:
        assert_status_transition(current_status, AssessmentStatus.SENT)

    saved = assessment_repo.update_assessment(
        assessment_id,
        {
            "status": AssessmentStatus.SENT,
            "access_token": token,
            "token_expires_at": expires_at,
            "sent_at": utc_now(),
            "candidate_email": to_email,
        },
    )

    if not saved:
        raise AssessmentServiceError("Could not activate the assessment link. Email was not sent.")
    try:
        send_email(to_email, subject, body, from_email, primary_link=link)
    except Exception:
        assessment_repo.update_assessment(assessment_id, {
            key: assessment.get(key) for key in
            ("status", "access_token", "token_expires_at", "sent_at", "candidate_email")
        })
        raise

    db.log_audit(
        "Assessment Sent",
        recruiter.get("username") or "",
        f"Sent assessment #{assessment_id} to '{assessment.get('candidate_name') or to_email}'.",
        int(assessment.get("jd_id") or 0) or None,
    )

    updated = assessment_repo.get_assessment_by_id(assessment_id) or {}
    return {
        "success": True,
        "assessment_id": assessment_id,
        "status": updated.get("status"),
        "access_token": token,
        "assessment_link": link,
        "token_expires_at": updated.get("token_expires_at"),
        "email": {"from_email": from_email, "to_email": to_email, "subject": subject, "body": body},
    }


def _resolve_token_assessment(token: str, *, allow_time_expired: bool = False) -> dict[str, Any]:
    raw_token = str(token or "").strip()
    if not raw_token:
        raise AssessmentServiceError("Assessment token is required.", status_code=400)

    assessment = assessment_repo.get_assessment_by_token(raw_token)
    if not assessment:
        raise AssessmentServiceError("Invalid assessment token.", status_code=404)

    if not str(assessment.get("access_token") or "").strip():
        raise AssessmentServiceError("Assessment token is not active.", status_code=403)

    if token_is_expired(assessment.get("token_expires_at")):
        raise AssessmentServiceError("Assessment link has expired.", status_code=410)

    status = str(assessment.get("status") or "")
    if status == AssessmentStatus.TERMINATED or int(assessment.get("proctoring_violation_count") or 0) >= 2:
        reason = str(assessment.get("termination_reason") or "Two proctoring violations")
        raise AssessmentServiceError(f"Assessment terminated: {reason}. This attempt cannot be resumed.", status_code=409)

    if status in AssessmentStatus.submitted_states():
        raise AssessmentServiceError("This assessment has already been submitted.", status_code=409)

    if status in AssessmentStatus.terminal_states():
        raise AssessmentServiceError("This assessment has already been completed.", status_code=409)

    if status not in AssessmentStatus.candidate_accessible_states():
        raise AssessmentServiceError("Assessment is not available yet.", status_code=403)

    remaining = remaining_seconds(assessment)
    if remaining is not None and remaining <= 0 and not allow_time_expired:
        raise AssessmentServiceError("Assessment time limit has expired.", status_code=403)

    return assessment


def _begin_candidate_session(assessment: dict[str, Any]) -> dict[str, Any]:
    """Mark assessment in progress after the candidate accepts the exam rules."""
    assessment_id = int(assessment["id"])
    current_status = str(assessment.get("status") or "")
    if current_status == AssessmentStatus.SENT:
        assert_status_transition(current_status, AssessmentStatus.IN_PROGRESS)
        assessment = assessment_repo.begin_candidate_attempt(assessment_id) or assessment
    if assessment.get("status") != AssessmentStatus.IN_PROGRESS:
        raise AssessmentServiceError("This assessment cannot be started.", status_code=409)
    return assessment


def get_assessment_by_token(token: str) -> dict[str, Any]:
    assessment = _resolve_token_assessment(token)
    questions = assessment_repo.get_questions_for_assessment(int(assessment["id"]))
    saved_answers = assessment_repo.get_answers_for_assessment(int(assessment["id"]))
    return {
        "assessment": candidate_assessment_payload(assessment, questions=questions),
        "questions": [candidate_question_payload(q) for q in questions],
        "saved_answers": [
            {
                "question_id": row.get("question_id"),
                "answer": row.get("answer") or "",
                "language": row.get("language") or "",
                "updated_at": row.get("updated_at"),
            }
            for row in saved_answers
        ],
    }


TERMS_VERSION = "assessment-proctoring-v2"


def start_candidate_assessment(token: str, *, accepted_terms: bool = False, recording_consent: bool = False) -> dict[str, Any]:
    assessment = _resolve_token_assessment(token)
    if accepted_terms is not True:
        raise AssessmentServiceError("Accept the assessment terms and conditions before starting.", status_code=400)
    if recording_consent is not True:
        raise AssessmentServiceError("Consent to camera, microphone and screen recording before starting.", status_code=400)
    if not proctoring_media.has_verified_reference(int(assessment["id"])):
        raise AssessmentServiceError("Capture a clear photo of your face before starting.", status_code=409)
    assessment = _begin_candidate_session(assessment)
    now = utc_now()
    acceptance = {"terms_accepted_at": now, "terms_version": TERMS_VERSION, "recording_consent_at": now}
    if not assessment_repo.update_assessment(int(assessment["id"]), acceptance):
        raise AssessmentServiceError("Could not record terms acceptance. Please retry.", status_code=503)
    assessment = {**assessment, **acceptance}
    return {"success": True, "assessment": candidate_assessment_payload(assessment, questions=[])}


def report_proctoring_violation(token: str, event_id: str, reason: str) -> dict[str, Any]:
    # Idempotent retries remain valid even after this event terminates the attempt.
    assessment = assessment_repo.get_assessment_by_token(str(token or "").strip())
    if not assessment:
        raise AssessmentServiceError("Invalid assessment token.", status_code=404)
    if assessment.get("status") != AssessmentStatus.TERMINATED:
        assessment = _resolve_token_assessment(token, allow_time_expired=True)
        if assessment.get("status") != AssessmentStatus.IN_PROGRESS:
            raise AssessmentServiceError("Start the assessment before reporting a violation.", status_code=409)
        assessment = assessment_repo.record_proctoring_violation(int(assessment["id"]), event_id, reason)
        if not assessment:
            raise AssessmentServiceError("Could not record exam violation.", status_code=503)
        if assessment.get("status") == AssessmentStatus.TERMINATED:
            assessment_repo.mark_answers_final(int(assessment["id"]))
            record_candidate_outcome(assessment, AssessmentStatus.TERMINATED)
            db.log_audit("Assessment Terminated", "",
                f"Assessment #{assessment['id']} terminated after two proctoring violations.",
                int(assessment.get("jd_id") or 0) or None)
    return {"success": True, "status": assessment.get("status"),
            "violation_count": int(assessment.get("proctoring_violation_count") or 0),
            "terminated": assessment.get("status") == AssessmentStatus.TERMINATED}


# Late chunks from the final recorder flush are accepted for this long after the attempt closes.
RECORDING_GRACE = timedelta(minutes=15)


def _face_status(assessment: dict[str, Any], face_ok: bool) -> dict[str, Any]:
    return {"success": True, "face_ok": face_ok, "status": assessment.get("status"),
            "face_violation_count": int(assessment.get("face_violation_count") or 0),
            "terminated": assessment.get("status") == AssessmentStatus.TERMINATED,
            "termination_reason": assessment.get("termination_reason") or ""}


def store_face_snapshot(token: str, *, snapshot_id: str, kind: str, image: bytes, mime_type: str,
                        face_count: int, face_ok: bool, issue: str) -> dict[str, Any]:
    """Persist a candidate photo. A periodic photo without a visible, forward-facing face
    is a violation; the second violation terminates the attempt."""
    raw = assessment_repo.get_assessment_by_token(str(token or "").strip())
    if not raw:
        raise AssessmentServiceError("Invalid assessment token.", status_code=404)
    aid = int(raw["id"])
    if proctoring_media.find_snapshot(aid, snapshot_id):
        # Idempotent retry: report the outcome without counting it again.
        return _face_status(raw, face_ok)
    assessment = _resolve_token_assessment(token, allow_time_expired=True)
    if kind == "periodic" and assessment.get("status") != AssessmentStatus.IN_PROGRESS:
        raise AssessmentServiceError("Start the assessment before sending exam photos.", status_code=409)
    proctoring_media.insert_snapshot(assessment, snapshot_id=snapshot_id, kind=kind, image=image,
                                     mime_type=mime_type, face_count=face_count, face_ok=face_ok,
                                     issue=issue, captured_at=utc_now())
    if kind == "periodic" and not face_ok:
        assessment = proctoring_media.record_face_violation(aid, snapshot_id, issue) or assessment
        if assessment.get("status") == AssessmentStatus.TERMINATED:
            assessment_repo.mark_answers_final(aid)
            record_candidate_outcome(assessment, AssessmentStatus.TERMINATED)
            db.log_audit("Assessment Terminated", "",
                f"Assessment #{aid} terminated: face not detected on camera twice.",
                int(assessment.get("jd_id") or 0) or None)
    return _face_status(assessment, face_ok)


def store_recording_chunk(token: str, *, stream: str, session_id: str, sequence: int,
                          data: bytes, mime_type: str) -> dict[str, Any]:
    assessment = assessment_repo.get_assessment_by_token(str(token or "").strip())
    if not assessment or not str(assessment.get("access_token") or "").strip():
        raise AssessmentServiceError("Invalid assessment token.", status_code=404)
    status = str(assessment.get("status") or "")
    if not assessment.get("started_at"):
        raise AssessmentServiceError("Start the assessment before uploading recordings.", status_code=409)
    if status != AssessmentStatus.IN_PROGRESS:
        closed = parse_iso_datetime(assessment.get("completed_at"))
        if status not in AssessmentStatus.submitted_states() or not closed or utc_now() - closed > RECORDING_GRACE:
            raise AssessmentServiceError("This assessment is no longer accepting recordings.", status_code=409)
    stored = proctoring_media.store_recording_chunk(assessment, stream=stream, session_id=session_id,
                                                    sequence=sequence, data=data, mime_type=mime_type)
    return {"success": True, "stored": stored, "sequence": sequence}


def get_proctoring_evidence(assessment_id: int) -> dict[str, Any]:
    assessment = assessment_repo.get_assessment_by_id(int(assessment_id))
    if not assessment:
        raise AssessmentServiceError("Assessment not found.", status_code=404)
    events = [{"type": "focus", **event} for event in assessment.get("proctoring_events") or []]
    events += [{"type": "face", **event} for event in assessment.get("face_violations") or []]
    return {
        "assessment_id": int(assessment_id),
        "candidate_name": assessment.get("candidate_name") or "",
        "status": assessment.get("status"),
        "termination_reason": assessment.get("termination_reason") or "",
        "recording_consent_at": assessment.get("recording_consent_at"),
        "face_violation_count": int(assessment.get("face_violation_count") or 0),
        "proctoring_violation_count": int(assessment.get("proctoring_violation_count") or 0),
        "events": sorted(events, key=lambda event: str(event.get("recorded_at") or "")),
        "snapshots": proctoring_media.list_snapshots(int(assessment_id)),
        "recordings": proctoring_media.list_recording_sessions(int(assessment_id)),
    }


def get_proctoring_snapshot(assessment_id: int, snapshot_id: str) -> tuple[bytes, str]:
    row = proctoring_media.find_snapshot(int(assessment_id), snapshot_id)
    if not row:
        raise AssessmentServiceError("Snapshot not found.", status_code=404)
    return bytes(row["image"]), row.get("mime_type") or "image/jpeg"


def get_recording_chunk(assessment_id: int, stream: str, session_id: str, sequence: int) -> tuple[bytes, str]:
    chunk = proctoring_media.read_recording_chunk(int(assessment_id), stream, session_id, sequence)
    if not chunk:
        raise AssessmentServiceError("Recording chunk not found.", status_code=404)
    return chunk


def save_answer(token: str, question_id: int, answer: str, language: str = "") -> dict[str, Any]:
    assessment = _resolve_token_assessment(token)
    assessment_id = int(assessment["id"])
    question = assessment_repo.get_question_by_id(question_id)
    if not question or int(question.get("assessment_id") or 0) != assessment_id:
        raise AssessmentServiceError("Question not found for this assessment.")

    current_status = str(assessment.get("status") or "")
    if current_status == AssessmentStatus.SENT:
        raise AssessmentServiceError("Start the assessment before saving answers.", status_code=409)

    answer_id = assessment_repo.upsert_candidate_answer(
        assessment_id,
        question_id,
        answer,
        is_final=False,
        language=_answer_language(question, language),
    )
    return {
        "success": True,
        "answer_id": answer_id,
        "question_id": question_id,
        "status": AssessmentStatus.IN_PROGRESS,
    }


def _answer_language(question: dict[str, Any], language: str) -> str | None:
    if str(question.get("question_type") or "") != "coding" or not language:
        return None
    from assessment.code_execution.languages import normalize_language

    normalized = normalize_language(language)
    if not normalized:
        raise AssessmentServiceError("Unsupported programming language.")
    return normalized


def run_candidate_code(token: str, question_id: int, code: str, language: str = "") -> dict[str, Any]:
    """Run an answer against the question's visible sample tests only (the Run button)."""
    from assessment.code_execution.grader import grade_answer, outcome_dicts
    from assessment.code_execution.judge0 import ExecutionUnavailable

    assessment = _resolve_token_assessment(token)
    if assessment.get("status") != AssessmentStatus.IN_PROGRESS:
        raise AssessmentServiceError("Start the assessment before running code.", status_code=409)
    question = assessment_repo.get_question_by_id(question_id)
    if not question or int(question.get("assessment_id") or 0) != int(assessment["id"]):
        raise AssessmentServiceError("Question not found for this assessment.", status_code=404)
    if str(question.get("question_type") or "") not in {"coding", "sql"}:
        raise AssessmentServiceError("Only coding and SQL questions can be run.")
    if not any(isinstance(c, dict) and not c.get("hidden") for c in question.get("test_cases") or []):
        raise AssessmentServiceError("This question has no sample tests to run. Your answer will still be graded on submit.", status_code=409)
    if not str(code or "").strip():
        raise AssessmentServiceError("Write some code before running it.")
    if len(code) > 50_000:
        raise AssessmentServiceError("The answer is too long to run (50,000 characters maximum).")
    limit = int(os.environ.get("ASSESSMENT_MAX_RUNS_PER_QUESTION") or 30)
    if not assessment_repo.consume_code_run(int(assessment["id"]), int(question_id), limit):
        raise AssessmentServiceError(f"Run limit reached for this question ({limit} runs). Your answer will still be graded on submit.", status_code=429)
    try:
        graded = grade_answer(question, code, language, include_hidden=False)
    except ValueError as exc:
        raise AssessmentServiceError(str(exc)) from exc
    except ExecutionUnavailable as exc:
        raise AssessmentServiceError(f"Code could not be run right now: {exc}", status_code=503) from exc
    summary = graded.summary()
    return {
        "method": graded.method, "language": graded.language, "note": graded.note,
        "passed": graded.passed, "total": graded.total, "tests": outcome_dicts(graded),
        "hidden_test_count": sum(1 for c in question.get("test_cases") or [] if isinstance(c, dict) and c.get("hidden")),
        "feedback": summary["feedback"],
    }


def _scoring_summary(scoring: dict[str, Any], passing_score: int) -> str:
    pending_note = ""
    coding_results = [r for r in scoring["question_results"] if r.get("question_type") in {"coding", "sql"}]
    if coding_results:
        passed_tests = sum(int((r.get("metadata") or {}).get("tests_passed") or 0) for r in coding_results)
        total_tests = sum(int((r.get("metadata") or {}).get("tests_total") or 0) for r in coding_results)
        if total_tests:
            pending_note += f" Coding/SQL tests passed: {passed_tests}/{total_tests} (including hidden tests)."
        if any(r.get("evaluation_method") == "ai_estimated" for r in coding_results):
            pending_note += " Some coding answers were AI-estimated because code execution is not configured."
    if int(scoring.get("pending_review_count") or 0) > 0:
        pending_note += f" {scoring['pending_review_count']} coding/SQL answer(s) could not be graded automatically (counted as 0)."
    return (
        f"Score: {scoring['score_percentage']}% ({scoring['earned_points']}/{scoring['total_points']} points). "
        f"Passing score: {passing_score}%.{pending_note}"
    )


def _result_document(assessment: dict[str, Any], scoring: dict[str, Any], final_status: str, summary: str) -> dict[str, Any]:
    return {
        "assessment_id": int(assessment["id"]),
        "candidate_id": int(assessment.get("candidate_id") or 0),
        "jd_id": int(assessment.get("jd_id") or 0),
        "total_points": scoring["total_points"],
        "earned_points": scoring["earned_points"],
        "score": scoring["score"],
        "score_percentage": scoring["score_percentage"],
        "percentage": scoring["percentage"],
        "mcq_percentage": scoring.get("mcq_percentage"),
        "passed": bool(scoring["passed"]),
        "status": final_status,
        "question_results": scoring["question_results"],
        "evaluation_breakdown": scoring.get("evaluation_breakdown"),
        "pending_review_count": scoring.get("pending_review_count"),
        "pass_basis": scoring.get("pass_basis"),
        "summary": summary,
        "scored_at": utc_now(),
    }


def regrade_assessment(assessment_id: int, *, actor: str = "") -> dict[str, Any]:
    """Score a submitted assessment's saved final answers again with the current graders.

    Used for results recorded before automatic coding/SQL grading existed, or after
    code execution is configured. Answers are never changed; only the result is.
    """
    assessment = assessment_repo.get_assessment_by_id(int(assessment_id))
    if not assessment:
        raise AssessmentServiceError("Assessment not found.", status_code=404)
    previous_status = str(assessment.get("status") or "")
    if previous_status not in {AssessmentStatus.COMPLETED, AssessmentStatus.PASSED, AssessmentStatus.FAILED}:
        raise AssessmentServiceError("Only submitted assessments can be re-graded.", status_code=409)
    questions = assessment_repo.get_questions_for_assessment(int(assessment_id))
    rows = assessment_repo.get_answers_for_assessment(int(assessment_id))
    answers = {int(r.get("question_id") or 0): str(r.get("answer") or "") for r in rows}
    languages = {int(r.get("question_id") or 0): str(r.get("language") or "") for r in rows}
    passing_score = int(assessment.get("passing_score") or DEFAULT_PASSING_SCORE)
    scoring = evaluate_assessment(questions, answers, passing_score=passing_score, languages_by_question=languages)
    passed = bool(scoring["passed"])
    final_status = AssessmentStatus.PASSED if passed else AssessmentStatus.FAILED
    summary = _scoring_summary(scoring, passing_score) + " (Re-graded.)"
    result_id = assessment_repo.upsert_assessment_result(_result_document(assessment, scoring, final_status, summary))

    if final_status != previous_status:
        assessment_repo.update_assessment(int(assessment_id), {"status": final_status})
        record_candidate_outcome(assessment, final_status)
    db.log_audit(
        "Assessment Re-graded",
        actor,
        f"Assessment #{assessment_id} re-graded: {previous_status} -> {final_status} ({scoring['score_percentage']}%).",
        int(assessment.get("jd_id") or 0) or None,
    )
    return get_assessment_result(int(assessment_id), result_id=result_id)


def submit_assessment(token: str, answers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    assessment = _resolve_token_assessment(token, allow_time_expired=True)
    assessment_id = int(assessment["id"])
    questions = assessment_repo.get_questions_for_assessment(assessment_id)
    if not questions:
        raise AssessmentServiceError("Assessment has no questions.")
    if assessment.get("status") != AssessmentStatus.IN_PROGRESS:
        raise AssessmentServiceError("Start the assessment before submitting answers.", status_code=409)

    answers_by_question: dict[int, str] = {}
    saved_rows = assessment_repo.get_answers_for_assessment(assessment_id)
    languages_by_question: dict[int, str] = {
        int(row.get("question_id") or 0): str(row.get("language") or "") for row in saved_rows
    }
    expired = remaining_seconds(assessment) == 0
    if answers and not expired:
        for item in answers:
            answers_by_question[int(item["question_id"])] = str(item.get("answer") or "")
            if item.get("language"):
                languages_by_question[int(item["question_id"])] = str(item["language"])
    else:
        for row in saved_rows:
            answers_by_question[int(row.get("question_id") or 0)] = str(row.get("answer") or "")

    for question in questions:
        qid = int(question.get("id") or 0)
        answer_text = answers_by_question.get(qid, "")
        try:
            language = _answer_language(question, languages_by_question.get(qid, ""))
        except AssessmentServiceError:
            language = None
        assessment_repo.upsert_candidate_answer(assessment_id, qid, answer_text, is_final=True, language=language)

    passing_score = int(assessment.get("passing_score") or DEFAULT_PASSING_SCORE)
    scoring = evaluate_assessment(questions, answers_by_question, passing_score=passing_score,
                                  languages_by_question=languages_by_question)
    passed = bool(scoring["passed"])
    final_status = AssessmentStatus.PASSED if passed else AssessmentStatus.FAILED
    summary = _scoring_summary(scoring, passing_score)

    current_status = str(assessment.get("status") or AssessmentStatus.IN_PROGRESS)
    assert_status_transition(current_status, AssessmentStatus.COMPLETED)
    if not assessment_repo.complete_candidate_attempt(assessment_id):
        raise AssessmentServiceError("This assessment is closed and cannot be submitted.", status_code=409)
    assert_status_transition(AssessmentStatus.COMPLETED, final_status)
    assessment_repo.update_assessment(assessment_id, {"status": final_status})
    assessment_repo.mark_answers_final(assessment_id)

    result_id = assessment_repo.upsert_assessment_result(_result_document(assessment, scoring, final_status, summary))

    record_candidate_outcome(assessment, final_status)

    db.log_audit(
        "Assessment Completed",
        "",
        f"Assessment #{assessment_id} completed with status {final_status} ({scoring['score_percentage']}%).",
        int(assessment.get("jd_id") or 0) or None,
    )

    return get_assessment_result(assessment_id, result_id=result_id)


def get_assessment_result(assessment_id: int, *, result_id: int | None = None) -> dict[str, Any]:
    assessment = assessment_repo.get_assessment_by_id(assessment_id)
    if not assessment:
        raise AssessmentServiceError("Assessment not found.")

    result = assessment_repo.get_result_by_assessment_id(assessment_id)
    if not result:
        return {
            "assessment": assessment_summary_payload(assessment, include_token=False),
            "result": None,
            "status": assessment.get("status") or AssessmentStatus.NOT_CREATED,
        }

    return {
        "assessment": assessment_summary_payload(assessment, include_token=False),
        "result": _result_payload(result),
        "status": assessment.get("status"),
        "score": result.get("score") if result.get("score") is not None else result.get("earned_points"),
        "percentage": result.get("percentage") if result.get("percentage") is not None else result.get("score_percentage"),
    }


__all__ = [
    "AssessmentServiceError",
    "SchemaValidationError",
    "generate_assessment",
    "lookup_assessment",
    "save_assessment_draft",
    "get_assessment_detail",
    "preview_assessment",
    "generate_assessment_email",
    "add_question",
    "update_question",
    "remove_question",
    "send_assessment",
    "get_assessment_by_token",
    "start_candidate_assessment",
    "report_proctoring_violation",
    "store_face_snapshot",
    "store_recording_chunk",
    "get_proctoring_evidence",
    "get_proctoring_snapshot",
    "get_recording_chunk",
    "save_answer",
    "submit_assessment",
    "get_assessment_result",
    "is_eligible_for_interview",
    "is_assessment_passed_for_candidate_jd",
    "enrich_candidates_with_assessments",
    "assessment_pipeline_snapshot",
]
