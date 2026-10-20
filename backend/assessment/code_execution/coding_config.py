"""Coding question configuration: execution limits, scoring rules, qualification criteria.

Everything here is stored on the question document, so it travels with the question into
the published assessment version. Scoring is based only on executed test results:
the candidate's source code is never compared with the reference solution.
"""

from __future__ import annotations

import math
from typing import Any

from assessment.code_execution.judge0 import COMPARISON_MODES
from assessment.code_execution.languages import LANGUAGES, normalize_language

EXECUTABLE_TYPES = ("coding", "sql")
DIFFICULTIES = ("Easy", "Medium", "Hard")
TIME_LIMIT_RANGE = (0.5, 15.0)        # CPU seconds per test
MEMORY_LIMIT_RANGE = (16, 512)        # MB
MAX_TEXT = 5000
MAX_REFERENCE_CHARS = 50_000
DEFAULT_TIME_LIMIT_SECONDS = 2.0
DEFAULT_MEMORY_LIMIT_MB = 128
DEFAULT_COMPARISON = "trim_trailing"
DEFAULT_SCORING = {
    "partial_credit": True,      # marks in proportion to the weight of passed tests
    "min_tests_passed": 0,       # qualification: at least this many tests pass
    "min_score_percent": 50.0,   # qualification: at least this share of the question's marks
    "require_mandatory": True,   # qualification: every test marked mandatory passes
}
TEXT_FIELDS = ("title", "input_format", "output_format", "constraints", "edge_cases", "skill_tag")


def qtype(question: dict) -> str:
    raw = question.get("question_type") or ""
    return str(raw.value if hasattr(raw, "value") else raw).lower()


def enabled_cases(question: dict) -> list[dict]:
    return [c for c in question.get("test_cases") or [] if isinstance(c, dict) and c.get("enabled", True) is not False]


def case_weight(case: dict) -> float:
    try:
        weight = float(case.get("weight", 1) if case.get("weight") not in (None, "") else 1)
    except (TypeError, ValueError):
        return 1.0
    return weight if weight > 0 else 1.0


def scoring_rules(question: dict) -> dict:
    stored = question.get("scoring") if isinstance(question.get("scoring"), dict) else {}
    return {**DEFAULT_SCORING, **{k: v for k, v in stored.items() if k in DEFAULT_SCORING}}


def default_title(text: str) -> str:
    first = " ".join(str(text or "").split()[:10])
    return first.rstrip(".,;:") + ("…" if len(str(text or "").split()) > 10 else "")


def allowed_languages(question: dict) -> list[str]:
    if qtype(question) == "sql":
        return ["sql"]
    keys = [k for k in question.get("allowed_languages") or [] if k in LANGUAGES]
    return keys or list(LANGUAGES)


def reference_solutions(question: dict) -> dict[str, str]:
    """All reference programs by language: the primary (correct_answer) plus any extra ones."""
    from assessment.code_execution.verification import reference_language

    out = {}
    primary = str(question.get("correct_answer") or "")
    if primary.strip():
        out[reference_language(question)] = primary
    for language, code in (question.get("reference_solutions") or {}).items():
        if language in LANGUAGES and isinstance(code, str) and code.strip() and language not in out:
            out[language] = code
    return out


def config_view(question: dict) -> dict:
    """The question's coding configuration with defaults filled in (recruiter view only)."""
    is_sql = qtype(question) == "sql"
    return {
        "title": question.get("title") or default_title(question.get("question_text")),
        "question_text": question.get("question_text") or "",
        "skill_tag": question.get("skill_tag") or "",
        "difficulty": question.get("difficulty") or "Medium",
        "points": int(question.get("points") or 0) or 10,
        "allowed_languages": allowed_languages(question),
        "input_format": question.get("input_format") or "",
        "output_format": question.get("output_format") or "",
        "constraints": question.get("constraints") or "",
        "edge_cases": question.get("edge_cases") or "",
        "time_limit_seconds": None if is_sql else float(question.get("time_limit_seconds") or DEFAULT_TIME_LIMIT_SECONDS),
        "memory_limit_mb": None if is_sql else int(question.get("memory_limit_mb") or DEFAULT_MEMORY_LIMIT_MB),
        "comparison": question.get("comparison") or DEFAULT_COMPARISON,
        "scoring": scoring_rules(question),
        "reference_solutions": {k: v for k, v in (question.get("reference_solutions") or {}).items() if k in LANGUAGES},
        "generation_prompt": question.get("generation_prompt") or "",
    }


def _number(value: Any, label: str, low: float, high: float, *, integer: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number between {low:g} and {high:g}.") from None
    if math.isnan(number) or not low <= number <= high or (integer and number != int(number)):
        kind = "a whole number" if integer else "a number"
        raise ValueError(f"{label} must be {kind} between {low:g} and {high:g}.")
    return int(number) if integer else number


def normalize_config(question_type: str, data: dict, current: dict) -> dict:
    """Validate recruiter-edited configuration fields; returns the question patch (raises ValueError)."""
    patch: dict[str, Any] = {}
    for key in TEXT_FIELDS:
        if key in data:
            value = data[key]
            if value is None:
                value = ""
            if not isinstance(value, str) or len(value) > MAX_TEXT:
                raise ValueError(f"{key.replace('_', ' ').capitalize()} must be text of at most {MAX_TEXT} characters.")
            patch[key] = value.strip()
    if "question_text" in data:
        text = data["question_text"]
        if not isinstance(text, str) or len(text.split()) < 5:
            raise ValueError("The problem statement must describe the task (at least 5 words).")
        patch["question_text"] = text.strip()
    if "difficulty" in data:
        if data["difficulty"] not in DIFFICULTIES:
            raise ValueError("Difficulty must be Easy, Medium or Hard.")
        patch["difficulty"] = data["difficulty"]
    if "points" in data:
        patch["points"] = int(_number(data["points"], "Maximum marks", 1, 100, integer=True))
    if "comparison" in data:
        if data["comparison"] not in COMPARISON_MODES:
            raise ValueError(f"Output comparison must be one of: {', '.join(COMPARISON_MODES)}.")
        patch["comparison"] = data["comparison"]
    if question_type == "coding":
        if "allowed_languages" in data:
            raw = data["allowed_languages"]
            if not isinstance(raw, list) or not raw:
                raise ValueError("Select at least one allowed programming language.")
            languages = []
            for item in raw:
                language = normalize_language(item)
                if not language:
                    raise ValueError(f"Unsupported language '{item}'. Use Python, JavaScript, Java, C or C++.")
                if language not in languages:
                    languages.append(language)
            patch["allowed_languages"] = languages
            if current.get("default_language") not in languages:
                patch["default_language"] = languages[0]
        if "time_limit_seconds" in data:
            patch["time_limit_seconds"] = _number(data["time_limit_seconds"], "Time limit (seconds)", *TIME_LIMIT_RANGE)
        if "memory_limit_mb" in data:
            patch["memory_limit_mb"] = int(_number(data["memory_limit_mb"], "Memory limit (MB)", *MEMORY_LIMIT_RANGE, integer=True))
        if "reference_solutions" in data:
            raw = data["reference_solutions"] or {}
            if not isinstance(raw, dict):
                raise ValueError("Reference solutions must map a language to its program.")
            extra = {}
            for key, code in raw.items():
                language = normalize_language(key)
                if not language:
                    raise ValueError(f"Unsupported reference language '{key}'.")
                if not isinstance(code, str) or len(code) > MAX_REFERENCE_CHARS:
                    raise ValueError(f"The {LANGUAGES[language]['label']} reference solution must be text (50,000 characters maximum).")
                if code.strip():
                    extra[language] = code
            patch["reference_solutions"] = extra
    if "scoring" in data:
        raw = data["scoring"]
        if not isinstance(raw, dict):
            raise ValueError("Scoring rules must be an object.")
        rules = scoring_rules(current)
        for key in ("partial_credit", "require_mandatory"):
            if key in raw:
                if not isinstance(raw[key], bool):
                    raise ValueError(f"{key.replace('_', ' ').capitalize()} must be true or false.")
                rules[key] = raw[key]
        if "min_tests_passed" in raw:
            rules["min_tests_passed"] = int(_number(raw["min_tests_passed"], "Minimum tests passed", 0, 30, integer=True))
        if "min_score_percent" in raw:
            rules["min_score_percent"] = _number(raw["min_score_percent"], "Minimum coding score (%)", 0, 100)
        patch["scoring"] = rules
    return patch


def normalize_case_scoring(cases: list[dict], raw_cases: list) -> list[dict]:
    """Copy validated weight / mandatory flags from the recruiter's test cases."""
    for case, raw in zip(cases, raw_cases):
        raw = raw if isinstance(raw, dict) else {}
        if raw.get("weight") not in (None, ""):
            case["weight"] = _number(raw["weight"], f"Weight of test '{case.get('name') or case['id']}'", 0.01, 100)
        else:
            case["weight"] = 1.0
        if "mandatory" in raw and not isinstance(raw["mandatory"], bool):
            raise ValueError("Mandatory must be true or false.")
        case["mandatory"] = raw.get("mandatory") is True
    return cases


def config_problems(question: dict) -> list[str]:
    """Why this coding/SQL question cannot be published. Empty when it is ready."""
    from assessment.code_execution.verification import verification_view

    problems: list[str] = []
    kind = qtype(question)
    cases = enabled_cases(question)
    visible = [c for c in cases if not c.get("hidden")]
    hidden = [c for c in cases if c.get("hidden")]
    rules = scoring_rules(question)
    if not str(question.get("correct_answer") or "").strip():
        problems.append("No reference solution.")
    if not cases:
        problems.append("No enabled test cases.")
    else:
        if not visible:
            problems.append("Add at least one public sample test case.")
        if not hidden:
            problems.append("Add at least one hidden test case.")
    if any(case_weight(c) <= 0 for c in cases):
        problems.append("Test-case weights must be positive.")
    if rules["min_tests_passed"] > len(cases):
        problems.append(f"Minimum tests passed ({rules['min_tests_passed']}) is more than the {len(cases)} enabled test cases.")
    if not 0 <= float(rules["min_score_percent"]) <= 100:
        problems.append("Minimum coding score must be between 0 and 100%.")
    if not int(question.get("points") or 0) > 0:
        problems.append("Maximum marks must be at least 1.")
    if kind == "coding":
        if not [k for k in question.get("allowed_languages") or list(LANGUAGES) if k in LANGUAGES]:
            problems.append("No allowed programming language.")
        seconds = float(question.get("time_limit_seconds") or DEFAULT_TIME_LIMIT_SECONDS)
        memory = int(question.get("memory_limit_mb") or DEFAULT_MEMORY_LIMIT_MB)
        if not TIME_LIMIT_RANGE[0] <= seconds <= TIME_LIMIT_RANGE[1]:
            problems.append("Time limit is out of range.")
        if not MEMORY_LIMIT_RANGE[0] <= memory <= MEMORY_LIMIT_RANGE[1]:
            problems.append("Memory limit is out of range.")
    verification = verification_view(question)
    if verification["status"] != "verified":
        problems.append(_VERIFICATION_REASONS.get(verification["status"], NOT_VERIFIED_REASON))
    return problems


NOT_VERIFIED_REASON = "The reference solution has not been verified against the current tests."
_VERIFICATION_REASONS = {"failed": "The reference solution fails one or more test cases.",
                         "unavailable": "The reference solution could not be executed (code execution unavailable)."}
# Reasons that only mean "not executed yet", as opposed to a solution that ran and failed.
UNVERIFIED_REASONS = frozenset({NOT_VERIFIED_REASON, _VERIFICATION_REASONS["unavailable"]})


def score_outcomes(question: dict, outcomes: list[Any]) -> dict:
    """Marks, pass state and qualification from executed test outcomes.

    outcomes: objects or dicts with id, passed and status, in any order.
    """
    def get(outcome, key):
        return outcome.get(key) if isinstance(outcome, dict) else getattr(outcome, key, None)

    cases = {str(c.get("id")): c for c in enabled_cases(question)}
    rules = scoring_rules(question)
    points = float(question.get("points") or 0)
    total_weight = passed_weight = 0.0
    passed_ids, mandatory_failed, statuses = [], [], []
    for outcome in outcomes:
        case = cases.get(str(get(outcome, "id")), {})
        weight = case_weight(case)
        total_weight += weight
        statuses.append(str(get(outcome, "status") or ""))
        if get(outcome, "passed"):
            passed_weight += weight
            passed_ids.append(str(get(outcome, "id")))
        elif case.get("mandatory"):
            mandatory_failed.append(case.get("name") or str(get(outcome, "id")))
    total, passed = len(outcomes), len(passed_ids)
    full_pass = total > 0 and passed == total
    if not total:
        fraction = 0.0
    elif rules["partial_credit"]:
        fraction = passed_weight / total_weight
    else:
        fraction = 1.0 if full_pass else 0.0
    marks = round(points * fraction, 2)
    percent = round(fraction * 100, 2)

    error_kind = ""
    if total and passed == 0:
        if "compile_error" in statuses:
            error_kind = "compile_error"
        elif all(s in {"runtime_error", "time_limit", "memory_limit", "output_limit"} for s in statuses):
            error_kind = "runtime_error"
    if error_kind:
        result_status = "execution_error"
    elif full_pass:
        result_status = "passed"
    elif marks > 0 or passed:
        result_status = "partially_passed"
    else:
        result_status = "not_passed"

    checks = [
        {"rule": "min_tests_passed", "label": f"At least {rules['min_tests_passed']} test case(s) passed",
         "required": rules["min_tests_passed"], "actual": passed, "met": passed >= rules["min_tests_passed"]},
        {"rule": "min_score_percent", "label": f"At least {rules['min_score_percent']:g}% of the marks",
         "required": rules["min_score_percent"], "actual": percent, "met": percent >= float(rules["min_score_percent"])},
    ]
    if rules["require_mandatory"] and any(c.get("mandatory") for c in cases.values()):
        checks.append({"rule": "mandatory_tests", "label": "Every mandatory test case passed",
                       "required": True, "actual": not mandatory_failed, "met": not mandatory_failed})
    qualified = all(c["met"] for c in checks)
    return {
        "marks": marks, "max_marks": points, "score_percent": percent,
        "tests_passed": passed, "tests_total": total,
        "weight_passed": round(passed_weight, 4), "weight_total": round(total_weight, 4),
        "result_status": result_status, "error_kind": error_kind,
        "qualification": "qualified" if qualified else "not_qualified",
        "qualification_checks": checks, "mandatory_failed": mandatory_failed,
        "scoring_rules": rules,
    }
