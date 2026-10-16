"""Reference-solution verification for coding / SQL questions.

A question is "verified" only when its reference solution was actually executed
against every enabled test case and all of them passed. Each verification
stores a fingerprint of the solution, language and enabled tests; any later
change makes the stored result stale, so it reads as "not_verified" again.

Statuses: not_verified | verified | failed | unavailable
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from assessment.code_execution import sql_runner
from assessment.code_execution.judge0 import (
    INFRASTRUCTURE_STATUSES, ExecutionLimits, ExecutionUnavailable, Judge0Runner, outputs_match,
)
from assessment.code_execution.languages import DEFAULT_LANGUAGE, LANGUAGES, normalize_language

NOT_VERIFIED, VERIFIED, FAILED, UNAVAILABLE = "not_verified", "verified", "failed", "unavailable"
MAX_TESTS = 30
_UNSET: Any = object()
_CONTENT_KEYS = {"coding": ("input", "expected_output"), "sql": ("setup_sql",)}


def _qtype(question: dict) -> str:
    raw = question.get("question_type") or ""
    return str(raw.value if hasattr(raw, "value") else raw).lower()


def reference_language(question: dict) -> str:
    if _qtype(question) == "sql":
        return "sql"
    return normalize_language(question.get("reference_language")) or DEFAULT_LANGUAGE


def enabled_cases(question: dict) -> list[dict]:
    return [c for c in question.get("test_cases") or [] if isinstance(c, dict) and c.get("enabled", True) is not False]


def fingerprint(question: dict) -> str:
    """Hash of everything verification depends on (not results or computed SQL expectations)."""
    keys = _CONTENT_KEYS.get(_qtype(question), ("input", "expected_output"))
    payload = {
        "type": _qtype(question),
        "language": reference_language(question),
        "reference": question.get("correct_answer") or "",
        "schema": question.get("sql_schema") or "",
        "order_matters": bool(question.get("order_matters")),
        "tests": [[c.get("id")] + [c.get(k) or "" for k in keys] for c in enabled_cases(question)],
        # Extra per-language references, limits and the comparison rule all change what "passes".
        "extra_references": {k: v for k, v in sorted((question.get("reference_solutions") or {}).items()) if v},
        "limits": [question.get("time_limit_seconds"), question.get("memory_limit_mb")],
        "comparison": question.get("comparison") or "trim_trailing",
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def execution_status() -> dict:
    runner = Judge0Runner.from_env()
    return {
        "coding": {"available": runner is not None, "provider": "judge0" if runner else None,
                   "languages": [{"key": k, "label": v["label"]} for k, v in LANGUAGES.items()]},
        "sql": {"available": True, "provider": "sqlite-sandbox"},
    }


def verification_view(question: dict) -> dict:
    """Current verification state; stale results read as not_verified."""
    stored = question.get("verification") or {}
    current = fingerprint(question)
    if stored and stored.get("fingerprint") == current:
        return {k: v for k, v in stored.items() if k != "fingerprint"} | {"stale": False}
    if stored:
        return {"status": NOT_VERIFIED, "stale": True, "results": [], "message": "The solution or test cases changed since the last verification."}
    # Questions generated before this feature: tests_verified meant the reference passed every test.
    if question.get("tests_verified") is True:
        return {"status": VERIFIED, "stale": False, "results": [], "message": "Verified when the question was generated."}
    return {"status": NOT_VERIFIED, "stale": False, "results": [], "message": "The reference solution has not been verified."}


def normalize_test_cases(question_type: str, raw: Any) -> list[dict]:
    """Validate admin-edited test cases; keeps ids stable and assigns ids to new ones."""
    if not isinstance(raw, list):
        raise ValueError("test_cases must be a list.")
    if len(raw) > MAX_TESTS:
        raise ValueError(f"At most {MAX_TESTS} test cases are allowed.")
    cases, seen = [], set()
    for number, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Test case {number} must be an object.")
        case_id = str(item.get("id") or "").strip()[:40] or f"tc_{uuid.uuid4().hex[:10]}"
        if case_id in seen:
            case_id = f"tc_{uuid.uuid4().hex[:10]}"
        seen.add(case_id)
        case = {
            "id": case_id,
            "name": str(item.get("name") or "").strip()[:120],
            "description": str(item.get("description") or "").strip()[:500],
            "hidden": item.get("hidden") is True,
            "enabled": item.get("enabled") is not False,
        }
        if question_type == "sql":
            setup = item.get("setup_sql")
            if not isinstance(setup, str):
                raise ValueError(f"Test case {number}: setup_sql must be text (INSERT statements; may be empty for an empty table).")
            if len(setup) > 50_000:
                raise ValueError(f"Test case {number}: setup_sql is too large.")
            case["setup_sql"] = setup
            if isinstance(item.get("expected"), dict):
                case["expected"] = item["expected"]
        else:
            stdin, expected = item.get("input"), item.get("expected_output")
            if not isinstance(stdin, str) or not isinstance(expected, str):
                raise ValueError(f"Test case {number}: input and expected_output must be text.")
            if not expected.strip():
                raise ValueError(f"Test case {number}: expected_output cannot be empty.")
            if len(stdin) > 20_000 or len(expected) > 20_000:
                raise ValueError(f"Test case {number} is too large.")
            case["input"], case["expected_output"] = stdin, expected
        cases.append(case)
    return cases


def _result(case: dict, passed: bool, status: str, actual: Any = None, error: str = "", time: Optional[float] = None) -> dict:
    return {"id": case.get("id"), "name": case.get("name") or "", "hidden": bool(case.get("hidden")), "passed": passed,
            "status": status, "actual": actual, "error": (error or "")[:1500], "time": time}


def verify_question(question: dict, *, runner: Any = _UNSET) -> tuple[dict, list[dict]]:
    """Execute the reference against enabled tests. Returns (verification, updated_test_cases)."""
    now = datetime.now(timezone.utc).isoformat()
    qtype = _qtype(question)
    reference = str(question.get("correct_answer") or "")
    tests = [dict(c) for c in question.get("test_cases") or [] if isinstance(c, dict)]
    enabled = [c for c in tests if c.get("enabled", True) is not False]
    base = {"fingerprint": fingerprint(question), "verified_at": now, "language": reference_language(question)}

    if not reference.strip():
        return {**base, "status": FAILED, "results": [], "message": "Add a reference solution first."}, tests
    if not enabled:
        return {**base, "status": FAILED, "results": [], "message": "Enable at least one test case."}, tests

    if qtype == "sql":
        results = []
        for case in enabled:
            try:
                case["expected"] = sql_runner.expected_from_reference(question.get("sql_schema") or "", case.get("setup_sql") or "", reference)
                results.append(_result(case, True, "passed", actual=case["expected"]))
            except sql_runner.SqlExecutionError as exc:
                case.pop("expected", None)
                results.append(_result(case, False, "error", error=str(exc)))
        by_id = {c["id"]: c for c in enabled}
        tests = [by_id.get(c.get("id"), c) for c in tests]
        ok = all(r["passed"] for r in results)
        message = ("Reference query ran on every enabled dataset; expected results were recorded."
                   if ok else "The reference query failed on one or more datasets.")
        return {**base, "status": VERIFIED if ok else FAILED, "results": results, "message": message}, tests

    runner = Judge0Runner.from_env() if runner is _UNSET else runner
    if runner is None:
        return {**base, "status": UNAVAILABLE, "results": [],
                "message": "Code execution is not configured. Set JUDGE0_URL (and JUDGE0_AUTH_TOKEN or JUDGE0_RAPIDAPI_KEY)."}, tests
    from assessment.code_execution.coding_config import reference_solutions

    mode = question.get("comparison") or "trim_trailing"
    default = runner.default_limits() if hasattr(runner, "default_limits") else None
    limits = ExecutionLimits.for_question(question, default)
    results, languages = [], []
    for language, code in reference_solutions(question).items():
        try:
            runs = runner.run(language, code, enabled, limits=limits)
        except ExecutionUnavailable as exc:
            return {**base, "status": UNAVAILABLE, "results": [], "message": f"Code execution is unavailable: {exc}"}, tests
        if any(run.status in INFRASTRUCTURE_STATUSES for run in runs) or len(runs) != len(enabled):
            return {**base, "status": UNAVAILABLE, "results": [], "message": "The sandbox failed internally while verifying. Retry."}, tests
        rows = []
        for case, run in zip(enabled, runs):
            if run.status == "ok":
                passed = outputs_match(run.stdout, case.get("expected_output") or "", mode)
                rows.append(_result(case, passed, "passed" if passed else "wrong_answer", run.stdout, run.stderr, run.time))
            else:
                rows.append(_result(case, False, run.status, run.stdout, run.stderr, run.time))
            rows[-1]["language"] = language
            rows[-1]["memory"] = run.memory
        results.extend(rows)
        languages.append({"language": language, "label": LANGUAGES[language]["label"],
                          "passed": sum(r["passed"] for r in rows), "total": len(rows),
                          "status": VERIFIED if all(r["passed"] for r in rows) else FAILED})
    ok = all(entry["status"] == VERIFIED for entry in languages)
    summary = "; ".join(f"{e['label']}: {e['passed']}/{e['total']}" for e in languages)
    failing = [r for r in results if not r["passed"]]
    message = (f"Every reference solution passed all {len(enabled)} enabled test cases ({summary})." if ok
               else f"The reference solution fails {len(failing)} test run(s) ({summary}). Fix the solution or the expected output.")
    return {**base, "status": VERIFIED if ok else FAILED, "results": results, "languages": languages, "message": message}, tests
