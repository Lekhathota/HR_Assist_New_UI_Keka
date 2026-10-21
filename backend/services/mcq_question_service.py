"""
Recruiter-requested MCQs for a draft assessment (Preview Assessment → + Add MCQ).

The recruiter describes the question (instructions, topic, difficulty, marks, optional time limit);
the AI writes one MCQ from the assessment's JD. Generation returns a draft only: nothing is stored
until the recruiter has reviewed (and possibly edited) it and saves it. A saved question is an
ordinary MCQ row tagged with `source="custom_mcq"` and the prompt used, so grading, candidate links,
the question editor and Regenerate work unchanged. Nothing here sends email.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any

from pymongo.errors import DuplicateKeyError

import database as db
from assessment import repository as assessment_repo
from assessment.generation import is_duplicate, normalized_jd, requirement_catalog, shuffle_mcq_options
from assessment.models import (
    CODING_DIFFICULTIES,
    MAX_ASSESSMENT_MINUTES,
    MAX_CODING_PROMPT_CHARS,
    MAX_CODING_TIME_LIMIT_MINUTES,
    MAX_CODING_TOPIC_CHARS,
    AssessmentStatus,
    max_assessment_questions,
)
from assessment.utilities import assessment_summary_payload, recruiter_question_payload
from services.assessment_service import AssessmentServiceError, validate_mcq
from services.json_parser import parse_json_response
from services.llm_service import LLMService
from services.prompt_service import PromptService

SOURCE = "custom_mcq"
GENERATION_ATTEMPTS = 3
DEFAULT_POINTS = 5
EDIT_KEYS = ("question_text", "options", "correct_answer", "explanation", "difficulty", "points")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.:-]{8,80}$")


# ---------------------------------------------------------------- shared helpers (also used for coding)

def editable_assessment(assessment_id: int) -> dict[str, Any]:
    assessment = assessment_repo.get_assessment_by_id(assessment_id)
    if not assessment:
        raise AssessmentServiceError("Assessment not found.", status_code=404)
    if assessment.get("status") not in AssessmentStatus.editable_states():
        raise AssessmentServiceError("Questions can only be added while the assessment is a DRAFT.", status_code=409)
    return assessment


def clean_request_id(value: Any) -> str:
    """Optional client token identifying one save; a repeated save with the same token is a no-op."""
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or not _REQUEST_ID.match(value):
        raise AssessmentServiceError("request_id must be 8-80 letters, digits, '-', '_', '.' or ':'.")
    return value


def question_for_request(assessment_id: int, request_id: str) -> dict[str, Any] | None:
    if not request_id:
        return None
    return next((q for q in assessment_repo.get_questions_for_assessment(assessment_id)
                 if q.get("client_request_id") == request_id), None)


def extend_duration(assessment: dict[str, Any], minutes: int | None) -> int:
    """Add a question's time limit to the assessment duration (capped); returns the new duration."""
    current = int(assessment.get("time_limit_minutes") or 0)
    if not minutes:
        return current
    updated = min(MAX_ASSESSMENT_MINUTES, current + int(minutes))
    if updated != current:
        assessment_repo.update_assessment(int(assessment["id"]), {"time_limit_minutes": updated})
    return updated


def assessment_state(assessment_id: int) -> dict[str, Any]:
    """Summary the preview needs after a change: counts, marks and duration come from the stored draft."""
    assessment = assessment_repo.get_assessment_by_id(assessment_id) or {}
    questions = assessment_repo.get_questions_for_assessment(assessment_id)
    return {
        "assessment": assessment_summary_payload(assessment, questions=questions),
        "questions": [recruiter_question_payload(q) for q in questions],
        "counts": {kind: sum(1 for q in questions if q.get("question_type") == kind) for kind in ("mcq", "coding", "sql")},
        "total_marks": sum(int(q.get("points") or 0) for q in questions),
    }


def _time_limit(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        raise AssessmentServiceError(f"Time limit must be a whole number of minutes between 1 and {MAX_CODING_TIME_LIMIT_MINUTES}.") from None
    if isinstance(value, float) and value != minutes or not 1 <= minutes <= MAX_CODING_TIME_LIMIT_MINUTES:
        raise AssessmentServiceError(f"Time limit must be a whole number of minutes between 1 and {MAX_CODING_TIME_LIMIT_MINUTES}.")
    return minutes


def clean_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Recruiter settings for one MCQ request."""
    if not isinstance(data, dict):
        raise AssessmentServiceError("Request body must be a JSON object.")
    prompt, topic = data.get("prompt") or "", data.get("topic") or ""
    if not isinstance(prompt, str) or not isinstance(topic, str):
        raise AssessmentServiceError("The prompt and topic must be text.")
    prompt, topic = prompt.strip(), topic.strip()
    if len(prompt) > MAX_CODING_PROMPT_CHARS:
        raise AssessmentServiceError(f"The prompt is too long (max {MAX_CODING_PROMPT_CHARS} characters).")
    if len(topic) > MAX_CODING_TOPIC_CHARS:
        raise AssessmentServiceError(f"The topic is too long (max {MAX_CODING_TOPIC_CHARS} characters).")
    difficulty = str(data.get("difficulty") or "Medium").strip().title()
    if difficulty not in CODING_DIFFICULTIES:
        raise AssessmentServiceError("Difficulty must be Easy, Medium or Hard.")
    try:
        points = int(data.get("points") if data.get("points") not in (None, "") else DEFAULT_POINTS)
    except (TypeError, ValueError):
        raise AssessmentServiceError("Marks must be a whole number between 1 and 100.") from None
    if not 1 <= points <= 100:
        raise AssessmentServiceError("Marks must be a whole number between 1 and 100.")
    return {"prompt": prompt, "topic": topic, "difficulty": difficulty, "points": points,
            "time_limit_minutes": _time_limit(data.get("time_limit_minutes"))}


# ---------------------------------------------------------------- generation

def validate_generated_mcq(item: Any, *, difficulty: str, points: int, catalog: dict[str, str],
                           previous_questions: list[str] = ()) -> dict[str, Any]:
    """Turn the model's JSON for one MCQ into a question row, or raise ValueError."""
    if not isinstance(item, dict):
        raise ValueError("The response must be one JSON object.")
    text = str(item.get("question") or item.get("question_text") or "").strip()
    if len(text.split()) < 8:
        raise ValueError("question must be a complete question (at least 8 words).")
    if str(item.get("question_type") or "mcq").strip().lower() != "mcq":
        raise ValueError("question_type must be mcq.")
    if str(item.get("difficulty") or "").strip().title() != difficulty:
        raise ValueError(f"difficulty must be {difficulty}, as chosen by the recruiter.")
    options = item.get("options")
    if not isinstance(options, list) or len(options) != 4 or not all(isinstance(o, str) and o.strip() for o in options):
        raise ValueError("options must be exactly four non-empty strings.")
    options = [o.strip() for o in options]
    if len({" ".join(o.lower().split()) for o in options}) != 4:
        raise ValueError("The four options must be different from each other.")
    answer = str(item.get("correct_answer") or "").strip()
    label = re.fullmatch(r"(?:option\s+)?([A-D])[.)]?", answer, re.I)
    if answer not in options and label:
        answer = options[ord(label.group(1).upper()) - ord("A")]
    if options.count(answer) != 1:
        raise ValueError("correct_answer must be the exact text of exactly one option.")
    explanation = str(item.get("explanation") or "").strip()
    if not explanation:
        raise ValueError("explanation must say why the correct answer is right.")
    ref = item.get("jd_requirement_id")
    if ref not in (None, "", "null") and ref not in catalog:
        raise ValueError("jd_requirement_id must be one of the numbered JD requirements, or null.")
    if any(is_duplicate(text, other) for other in previous_questions):
        raise ValueError("The question repeats an existing question in this assessment.")
    focus = item.get("evaluation_focus")
    focus = [v.strip() for v in focus if isinstance(v, str) and v.strip()] if isinstance(focus, list) else []
    row = {
        "question_text": text, "question_type": "mcq", "options": options, "correct_answer": answer,
        "explanation": explanation, "difficulty": difficulty, "points": points,
        "skill_tag": str(item.get("skill") or "").strip() or "General",
        "scenario_type": str(item.get("scenario_type") or "Scenario").strip() or "Scenario",
        "evaluation_focus": focus or ["Practical application"],
        **({"jd_requirement": catalog[ref]} if ref in catalog else {}),
    }
    return shuffle_mcq_options([row])[0]  # models tend to put the answer first


def _other_texts(assessment_id: int, exclude_id: int | None = None) -> list[str]:
    return [q.get("question_text") or "" for q in assessment_repo.get_questions_for_assessment(assessment_id)
            if q.get("id") != exclude_id]


def _generate_with_ai(jd: dict[str, Any], settings: dict[str, Any], previous: list[str]) -> dict[str, Any]:
    context = normalized_jd(jd)
    catalog = requirement_catalog(context)
    try:
        llm = LLMService(model=os.getenv("ASSESSMENT_MODEL") or "gpt-4.1", temperature=0.6)
    except Exception as exc:
        raise AssessmentServiceError("AI question generation is unavailable. Check the configured AI service.", status_code=503) from exc
    prompt_service = PromptService()
    feedback = ""
    for _ in range(GENERATION_ATTEMPTS):
        try:
            prompt = prompt_service.render(
                "mcq_question_generate.jinja", question_prompt=settings["prompt"], jd_data=context,
                requirement_catalog=catalog, difficulty=settings["difficulty"], points=settings["points"],
                topic=settings["topic"], time_limit_minutes=settings["time_limit_minutes"],
                previous_questions=previous[-60:], generation_nonce=uuid.uuid4().hex, validation_feedback=feedback,
            )
            item = parse_json_response(llm.invoke(prompt, temperature=0.6))
            return validate_generated_mcq(item, difficulty=settings["difficulty"], points=settings["points"],
                                          catalog=catalog, previous_questions=previous)
        except (ValueError, TypeError, KeyError) as exc:
            feedback = str(exc)[:2000]
        except Exception as exc:
            raise AssessmentServiceError("AI question generation failed. Please retry; your settings were kept.", status_code=502) from exc
    raise AssessmentServiceError("The AI could not produce a valid MCQ after three attempts. "
                                 f"Adjust the instructions or retry. Last problem: {feedback}", status_code=502)


def _jd_for(assessment: dict[str, Any]) -> dict[str, Any]:
    jd = db.get_jd_by_id(int(assessment.get("jd_id") or 0), include_raw_text=True)
    if not jd:
        raise AssessmentServiceError("The assessment's job description no longer exists.", status_code=409)
    return jd


def generate_mcq_draft(assessment_id: int, data: dict[str, Any]) -> dict[str, Any]:
    """Generate one MCQ for review. Nothing is stored and nothing is sent."""
    assessment = editable_assessment(assessment_id)
    settings = clean_settings(data or {})
    if not settings["prompt"] and not settings["topic"]:
        raise AssessmentServiceError("Enter instructions or a topic for the question.")
    if assessment_repo.count_questions_for_assessment(assessment_id) + 1 > max_assessment_questions():
        raise AssessmentServiceError(f"An assessment can have at most {max_assessment_questions()} questions.", status_code=409)
    row = _generate_with_ai(_jd_for(assessment), settings, _other_texts(assessment_id))
    if settings["topic"]:
        row["skill_tag"] = settings["topic"]
    return {"draft": {**row, "generation_prompt": settings["prompt"], "time_limit_minutes": settings["time_limit_minutes"]},
            "settings": settings}


def regenerate_custom_mcq(assessment: dict[str, Any], question: dict[str, Any], others: list[str]) -> dict[str, Any]:
    """New version of a saved recruiter-requested MCQ, from its own prompt, topic, difficulty and marks."""
    settings = clean_settings({"prompt": question.get("generation_prompt") or "", "topic": question.get("skill_tag") or "",
                               "difficulty": question.get("difficulty") or "Medium", "points": question.get("points"),
                               "time_limit_minutes": question.get("time_limit_minutes")})
    row = _generate_with_ai(_jd_for(assessment), settings, others)
    if settings["topic"]:
        row["skill_tag"] = settings["topic"]
    return row


# ---------------------------------------------------------------- save

def save_mcq_question(assessment_id: int, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the reviewed MCQ and add it after the existing MCQs.

    Existing questions are never replaced. Questions after the MCQ block (coding, SQL) move down one
    place so candidates still see all MCQs first. Saving the same request_id twice stores one question.
    """
    assessment = editable_assessment(assessment_id)
    if not isinstance(data, dict) or not isinstance(data.get("question"), dict):
        raise AssessmentServiceError("Send the reviewed question to save.")
    request_id = clean_request_id(data.get("request_id"))
    existing = question_for_request(assessment_id, request_id)
    if existing:
        return {"question": recruiter_question_payload(existing), "replayed": True, **assessment_state(assessment_id)}
    settings = clean_settings({key: data.get(key) for key in ("prompt", "topic", "time_limit_minutes")}
                              | {key: data["question"].get(key) for key in ("difficulty", "points")})
    edits = {key: data["question"][key] for key in EDIT_KEYS if key in data["question"]}
    for key in ("question_text", "correct_answer", "explanation"):
        if not isinstance(edits.get(key, ""), str):
            raise AssessmentServiceError(f"{key.replace('_', ' ').capitalize()} must be text.")
    row = {
        "question_type": "mcq",
        "question_text": str(edits.get("question_text") or "").strip(),
        "options": [o.strip() if isinstance(o, str) else o for o in (edits.get("options") or [])],
        "correct_answer": str(edits.get("correct_answer") or "").strip(),
        "explanation": str(edits.get("explanation") or "").strip(),
        "difficulty": settings["difficulty"], "points": settings["points"],
    }
    validate_mcq(row)
    if any(is_duplicate(row["question_text"], other) for other in _other_texts(assessment_id)):
        raise AssessmentServiceError("This question repeats another question in the assessment. Edit it or regenerate.")
    if assessment_repo.count_questions_for_assessment(assessment_id) + 1 > max_assessment_questions():
        raise AssessmentServiceError(f"An assessment can have at most {max_assessment_questions()} questions.", status_code=409)
    draft = data.get("draft_meta") if isinstance(data.get("draft_meta"), dict) else {}
    row.update(
        skill_tag=settings["topic"] or str(draft.get("skill_tag") or "").strip()[:MAX_CODING_TOPIC_CHARS] or "General",
        scenario_type=str(draft.get("scenario_type") or "Scenario")[:80],
        evaluation_focus=[str(v)[:200] for v in draft.get("evaluation_focus") or [] if str(v).strip()][:10] or ["Practical application"],
        source=SOURCE, generation_prompt=settings["prompt"], time_limit_minutes=settings["time_limit_minutes"],
        **({"client_request_id": request_id} if request_id else {}),
    )
    if isinstance(draft.get("jd_requirement"), str) and draft["jd_requirement"].strip():
        row["jd_requirement"] = draft["jd_requirement"].strip()[:1000]

    questions = assessment_repo.get_questions_for_assessment(assessment_id)
    mcqs = [q for q in questions if q.get("question_type") == "mcq"]
    position = max((int(q.get("sort_order") or 0) for q in mcqs), default=-1) + 1
    for q in questions:  # keep the MCQ block first: shift later questions down by one
        if q.get("question_type") != "mcq" and int(q.get("sort_order") or 0) >= position:
            assessment_repo.update_question(int(q["id"]), {"sort_order": int(q.get("sort_order") or 0) + 1})
    row["sort_order"] = position
    row["question_id"] = _next_label(questions)
    try:
        question_id = assessment_repo.create_question({"assessment_id": assessment_id, **row})
    except DuplicateKeyError:
        # A concurrent save of the same request won the race; return its question.
        existing = question_for_request(assessment_id, request_id)
        if not existing:
            raise
        return {"question": recruiter_question_payload(existing), "replayed": True, **assessment_state(assessment_id)}
    if data.get("extend_duration") is True:
        extend_duration(assessment, settings["time_limit_minutes"])
    db.log_audit("Assessment Question Added", "", f"Added AI-generated MCQ #{question_id} to assessment #{assessment_id}.",
                 int(assessment.get("jd_id") or 0) or None)
    question = assessment_repo.get_question_by_id(question_id) or {}
    return {"question": recruiter_question_payload(question), "replayed": False, **assessment_state(assessment_id)}


def _next_label(questions: list[dict[str, Any]]) -> str:
    """Display label (Q031…) that no other question in the assessment uses."""
    taken = {str(q.get("question_id") or "") for q in questions}
    number = len(questions) + 1
    while f"Q{number:03d}" in taken:
        number += 1
    return f"Q{number:03d}"
