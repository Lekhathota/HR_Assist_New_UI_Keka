"""
Recruiter-defined coding questions for a draft assessment (Assessment Builder → Coding Questions).

The base "Generate from JD" exam keeps its fixed format. On top of it a recruiter can add any
number of coding entries ("specs", up to ASSESSMENT_MAX_CODING_QUESTIONS), each with its own
prompt, language, difficulty and points, and generate one question per entry from:
    the selected JD + the client-level coding prompt + the entry's own prompt.

Specs live on the assessment document (`coding_specs`); a generated question is an ordinary
question row tagged with `source="custom_coding"`, `coding_spec_id` and the prompts used, so
grading, candidate links and the existing question editor work unchanged.
"""

from __future__ import annotations

import os
import uuid
from difflib import SequenceMatcher
from typing import Any

import database as db
from assessment import repository as assessment_repo
from assessment.code_execution.languages import LANGUAGES, normalize_language
from assessment.code_execution.preparation import prepare_executable_questions, validate_test_fields
from assessment.generation import normalized_jd, requirement_catalog
from assessment.models import (
    CODING_DIFFICULTIES,
    MAX_CLIENT_CODING_PROMPT_CHARS,
    MAX_CODING_PROMPT_CHARS,
    AssessmentStatus,
    max_assessment_questions,
    max_coding_questions,
)
from assessment.utilities import recruiter_question_payload, utc_now
from services.assessment_service import AssessmentServiceError
from services.json_parser import parse_json_response
from services.llm_service import LLMService
from services.prompt_service import PromptService

SOURCE = "custom_coding"
GENERATION_ATTEMPTS = 3
DEFAULT_POINTS = 15


def _now() -> str:
    return utc_now().isoformat()


def _text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


# ---------------------------------------------------------------- validation

def _clean_spec_fields(data: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    """Validate recruiter input for one coding entry. Empty prompts are allowed while drafting."""
    if not isinstance(data, dict):
        raise AssessmentServiceError("Request body must be a JSON object.")
    out: dict[str, Any] = {}
    if "prompt" in data or not partial:
        prompt = data.get("prompt", "")
        if not isinstance(prompt, str):
            raise AssessmentServiceError("The question prompt must be text.")
        prompt = prompt.strip()
        if len(prompt) > MAX_CODING_PROMPT_CHARS:
            raise AssessmentServiceError(f"The question prompt is too long (max {MAX_CODING_PROMPT_CHARS} characters).")
        out["prompt"] = prompt
    if "language" in data or not partial:
        raw = str(data.get("language") or "").strip().lower()
        if raw in {"", "any"}:
            out["language"] = ""
        else:
            language = normalize_language(raw)
            if not language:
                supported = ", ".join(spec["label"] for spec in LANGUAGES.values())
                raise AssessmentServiceError(f"Unsupported language '{data.get('language')}'. Supported: {supported}.")
            out["language"] = language
    if "difficulty" in data or not partial:
        difficulty = str(data.get("difficulty") or "Medium").strip().title()
        if difficulty not in CODING_DIFFICULTIES:
            raise AssessmentServiceError("Difficulty must be Easy, Medium or Hard.")
        out["difficulty"] = difficulty
    if "points" in data or not partial:
        try:
            points = int(data.get("points") if data.get("points") not in (None, "") else DEFAULT_POINTS)
        except (TypeError, ValueError):
            raise AssessmentServiceError("Points must be a whole number between 1 and 100.") from None
        if not 1 <= points <= 100:
            raise AssessmentServiceError("Points must be a whole number between 1 and 100.")
        out["points"] = points
    return out


def validate_generated_coding_question(
    item: Any,
    *,
    difficulty: str,
    language: str,
    points: int,
    catalog: dict[str, str],
    previous_questions: list[str] = (),
    require_tests: bool = True,
) -> dict[str, Any]:
    """Turn the model's JSON for one coding question into a question row, or raise ValueError."""
    if not isinstance(item, dict):
        raise ValueError("The response must be one JSON object.")
    text = str(item.get("question") or item.get("question_text") or "").strip()
    if len(text.split()) < 12:
        raise ValueError("question must be a complete problem statement (scenario, behaviour, constraints and samples).")
    if str(item.get("question_type") or "coding").strip().lower() != "coding":
        raise ValueError("question_type must be coding.")
    if str(item.get("difficulty") or "").strip().title() != difficulty:
        raise ValueError(f"difficulty must be {difficulty}, as chosen by the recruiter.")
    answer = str(item.get("correct_answer") or "").strip()
    if not answer:
        raise ValueError("correct_answer must be a complete Python 3 reference program.")
    explanation = str(item.get("explanation") or "").strip()
    if not explanation:
        raise ValueError("explanation must describe the expected solution approach.")
    focus = item.get("evaluation_focus")
    if not isinstance(focus, list) or not focus or not all(isinstance(v, str) and v.strip() for v in focus):
        raise ValueError("evaluation_focus must be a nonempty list of strings.")
    ref = item.get("jd_requirement_id")
    if ref not in (None, "", "null") and ref not in catalog:
        raise ValueError("jd_requirement_id must be one of the numbered JD requirements, or null.")
    canonical = _text(text)
    for other in previous_questions:
        other = _text(other)
        if other and (canonical == other or SequenceMatcher(None, canonical, other).ratio() >= .88):
            raise ValueError("The question repeats an existing question in this assessment.")

    executable: dict[str, Any] = {}
    try:
        executable = validate_test_fields(item, "coding", "Question")
    except ValueError:
        if require_tests:
            raise
    if language and executable:
        executable["allowed_languages"] = [language]
        executable["default_language"] = language
    return {
        "question_text": text,
        "question_type": "coding",
        "options": [],
        "correct_answer": answer,
        "starter_code": "",
        "points": points,
        "skill_tag": str(item.get("skill") or "").strip() or "Coding",
        "difficulty": difficulty,
        "scenario_type": str(item.get("scenario_type") or "Implementation").strip() or "Implementation",
        "explanation": explanation,
        "evaluation_focus": [v.strip() for v in focus],
        **({"jd_requirement": catalog[ref]} if ref in catalog else {}),
        **executable,
    }


# ---------------------------------------------------------------- loading helpers

def _editable(assessment_id: int) -> dict[str, Any]:
    assessment = assessment_repo.get_assessment_by_id(assessment_id)
    if not assessment:
        raise AssessmentServiceError("Assessment not found.", status_code=404)
    if assessment.get("status") not in AssessmentStatus.editable_states():
        raise AssessmentServiceError("Coding questions can only be changed while the assessment is a DRAFT.", status_code=409)
    return assessment


def _client_for(assessment: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    jd = db.get_jd_by_id(int(assessment.get("jd_id") or 0), include_raw_text=True) or {}
    client = db.get_client_by_id(int(jd["client_id"])) if jd.get("client_id") else None
    return jd, client or {}


def _client_prompt(assessment: dict[str, Any], client: dict[str, Any]) -> str:
    # An assessment-level prompt (even an empty one) overrides the client's default.
    if assessment.get("client_coding_prompt") is not None:
        return str(assessment["client_coding_prompt"])
    return str(client.get("coding_assessment_prompt") or "")


def _find_spec(specs: list[dict], spec_id: str) -> dict[str, Any]:
    for spec in specs:
        if spec.get("id") == spec_id:
            return spec
    raise AssessmentServiceError("Coding question entry not found.", status_code=404)


def _linked_questions(assessment_id: int) -> dict[str, dict]:
    return {
        str(q.get("coding_spec_id")): q
        for q in assessment_repo.get_questions_for_assessment(assessment_id)
        if q.get("source") == SOURCE and q.get("coding_spec_id")
    }


def _spec_view(spec: dict[str, Any], question: dict[str, Any] | None) -> dict[str, Any]:
    status = spec.get("status") or "pending"
    if status == "generated" and not question:
        status = "pending"  # the generated question was deleted from the question list
    return {
        "id": spec["id"],
        "prompt": spec.get("prompt") or "",
        "language": spec.get("language") or "",
        "difficulty": spec.get("difficulty") or "Medium",
        "points": int(spec.get("points") or DEFAULT_POINTS),
        "status": status,
        "last_error": spec.get("last_error") or "",
        "generated_at": spec.get("generated_at"),
        "created_at": spec.get("created_at"),
        "question": recruiter_question_payload(question) if question else None,
    }


def get_coding_config(assessment_id: int) -> dict[str, Any]:
    assessment = assessment_repo.get_assessment_by_id(assessment_id)
    if not assessment:
        raise AssessmentServiceError("Assessment not found.", status_code=404)
    jd, client = _client_for(assessment)
    linked = _linked_questions(assessment_id)
    questions = assessment_repo.get_questions_for_assessment(assessment_id)
    return {
        "editable": assessment.get("status") in AssessmentStatus.editable_states(),
        "jd": {"id": jd.get("id"), "title": jd.get("title") or ""},
        "client": {"id": client.get("id"), "name": client.get("name") or ""} if client else None,
        "client_prompt": _client_prompt(assessment, client),
        "client_default_prompt": str(client.get("coding_assessment_prompt") or ""),
        "specs": [_spec_view(spec, linked.get(spec.get("id"))) for spec in assessment.get("coding_specs") or []],
        "coding_question_count": sum(1 for q in questions if q.get("question_type") == "coding"),
        "question_count": len(questions),
        "limits": {
            "max_coding_questions": max_coding_questions(),
            "max_questions": max_assessment_questions(),
            "max_prompt_chars": MAX_CODING_PROMPT_CHARS,
            "max_client_prompt_chars": MAX_CLIENT_CODING_PROMPT_CHARS,
        },
        "languages": [{"key": key, "label": spec["label"]} for key, spec in LANGUAGES.items()],
        "difficulties": list(CODING_DIFFICULTIES),
    }


# ---------------------------------------------------------------- mutations

def save_client_prompt(assessment_id: int, prompt: Any, *, save_as_client_default: bool = False) -> dict[str, Any]:
    assessment = _editable(assessment_id)
    if not isinstance(prompt, str):
        raise AssessmentServiceError("The client coding prompt must be text.")
    prompt = prompt.strip()
    if len(prompt) > MAX_CLIENT_CODING_PROMPT_CHARS:
        raise AssessmentServiceError(f"The client coding prompt is too long (max {MAX_CLIENT_CODING_PROMPT_CHARS} characters).")
    assessment_repo.update_assessment(assessment_id, {"client_coding_prompt": prompt})
    if save_as_client_default:
        _, client = _client_for(assessment)
        if not client:
            raise AssessmentServiceError("This job has no client, so there is no client default to save.", status_code=409)
        db.update_client(int(client["id"]), {"coding_assessment_prompt": prompt})
    return get_coding_config(assessment_id)


def add_spec(assessment_id: int, data: dict[str, Any]) -> dict[str, Any]:
    assessment = _editable(assessment_id)
    specs = list(assessment.get("coding_specs") or [])
    if len(specs) >= max_coding_questions():
        raise AssessmentServiceError(f"An assessment can have at most {max_coding_questions()} custom coding questions.", status_code=409)
    linked = _linked_questions(assessment_id)
    pending = sum(1 for spec in specs if spec.get("id") not in linked)
    if assessment_repo.count_questions_for_assessment(assessment_id) + pending + 1 > max_assessment_questions():
        raise AssessmentServiceError(f"An assessment can have at most {max_assessment_questions()} questions.", status_code=409)
    fields = _clean_spec_fields(data or {}, partial=False)
    now = _now()
    spec = {"id": uuid.uuid4().hex[:12], **fields, "question_id": None, "status": "pending", "last_error": "",
            "generated_at": None, "created_at": now, "updated_at": now}
    specs.append(spec)
    assessment_repo.update_assessment(assessment_id, {"coding_specs": specs})
    return {"spec": _spec_view(spec, None), "config": get_coding_config(assessment_id)}


def update_spec(assessment_id: int, spec_id: str, data: dict[str, Any]) -> dict[str, Any]:
    assessment = _editable(assessment_id)
    specs = list(assessment.get("coding_specs") or [])
    spec = _find_spec(specs, spec_id)
    spec.update(_clean_spec_fields(data or {}, partial=True), updated_at=_now())
    assessment_repo.update_assessment(assessment_id, {"coding_specs": specs})
    return {"spec": _spec_view(spec, _linked_questions(assessment_id).get(spec_id)), "config": get_coding_config(assessment_id)}


def remove_spec(assessment_id: int, spec_id: str) -> dict[str, Any]:
    """Remove a coding entry together with the question generated from it."""
    assessment = _editable(assessment_id)
    specs = list(assessment.get("coding_specs") or [])
    _find_spec(specs, spec_id)
    question = _linked_questions(assessment_id).get(spec_id)
    if question:
        assessment_repo.delete_question(int(question["id"]))
    assessment_repo.update_assessment(assessment_id, {"coding_specs": [s for s in specs if s.get("id") != spec_id]})
    return get_coding_config(assessment_id)


def generate_spec_question(assessment_id: int, spec_id: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate (or regenerate) the coding question for one entry; replaces only that entry's question."""
    assessment = _editable(assessment_id)
    specs = list(assessment.get("coding_specs") or [])
    spec = _find_spec(specs, spec_id)
    if overrides:
        spec.update(_clean_spec_fields(overrides, partial=True), updated_at=_now())
    if not spec.get("prompt"):
        raise AssessmentServiceError("Enter the client's requirements for this question before generating it.")
    linked = _linked_questions(assessment_id)
    existing = linked.get(spec_id)
    if not existing and assessment_repo.count_questions_for_assessment(assessment_id) + 1 > max_assessment_questions():
        raise AssessmentServiceError(f"An assessment can have at most {max_assessment_questions()} questions.", status_code=409)

    jd, client = _client_for(assessment)
    if not jd:
        raise AssessmentServiceError("The assessment's job description no longer exists.", status_code=409)
    client_prompt = _client_prompt(assessment, client)
    previous = [q.get("question_text") or "" for q in assessment_repo.get_questions_for_assessment(assessment_id)
                if not existing or q.get("id") != existing.get("id")]
    try:
        row = _generate_with_ai(jd, client_prompt, spec, previous)
    except AssessmentServiceError as exc:
        spec.update(status="failed", last_error=str(exc), updated_at=_now())
        assessment_repo.update_assessment(assessment_id, {"coding_specs": specs})
        raise

    row.update(source=SOURCE, coding_spec_id=spec_id, generation_prompt=spec["prompt"], client_prompt_snapshot=client_prompt)
    if existing:
        # Regenerate in place: same question id and position; clear stale executable fields.
        stale = {key: None for key in ("test_cases", "input_format", "output_format", "allowed_languages",
                                        "default_language", "tests_verified", "reference_language",
                                        "verification", "config_fingerprint", "jd_requirement")}
        assessment_repo.update_question(int(existing["id"]), {**stale, **row})
        question_id = int(existing["id"])
    else:
        row["sort_order"] = assessment_repo.count_questions_for_assessment(assessment_id)
        question_id = assessment_repo.create_question({"assessment_id": assessment_id, **row})
    spec.update(status="generated", question_id=question_id, last_error="", generated_at=_now(), updated_at=_now())
    assessment_repo.update_assessment(assessment_id, {"coding_specs": specs})
    db.log_audit("Coding Question Generated", "",
                 f"Generated coding question #{question_id} for assessment #{assessment_id} from a recruiter prompt.",
                 int(assessment.get("jd_id") or 0) or None)
    question = assessment_repo.get_question_by_id(question_id) or {}
    return {"spec": _spec_view(spec, question), "question": recruiter_question_payload(question),
            "config": get_coding_config(assessment_id)}


def _generate_with_ai(jd: dict[str, Any], client_prompt: str, spec: dict[str, Any], previous: list[str]) -> dict[str, Any]:
    context = normalized_jd(jd)
    catalog = requirement_catalog(context)
    language = spec.get("language") or ""
    prompt_service = PromptService()
    try:
        llm = LLMService(model=os.getenv("ASSESSMENT_MODEL") or "gpt-4.1", temperature=0.6)
    except Exception as exc:
        raise AssessmentServiceError("AI question generation is unavailable. Check the configured AI service.", status_code=503) from exc
    feedback = ""
    for attempt in range(GENERATION_ATTEMPTS):
        strict = attempt < GENERATION_ATTEMPTS - 1  # the last attempt keeps a question whose tests cannot be verified
        try:
            prompt = prompt_service.render(
                "coding_question_generate.jinja",
                question_prompt=spec["prompt"], client_prompt=client_prompt, jd_data=context,
                requirement_catalog=catalog, difficulty=spec.get("difficulty") or "Medium",
                language=language, language_label=LANGUAGES[language]["label"] if language else "",
                points=int(spec.get("points") or DEFAULT_POINTS), previous_questions=previous[-40:],
                generation_nonce=uuid.uuid4().hex, validation_feedback=feedback,
            )
            item = parse_json_response(llm.invoke(prompt, temperature=0.6))
            row = validate_generated_coding_question(
                item, difficulty=spec.get("difficulty") or "Medium", language=language,
                points=int(spec.get("points") or DEFAULT_POINTS), catalog=catalog,
                previous_questions=previous, require_tests=strict,
            )
            return prepare_executable_questions([row], strict=strict)[0]
        except (ValueError, TypeError, KeyError) as exc:
            feedback = str(exc)[:2000]
        except Exception as exc:
            raise AssessmentServiceError("AI question generation failed. Please retry; your prompt was kept.", status_code=502) from exc
    raise AssessmentServiceError("The AI could not produce a valid coding question after three attempts. "
                                 f"Adjust the prompt or retry. Last problem: {feedback}", status_code=502)


# ---------------------------------------------------------------- regenerate-from-JD support

def carry_over_custom_coding(old_assessment: dict[str, Any], new_assessment_id: int) -> None:
    """Copy coding entries, the client prompt and their generated questions to a regenerated draft."""
    old_id = int(old_assessment["id"])
    specs = [dict(spec) for spec in old_assessment.get("coding_specs") or []]
    linked = _linked_questions(old_id)
    order = assessment_repo.count_questions_for_assessment(new_assessment_id)
    for spec in specs:
        question = linked.get(spec.get("id"))
        if question:
            copy = {key: value for key, value in question.items() if key not in {"id", "_id", "assessment_id", "created_at", "updated_at"}}
            spec["question_id"] = assessment_repo.create_question({**copy, "assessment_id": new_assessment_id, "sort_order": order})
            order += 1
        else:
            spec["question_id"] = None
            if spec.get("status") == "generated":
                spec["status"] = "pending"
    patch: dict[str, Any] = {"coding_specs": specs}
    if old_assessment.get("client_coding_prompt") is not None:
        patch["client_coding_prompt"] = old_assessment["client_coding_prompt"]
    if specs or "client_coding_prompt" in patch:
        assessment_repo.update_assessment(new_assessment_id, patch)
