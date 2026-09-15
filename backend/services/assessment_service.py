"""
Business logic for the Assessment module.
"""

from __future__ import annotations

import json
import os
import random
import uuid
from datetime import datetime
from typing import Any

import database as db
from assessment import repository as assessment_repo
from assessment.models import (
    AssessmentStatus,
    CODING_COUNT,
    DEFAULT_PASSING_SCORE,
    MCQ_COUNT,
    QuestionType,
    SQL_COUNT,
    TOTAL_GENERATED_QUESTIONS,
)
from assessment.schemas import SchemaValidationError
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
    utc_now,
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


def _load_context(candidate_id: int, jd_id: int) -> dict[str, Any]:
    candidate = db.get_candidate_by_id(candidate_id)
    jd = db.get_jd_by_id(jd_id, include_raw_text=False)
    if not candidate:
        raise AssessmentServiceError("Candidate not found.")
    if not jd:
        raise AssessmentServiceError("Job description not found.")
    if not _candidate_selected_for_jd(candidate_id, jd_id):
        raise AssessmentServiceError("Only selected candidates can receive assessments.")
    if not candidate.get("email"):
        raise AssessmentServiceError("Candidate email is missing.")
    candidate = {**candidate, "email": normalize_email(candidate.get("email"))}
    return {"candidate": candidate, "jd": jd}


def _normalized_jd_payload(jd_row: dict) -> dict:
    jd_json = jd_row.get("structured_data") or {}
    if isinstance(jd_json, str):
        jd_json = json.loads(jd_json)
    if not isinstance(jd_json, dict):
        jd_json = {}
    skills = jd_json.get("required_skills") or jd_row.get("skills") or []
    jd_json.setdefault("job_title", jd_row.get("title", "Unknown"))
    jd_json.setdefault("required_skills", skills)
    jd_json.setdefault("preferred_skills", [])
    jd_json.setdefault("experience_range", jd_row.get("experience_required") or "")
    jd_json.setdefault("responsibilities", jd_row.get("responsibilities") or [])
    return jd_json


def _fallback_questions(jd: dict) -> list[dict[str, Any]]:
    """Fallback question set with light variation when AI output is incomplete."""
    skills = list(jd.get("skills") or []) or ["General Skills", "Problem Solving", "Communication"]
    random.shuffle(skills)
    mcq_templates = [
        "Which option best demonstrates production-ready proficiency in {skill}?",
        "In a real project, what is the strongest evidence that a candidate can apply {skill} effectively?",
        "Which behavior most clearly shows practical experience with {skill}?",
    ]
    coding_templates = [
        "Write a function that solves a practical {skill} problem relevant to the {role} position. Include time complexity in a comment.",
        "Implement a small utility for a {role} workflow using {skill}. Handle invalid input and explain the complexity.",
        "Build a concise solution for a realistic {skill} task a {role} would face. Include one edge-case check.",
    ]
    sql_prompts = [
        (
            "Given tables `employees(id, name, department_id)` and "
            "`departments(id, name)`, write a SQL query to list each department "
            "name with the count of employees in that department.",
            "SELECT d.name, COUNT(e.id) AS employee_count FROM departments d LEFT JOIN employees e ON e.department_id = d.id GROUP BY d.name;",
        ),
        (
            "Given tables `candidates(id, name)` and `applications(id, candidate_id, status)`, "
            "write a SQL query to count selected applications per candidate.",
            "SELECT c.name, COUNT(a.id) AS selected_count FROM candidates c LEFT JOIN applications a ON a.candidate_id = c.id AND a.status = 'Selected' GROUP BY c.name;",
        ),
    ]
    questions: list[dict[str, Any]] = []
    order = 0

    for index in range(MCQ_COUNT):
        skill = skills[index % len(skills)]
        correct = f"Demonstrated production experience with {skill}"
        distractors = [
            f"No experience with {skill}",
            "Only theoretical knowledge",
            "Unrelated experience",
            "Unable to explain tradeoffs",
        ]
        options = [correct, *random.sample(distractors, 3)]
        random.shuffle(options)
        questions.append(
            {
                "question_text": random.choice(mcq_templates).format(skill=skill),
                "question_type": QuestionType.MCQ.value,
                "options": options,
                "correct_answer": correct,
                "starter_code": "",
                "points": 10,
                "skill_tag": str(skill),
                "sort_order": order,
            }
        )
        order += 1

    for index in range(CODING_COUNT):
        skill = skills[index % len(skills)]
        questions.append(
            {
                "question_text": random.choice(coding_templates).format(skill=skill, role=jd.get("title") or "role"),
                "question_type": QuestionType.CODING.value,
                "options": [],
                "correct_answer": f"# Reference solution using {skill}",
                "starter_code": "def solution(data):\n    # Your code here\n    pass\n",
                "points": 20,
                "skill_tag": str(skill),
                "sort_order": order,
            }
        )
        order += 1

    sql_question, sql_answer = random.choice(sql_prompts)
    questions.append(
        {
            "question_text": sql_question,
            "question_type": QuestionType.SQL.value,
            "options": [],
            "correct_answer": sql_answer,
            "starter_code": "",
            "points": 15,
            "skill_tag": "SQL",
            "sort_order": order,
        }
    )
    return questions


def _normalize_ai_question(item: dict[str, Any], question_type: str, sort_order: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    text = str(item.get("question_text") or "").strip()
    if not text:
        return None
    options = [str(x).strip() for x in (item.get("options") or []) if str(x).strip()]
    correct_answer = str(item.get("correct_answer") or "").strip()
    if question_type == QuestionType.MCQ.value:
        options = list(dict.fromkeys(options))[:4]
        if len(options) != 4 or correct_answer not in options:
            return None
    return {
        "question_text": text,
        "question_type": question_type,
        "options": options,
        "correct_answer": correct_answer,
        "starter_code": str(item.get("starter_code") or "").strip(),
        "points": int(item.get("points") or 10),
        "skill_tag": str(item.get("skill_tag") or "").strip(),
        "sort_order": sort_order,
    }


def _previous_question_texts(jd_id: int, *, limit: int = 40) -> list[str]:
    questions = assessment_repo.get_recent_questions_for_jd(jd_id, limit=limit)
    texts = []
    for row in questions:
        text = str(row.get("question_text") or "").strip()
        if text:
            texts.append(text[:240])
    return list(dict.fromkeys(texts))


def _variation_blueprint(jd: dict) -> str:
    skills = [str(skill).strip() for skill in (jd.get("skills") or []) if str(skill).strip()]
    focus_skill = random.choice(skills) if skills else str(jd.get("title") or "role fundamentals")
    blueprint_options = [
        f"Scenario-heavy assessment focused on practical {focus_skill} work, debugging, and tradeoffs.",
        f"Concept-depth assessment using different edge cases, production constraints, and {focus_skill} examples.",
        f"Hands-on assessment with output prediction, troubleshooting, and role-specific implementation tasks around {focus_skill}.",
        f"Mixed-difficulty assessment emphasizing design choices, failure modes, and applied {focus_skill} decisions.",
    ]
    return random.choice(blueprint_options)


def _generate_questions_with_ai(
    jd: dict,
    candidate: dict,
    *,
    previous_questions: list[str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    generation_nonce = uuid.uuid4().hex
    prompt_service = PromptService()
    llm = None
    title = f"{jd.get('title') or 'Role'} Technical Assessment"
    questions: list[dict[str, Any]] = []
    for temperature in (0.7, 0.55):
        prompt = prompt_service.render(
            "assessment_generate.jinja",
            jd_data=_normalized_jd_payload(jd),
            resume_data=candidate.get("structured_data") or {},
            mcq_count=MCQ_COUNT,
            coding_count=CODING_COUNT,
            sql_count=SQL_COUNT,
            generation_nonce=generation_nonce,
            variation_blueprint=_variation_blueprint(jd),
            previous_questions=(previous_questions or [])[:20],
        )
        try:
            llm = llm or LLMService(temperature=temperature)
            raw = llm.invoke(prompt, temperature=temperature)
            parsed = parse_json_response(raw)
        except Exception:
            parsed = {}

        title = str(parsed.get("title") or title).strip()
        questions = []
        order = 0

        for item in (parsed.get("mcq_questions") or [])[:MCQ_COUNT]:
            row = _normalize_ai_question(item, QuestionType.MCQ.value, order)
            if row:
                questions.append(row)
                order += 1

        for item in (parsed.get("coding_questions") or [])[:CODING_COUNT]:
            row = _normalize_ai_question(item, QuestionType.CODING.value, order)
            if row:
                if not row["starter_code"]:
                    row["starter_code"] = "def solution():\n    pass\n"
                questions.append(row)
                order += 1

        for item in (parsed.get("sql_questions") or [])[:SQL_COUNT]:
            row = _normalize_ai_question(item, QuestionType.SQL.value, order)
            if row:
                questions.append(row)
                order += 1

        # Legacy flat "questions" array support
        if len(questions) < TOTAL_GENERATED_QUESTIONS:
            for item in (parsed.get("questions") or []):
                if len(questions) >= TOTAL_GENERATED_QUESTIONS:
                    break
                qtype = str(item.get("question_type") or QuestionType.MCQ.value)
                row = _normalize_ai_question(item, qtype, order)
                if row:
                    questions.append(row)
                    order += 1

        if len(questions) >= TOTAL_GENERATED_QUESTIONS:
            break

    if len(questions) < TOTAL_GENERATED_QUESTIONS:
        fallback = _fallback_questions(jd)
        seen_orders = {q["sort_order"] for q in questions}
        for item in fallback:
            if len(questions) >= TOTAL_GENERATED_QUESTIONS:
                break
            if item["sort_order"] not in seen_orders:
                questions.append(item)

    questions.sort(key=lambda q: int(q.get("sort_order") or 0))
    for index, question in enumerate(questions[:TOTAL_GENERATED_QUESTIONS]):
        question["sort_order"] = index

    return title, questions[:TOTAL_GENERATED_QUESTIONS]


def _build_assessment_response(assessment_id: int, *, reused: bool = False) -> dict[str, Any]:
    assessment = assessment_repo.get_assessment_by_id(assessment_id) or {}
    questions = assessment_repo.get_questions_for_assessment(assessment_id)
    return {
        "reused": reused,
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
) -> dict[str, Any]:
    ctx = _load_context(candidate_id, jd_id)
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

    previous_questions = _previous_question_texts(jd_id)
    generated_title, generated_questions = _generate_questions_with_ai(
        jd,
        candidate,
        previous_questions=previous_questions,
    )
    assessment_id = assessment_repo.create_assessment(
        {
            "candidate_id": candidate_id,
            "jd_id": jd_id,
            "recruiter_id": recruiter_id,
            "status": AssessmentStatus.DRAFT,
            "title": title or generated_title,
            "candidate_name": candidate.get("name") or "",
            "candidate_email": normalize_email(candidate.get("email")),
            "job_role": jd.get("title") or "",
            "passing_score": passing_score,
            "time_limit_minutes": time_limit_minutes,
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

    if not assessment_repo.update_question(question_id, patch):
        raise AssessmentServiceError("No changes were applied to the question.")
    updated = assessment_repo.get_question_by_id(question_id) or {}
    return {"question": recruiter_question_payload(updated)}


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


def _build_invite_email(assessment: dict[str, Any], link: str, from_email: str) -> dict[str, str]:
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
        f"Passing score: {passing_score}%\n\n"
        "Please complete the assessment at your earliest convenience.\n\n"
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
    link = assessment_link(token)
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

    print(f"[email] Candidate test link: {link}", flush=True)
    send_email(to_email, subject, body, from_email, primary_link=link)

    if current_status == AssessmentStatus.DRAFT:
        assert_status_transition(current_status, AssessmentStatus.SENT)

    assessment_repo.update_assessment(
        assessment_id,
        {
            "status": AssessmentStatus.SENT,
            "access_token": token,
            "token_expires_at": expires_at,
            "sent_at": utc_now(),
            "candidate_email": to_email,
        },
    )

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


def _resolve_token_assessment(token: str) -> dict[str, Any]:
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
    if status in AssessmentStatus.submitted_states():
        raise AssessmentServiceError("This assessment has already been submitted.", status_code=409)

    if status in AssessmentStatus.terminal_states():
        raise AssessmentServiceError("This assessment has already been completed.", status_code=409)

    if status not in AssessmentStatus.candidate_accessible_states():
        raise AssessmentServiceError("Assessment is not available yet.", status_code=403)

    remaining = remaining_seconds(assessment)
    if remaining is not None and remaining <= 0:
        raise AssessmentServiceError("Assessment time limit has expired.", status_code=403)

    return assessment


def _begin_candidate_session(assessment: dict[str, Any]) -> dict[str, Any]:
    """Mark assessment in progress when the candidate opens it."""
    assessment_id = int(assessment["id"])
    current_status = str(assessment.get("status") or "")
    if current_status == AssessmentStatus.SENT:
        assert_status_transition(current_status, AssessmentStatus.IN_PROGRESS)
        assessment_repo.update_assessment(
            assessment_id,
            {"status": AssessmentStatus.IN_PROGRESS, "started_at": utc_now()},
        )
        assessment = assessment_repo.get_assessment_by_id(assessment_id) or assessment
    return assessment


def get_assessment_by_token(token: str) -> dict[str, Any]:
    assessment = _resolve_token_assessment(token)
    assessment = _begin_candidate_session(assessment)
    questions = assessment_repo.get_questions_for_assessment(int(assessment["id"]))
    saved_answers = assessment_repo.get_answers_for_assessment(int(assessment["id"]))
    return {
        "assessment": candidate_assessment_payload(assessment, questions=questions),
        "questions": [candidate_question_payload(q) for q in questions],
        "saved_answers": [
            {
                "question_id": row.get("question_id"),
                "answer": row.get("answer") or "",
                "updated_at": row.get("updated_at"),
            }
            for row in saved_answers
        ],
    }


def save_answer(token: str, question_id: int, answer: str) -> dict[str, Any]:
    assessment = _resolve_token_assessment(token)
    assessment_id = int(assessment["id"])
    question = assessment_repo.get_question_by_id(question_id)
    if not question or int(question.get("assessment_id") or 0) != assessment_id:
        raise AssessmentServiceError("Question not found for this assessment.")

    current_status = str(assessment.get("status") or "")
    if current_status == AssessmentStatus.SENT:
        assert_status_transition(current_status, AssessmentStatus.IN_PROGRESS)
        assessment_repo.update_assessment(
            assessment_id,
            {"status": AssessmentStatus.IN_PROGRESS, "started_at": utc_now()},
        )

    answer_id = assessment_repo.upsert_candidate_answer(
        assessment_id,
        question_id,
        answer,
        is_final=False,
    )
    return {
        "success": True,
        "answer_id": answer_id,
        "question_id": question_id,
        "status": AssessmentStatus.IN_PROGRESS,
    }


def submit_assessment(token: str, answers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    assessment = _resolve_token_assessment(token)
    assessment_id = int(assessment["id"])
    questions = assessment_repo.get_questions_for_assessment(assessment_id)
    if not questions:
        raise AssessmentServiceError("Assessment has no questions.")

    answers_by_question: dict[int, str] = {}
    if answers:
        for item in answers:
            answers_by_question[int(item["question_id"])] = str(item.get("answer") or "")
    else:
        for row in assessment_repo.get_answers_for_assessment(assessment_id):
            answers_by_question[int(row.get("question_id") or 0)] = str(row.get("answer") or "")

    for question in questions:
        qid = int(question.get("id") or 0)
        answer_text = answers_by_question.get(qid, "")
        assessment_repo.upsert_candidate_answer(assessment_id, qid, answer_text, is_final=True)

    passing_score = int(assessment.get("passing_score") or DEFAULT_PASSING_SCORE)
    scoring = evaluate_assessment(questions, answers_by_question, passing_score=passing_score)
    passed = bool(scoring["passed"])
    final_status = AssessmentStatus.PASSED if passed else AssessmentStatus.FAILED
    pending_note = ""
    if int(scoring.get("pending_review_count") or 0) > 0:
        pending_note = f" MCQ score: {scoring.get('mcq_percentage')}%. Coding/SQL pending review."
    summary = (
        f"Score: {scoring['score_percentage']}% ({scoring['earned_points']}/{scoring['total_points']} points). "
        f"Passing score: {passing_score}%.{pending_note}"
    )

    current_status = str(assessment.get("status") or AssessmentStatus.IN_PROGRESS)
    if current_status == AssessmentStatus.SENT:
        assessment_repo.update_assessment(
            assessment_id,
            {"status": AssessmentStatus.IN_PROGRESS, "started_at": utc_now()},
        )
        current_status = AssessmentStatus.IN_PROGRESS
    assert_status_transition(current_status, AssessmentStatus.COMPLETED)
    assessment_repo.update_assessment(
        assessment_id,
        {
            "status": AssessmentStatus.COMPLETED,
            "completed_at": utc_now(),
        },
    )
    assert_status_transition(AssessmentStatus.COMPLETED, final_status)
    assessment_repo.update_assessment(assessment_id, {"status": final_status})
    assessment_repo.mark_answers_final(assessment_id)

    result_id = assessment_repo.upsert_assessment_result(
        {
            "assessment_id": assessment_id,
            "candidate_id": int(assessment.get("candidate_id") or 0),
            "jd_id": int(assessment.get("jd_id") or 0),
            "total_points": scoring["total_points"],
            "earned_points": scoring["earned_points"],
            "score": scoring["score"],
            "score_percentage": scoring["score_percentage"],
            "percentage": scoring["percentage"],
            "mcq_percentage": scoring.get("mcq_percentage"),
            "passed": passed,
            "status": final_status,
            "question_results": scoring["question_results"],
            "evaluation_breakdown": scoring.get("evaluation_breakdown"),
            "pending_review_count": scoring.get("pending_review_count"),
            "pass_basis": scoring.get("pass_basis"),
            "summary": summary,
            "scored_at": utc_now(),
        }
    )

    db.update_candidate(
        int(assessment.get("candidate_id") or 0),
        {"hiring_stage": "Assessment Passed" if passed else "Assessment Failed"},
    )

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
    "save_answer",
    "submit_assessment",
    "get_assessment_result",
    "is_eligible_for_interview",
    "is_assessment_passed_for_candidate_jd",
    "enrich_candidates_with_assessments",
    "assessment_pipeline_snapshot",
]
