"""
Recruiter-defined coding questions for a draft assessment (Assessment Builder → Coding Questions).

The base "Generate from JD" exam keeps its fixed format. On top of it a recruiter can add any
number of coding entries ("specs", up to ASSESSMENT_MAX_CODING_QUESTIONS), each with its own
prompt, language, difficulty, topic, time limit and points, and generate one question per entry from:
    the selected JD + the client-level coding prompt + the entry's own prompt.

Generation produces a draft (`draft_question` on the spec) that the recruiter reviews and edits;
saving validates it and only then writes it to the assessment. Specs live on the assessment
document (`coding_specs`); a saved question is an ordinary question row tagged with
`source="custom_coding"`, `coding_spec_id` and the prompts used, so grading, candidate links and
the existing question editor work unchanged.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import database as db
from assessment import repository as assessment_repo
from assessment.code_execution.languages import LANGUAGES, normalize_language
from assessment.code_execution.preparation import MIN_HIDDEN, MIN_VISIBLE, prepare_executable_questions, validate_test_fields
from assessment.generation import is_duplicate, normalized_jd, requirement_catalog
from assessment.models import (
    CODING_DIFFICULTIES,
    MAX_CLIENT_CODING_PROMPT_CHARS,
    MAX_CODING_PROMPT_CHARS,
    MAX_CODING_TIME_LIMIT_MINUTES,
    MAX_CODING_TOPIC_CHARS,
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
SPEC_KEYS = ("prompt", "language", "difficulty", "points", "topic", "time_limit_minutes")
# Generated-question fields the recruiter can change while reviewing a draft.
DRAFT_EDIT_KEYS = ("question_text", "input_format", "output_format", "constraints", "explanation", "correct_answer", "test_cases")
DRAFT_VIEW_KEYS = (*DRAFT_EDIT_KEYS, "skill_tag", "difficulty", "points", "time_limit_minutes", "evaluation_focus",
                   "jd_requirement", "allowed_languages", "default_language", "tests_verified", "generation_prompt")
# Question fields cleared when a saved question is replaced, so stale tests never survive.
EXECUTABLE_RESET = ("test_cases", "input_format", "output_format", "allowed_languages", "default_language",
                    "tests_verified", "reference_language", "verification", "config_fingerprint", "jd_requirement",
                    "constraints", "time_limit_minutes")


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
    if "topic" in data or not partial:
        topic = data.get("topic") or ""
        if not isinstance(topic, str):
            raise AssessmentServiceError("The topic must be text.")
        if len(topic.strip()) > MAX_CODING_TOPIC_CHARS:
            raise AssessmentServiceError(f"The topic is too long (max {MAX_CODING_TOPIC_CHARS} characters).")
        out["topic"] = topic.strip()
    if "time_limit_minutes" in data or not partial:
        out["time_limit_minutes"] = _time_limit(data.get("time_limit_minutes"))
    return out


def _time_limit(value: Any) -> int | None:
    """Optional suggested solving time in whole minutes; empty means no limit."""
    if value in (None, ""):
        return None
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        raise AssessmentServiceError(f"Time limit must be a whole number of minutes between 1 and {MAX_CODING_TIME_LIMIT_MINUTES}.") from None
    if isinstance(value, float) and value != minutes or not 1 <= minutes <= MAX_CODING_TIME_LIMIT_MINUTES:
        raise AssessmentServiceError(f"Time limit must be a whole number of minutes between 1 and {MAX_CODING_TIME_LIMIT_MINUTES}.")
    return minutes


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
    if any(is_duplicate(text, other) for other in previous_questions):
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
        "constraints": str(item.get("constraints") or "").strip(),
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


def _draft_view(draft: dict[str, Any] | None) -> dict[str, Any] | None:
    if not draft:
        return None
    return {key: draft.get(key) for key in DRAFT_VIEW_KEYS if draft.get(key) is not None}


def _spec_view(spec: dict[str, Any], question: dict[str, Any] | None) -> dict[str, Any]:
    status = spec.get("status") or "pending"
    if status == "generated" and not question:
        status = "pending"  # the generated question was deleted from the question list
    if spec.get("draft_question"):
        status = "review"  # generated, waiting for the recruiter to review and save it
    return {
        "id": spec["id"],
        "prompt": spec.get("prompt") or "",
        "language": spec.get("language") or "",
        "difficulty": spec.get("difficulty") or "Medium",
        "points": int(spec.get("points") or DEFAULT_POINTS),
        "topic": spec.get("topic") or "",
        "time_limit_minutes": spec.get("time_limit_minutes"),
        "draft": _draft_view(spec.get("draft_question")),
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
        "status": assessment.get("status"),
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
            "max_topic_chars": MAX_CODING_TOPIC_CHARS,
            "max_time_limit_minutes": MAX_CODING_TIME_LIMIT_MINUTES,
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
    """Generate (or regenerate) a draft question for one entry for the recruiter to review.

    Nothing is added to the assessment until save_spec_question(); an entry's saved question stays
    unchanged until its new draft is saved.
    """
    assessment = _editable(assessment_id)
    specs = list(assessment.get("coding_specs") or [])
    spec = _find_spec(specs, spec_id)
    if overrides:
        spec.update(_clean_spec_fields(overrides, partial=True), updated_at=_now())
    if not spec.get("prompt"):
        raise AssessmentServiceError("Enter the client's requirements for this question before generating it.")
    existing = _linked_questions(assessment_id).get(spec_id)
    _check_room(assessment_id, existing)

    jd, client = _client_for(assessment)
    if not jd:
        raise AssessmentServiceError("The assessment's job description no longer exists.", status_code=409)
    client_prompt = _client_prompt(assessment, client)
    try:
        row = _generate_with_ai(jd, client_prompt, spec, _other_question_texts(assessment_id, existing))
    except AssessmentServiceError as exc:
        spec.update(status="failed", last_error=str(exc), updated_at=_now())
        assessment_repo.update_assessment(assessment_id, {"coding_specs": specs})
        raise

    row.update(generation_prompt=spec["prompt"], client_prompt_snapshot=client_prompt,
               time_limit_minutes=spec.get("time_limit_minutes"))
    if spec.get("topic"):
        row["skill_tag"] = spec["topic"]
    spec.update(draft_question=row, status="generated" if existing else "pending", last_error="", updated_at=_now())
    assessment_repo.update_assessment(assessment_id, {"coding_specs": specs})
    return {"spec": _spec_view(spec, existing), "draft": _draft_view(row), "config": get_coding_config(assessment_id)}


def save_spec_question(assessment_id: int, spec_id: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate the reviewed (and possibly edited) draft and add it to the assessment.

    A first save appends the question after all existing ones; saving a regenerated draft replaces
    the entry's own question in place (same id and position). Other questions are never touched.
    """
    assessment = _editable(assessment_id)
    specs = list(assessment.get("coding_specs") or [])
    spec = _find_spec(specs, spec_id)
    draft = spec.get("draft_question")
    if not draft:
        raise AssessmentServiceError("Generate the question and review it before saving.", status_code=409)
    data = data or {}
    if not isinstance(data, dict) or not isinstance(data.get("question") or {}, dict):
        raise AssessmentServiceError("Request body must be a JSON object.")
    spec_fields = _clean_spec_fields({key: data[key] for key in SPEC_KEYS if key in data}, partial=True)
    edits = {key: value for key, value in (data.get("question") or {}).items() if key in DRAFT_EDIT_KEYS}
    existing = _linked_questions(assessment_id).get(spec_id)
    _check_room(assessment_id, existing)
    spec.update(spec_fields)
    row = _validated_draft({**draft, **edits}, spec, edits, _other_question_texts(assessment_id, existing))

    row.update(source=SOURCE, coding_spec_id=spec_id)
    if existing:
        assessment_repo.update_question(int(existing["id"]), {**{key: None for key in EXECUTABLE_RESET}, **row})
        question_id = int(existing["id"])
    else:
        others = assessment_repo.get_questions_for_assessment(assessment_id)
        row["sort_order"] = max((int(q.get("sort_order") or 0) for q in others), default=-1) + 1
        question_id = assessment_repo.create_question({"assessment_id": assessment_id, **row})
    spec.pop("draft_question", None)
    spec.update(status="generated", question_id=question_id, last_error="", generated_at=_now(), updated_at=_now())
    assessment_repo.update_assessment(assessment_id, {"coding_specs": specs})
    db.log_audit("Coding Question Saved", "",
                 f"Saved coding question #{question_id} for assessment #{assessment_id} from a recruiter prompt.",
                 int(assessment.get("jd_id") or 0) or None)
    question = assessment_repo.get_question_by_id(question_id) or {}
    return {"spec": _spec_view(spec, question), "question": recruiter_question_payload(question),
            "config": get_coding_config(assessment_id)}


def discard_draft(assessment_id: int, spec_id: str) -> dict[str, Any]:
    """Drop an unsaved generated draft; a saved question of the entry is kept."""
    assessment = _editable(assessment_id)
    specs = list(assessment.get("coding_specs") or [])
    spec = _find_spec(specs, spec_id)
    spec.pop("draft_question", None)
    spec["updated_at"] = _now()
    assessment_repo.update_assessment(assessment_id, {"coding_specs": specs})
    return get_coding_config(assessment_id)


def _check_room(assessment_id: int, existing: dict[str, Any] | None) -> None:
    if not existing and assessment_repo.count_questions_for_assessment(assessment_id) + 1 > max_assessment_questions():
        raise AssessmentServiceError(f"An assessment can have at most {max_assessment_questions()} questions.", status_code=409)


def _other_question_texts(assessment_id: int, existing: dict[str, Any] | None) -> list[str]:
    return [q.get("question_text") or "" for q in assessment_repo.get_questions_for_assessment(assessment_id)
            if not existing or q.get("id") != existing.get("id")]


_TEXT_KEYS = ("question_text", "input_format", "output_format", "constraints", "explanation", "correct_answer")


def _validated_draft(row: dict[str, Any], spec: dict[str, Any], edits: dict[str, Any], others: list[str]) -> dict[str, Any]:
    """Check a reviewed draft before it is written to the assessment; raises AssessmentServiceError."""
    for key in _TEXT_KEYS:
        if row.get(key) is not None and not isinstance(row[key], str):
            raise AssessmentServiceError(f"{key.replace('_', ' ').capitalize()} must be text.")
    row = {**row, **{key: row[key].strip() for key in _TEXT_KEYS[:-1] if isinstance(row.get(key), str)}}
    if len((row.get("question_text") or "").split()) < 12:
        raise AssessmentServiceError("The problem statement must describe the task, behaviour, constraints and samples (at least 12 words).")
    if not (row.get("correct_answer") or "").strip():
        raise AssessmentServiceError("Add a reference solution (a complete Python 3 program).")
    if not row.get("explanation"):
        raise AssessmentServiceError("Add an explanation of the expected solution approach.")
    if any(is_duplicate(row["question_text"], other) for other in others):
        raise AssessmentServiceError("This question repeats another question in the assessment. Edit it or regenerate.")

    row.update(points=int(spec.get("points") or DEFAULT_POINTS), difficulty=spec.get("difficulty") or "Medium",
               time_limit_minutes=spec.get("time_limit_minutes"))
    if spec.get("topic"):
        row["skill_tag"] = spec["topic"]
    if not row.get("test_cases"):
        row["test_cases"] = None  # no automatic tests: graded by AI against the reference solution
        return row
    if "test_cases" in edits:
        _check_recruiter_tests(row["test_cases"])
    try:
        row.update(validate_test_fields(row, "coding", "Question"))
    except ValueError as exc:
        raise AssessmentServiceError(str(exc).replace("Question: ", "")) from exc
    if spec.get("language"):
        row.update(allowed_languages=[spec["language"]], default_language=spec["language"])
    if {"test_cases", "correct_answer"} & set(edits) or "tests_verified" not in row:
        try:
            row = prepare_executable_questions([row], strict=True)[0]
        except ValueError as exc:
            raise AssessmentServiceError(f"The reference solution does not pass the test cases: {str(exc).replace('Q1: ', '')}") from exc
    return row


def _check_recruiter_tests(cases: Any) -> None:
    """Recruiter-edited tests are checked strictly instead of being silently repaired."""
    if not isinstance(cases, list):
        raise AssessmentServiceError("Test cases must be a list.")
    for number, case in enumerate(cases, start=1):
        if not isinstance(case, dict) or not isinstance(case.get("input"), str) or not isinstance(case.get("expected_output"), str):
            raise AssessmentServiceError(f"Test {number} needs an input and an expected output.")
        if not case["expected_output"].strip():
            raise AssessmentServiceError(f"Test {number} needs an expected output.")
    inputs = [case["input"] for case in cases]
    if len(set(inputs)) != len(inputs):
        raise AssessmentServiceError("Two test cases have the same input. Make each test different.")
    visible = sum(1 for case in cases if not case.get("hidden"))
    if visible < MIN_VISIBLE["coding"] or len(cases) - visible < MIN_HIDDEN["coding"]:
        raise AssessmentServiceError(f"Keep at least {MIN_VISIBLE['coding']} visible sample tests and "
                                     f"{MIN_HIDDEN['coding']} hidden tests.")


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
                topic=spec.get("topic") or "", time_limit_minutes=spec.get("time_limit_minutes"),
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
