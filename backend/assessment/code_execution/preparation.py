"""Validate and prepare generated test cases for coding / SQL questions.

validate_test_fields() is pure (used by assessment.generation.validate_exam).
prepare_executable_questions() executes reference solutions: SQL expected
results are always computed by running the reference query (never trusted
from the model); coding tests are checked against the reference program in
Judge0 when it is configured.
"""

from __future__ import annotations

from typing import Any

from assessment.code_execution import sql_runner
from assessment.code_execution.judge0 import ExecutionLimits, ExecutionUnavailable, Judge0Runner, outputs_match
from assessment.code_execution.languages import DEFAULT_LANGUAGE, LANGUAGES, normalize_language

MIN_VISIBLE = {"coding": 2, "sql": 1}
MIN_HIDDEN = {"coding": 3, "sql": 2}
MAX_TESTS = 20
_UNSET: Any = object()


_SQL_SETUP_KEYS = ("setup_sql", "setup", "data_sql", "dataset", "data", "insert_sql", "sql", "input")
_SQL_SCHEMA_KEYS = ("sql_schema", "schema", "schema_sql", "tables_sql", "ddl")


def _as_text(value: Any) -> str | None:
    """Models return strings, lists of lines/statements or bare numbers; normalize to text."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list) and all(isinstance(v, (str, int, float)) for v in value):
        return "\n".join(str(v) for v in value)
    return None


def _hidden_flag(case: dict) -> bool | None:
    for key in ("hidden", "is_hidden"):
        value = case.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
            return value.strip().lower() == "true"
    for key in ("visible", "is_visible", "sample", "is_sample"):
        if isinstance(case.get(key), bool):
            return not case[key]
    return None


def _first_text(case: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if key in case:
            text = _as_text(case.get(key))
            if text is not None:
                return text
    return None


def validate_test_fields(item: dict, qtype: str, label: str) -> dict:
    """Return the executable fields for a generated coding/SQL question, or raise ValueError.

    Tolerates the shapes models commonly produce (lists of statements, numeric
    outputs, alternative key names, missing hidden flags) and only rejects tests
    that cannot be used at all.
    """
    raw_cases = item.get("test_cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"{label}: {qtype.upper()} questions need test_cases.")
    cases: list[dict] = []
    flags: list[bool | None] = []
    seen_inputs: set[str] = set()
    for case in raw_cases[:MAX_TESTS]:
        if not isinstance(case, dict):
            continue
        if qtype == "coding":
            stdin = _first_text(case, ("input", "stdin"))
            expected = _first_text(case, ("expected_output", "output", "expected", "stdout"))
            if stdin is None or expected is None or not expected.strip():
                continue
            if len(stdin) > 20_000 or len(expected) > 20_000 or stdin in seen_inputs:
                continue
            seen_inputs.add(stdin)
            cases.append({"input": stdin, "expected_output": expected})
        else:
            setup = _first_text(case, _SQL_SETUP_KEYS)
            if setup is None:
                continue
            cases.append({"setup_sql": setup})
        flags.append(_hidden_flag(case))

    minimum = MIN_VISIBLE[qtype] + MIN_HIDDEN[qtype]
    if len(cases) < minimum:
        raise ValueError(f"{label}: {qtype.upper()} needs at least {minimum} usable test cases "
                         f"({MIN_VISIBLE[qtype]} visible and {MIN_HIDDEN[qtype]} hidden); got {len(cases)}.")
    # Fill missing flags, then make sure both visible examples and hidden tests exist.
    hidden = [bool(f) if f is not None else index >= MIN_VISIBLE[qtype] for index, f in enumerate(flags)]
    if sum(not h for h in hidden) < MIN_VISIBLE[qtype] or sum(hidden) < MIN_HIDDEN[qtype]:
        hidden = [index >= MIN_VISIBLE[qtype] for index in range(len(cases))]
    for index, case in enumerate(cases):
        case["id"] = f"t{index + 1}"
        case["hidden"] = hidden[index]

    if qtype == "coding":
        return {
            "test_cases": cases,
            "input_format": str(item.get("input_format") or "").strip(),
            "output_format": str(item.get("output_format") or "").strip(),
            "allowed_languages": list(LANGUAGES),
            "default_language": normalize_language(item.get("default_language")) or DEFAULT_LANGUAGE,
        }
    schema = _first_text(item, _SQL_SCHEMA_KEYS) or ""
    if "create table" not in schema.lower():
        raise ValueError(f"{label}: SQL questions need sql_schema with CREATE TABLE statements.")
    return {"test_cases": cases, "sql_schema": schema, "order_matters": item.get("order_matters") is True}


EXECUTABLE_KEYS = ("test_cases", "sql_schema", "order_matters", "input_format", "output_format",
                   "allowed_languages", "default_language", "tests_verified")


def drop_tests(row: dict) -> dict:
    """Keep a question without automatic tests (graded by AI against its reference answer)."""
    for key in EXECUTABLE_KEYS:
        row.pop(key, None)
    return row


def prepare_executable_questions(rows: list[dict], *, runner: Any = _UNSET, strict: bool = True) -> list[dict]:
    """Attach verified expected results.

    strict=True raises ValueError so generation can retry with feedback. strict=False
    (last attempt) keeps a question whose tests cannot be verified, without tests,
    instead of failing the whole exam.
    """
    runner = Judge0Runner.from_env() if runner is _UNSET else runner
    for index, row in enumerate(rows, start=1):
        try:
            _prepare_row(index, row, runner)
        except ValueError:
            if strict:
                raise
            drop_tests(row)
    return rows


def _prepare_row(index: int, row: dict, runner: Any) -> None:
    qtype = row.get("question_type")
    if qtype == "sql" and row.get("test_cases"):
        non_empty = 0
        for case in row["test_cases"]:
            try:
                case["expected"] = sql_runner.expected_from_reference(row["sql_schema"], case["setup_sql"], row["correct_answer"])
            except sql_runner.SqlExecutionError as exc:
                raise ValueError(f"Q{index}: the reference SQL query failed on dataset {case['id']}: {exc}. "
                                 "Use SQLite-compatible SQL for the schema, data and reference query.") from exc
            non_empty += 1 if case["expected"]["rows"] else 0
        if non_empty < 2:
            raise ValueError(f"Q{index}: SQL datasets must make the reference query return rows in at least two datasets.")
        row["tests_verified"] = True
    elif qtype == "coding" and row.get("test_cases"):
        row["tests_verified"] = False
        if runner is None:
            return
        try:
            language = normalize_language(row.get("reference_language")) or DEFAULT_LANGUAGE
            enabled = [c for c in row["test_cases"] if c.get("enabled", True) is not False]
            default = runner.default_limits() if hasattr(runner, "default_limits") else None
            results = runner.run(language, row["correct_answer"], enabled, limits=ExecutionLimits.for_question(row, default))
        except ExecutionUnavailable:
            return  # keep the generated tests; they are marked unverified
        if any(run.status == "error" for run in results):
            return  # the sandbox failed, not the reference: keep the tests unverified
        bad = [case["id"] for case, run in zip(enabled, results)
               if run.status != "ok" or not outputs_match(run.stdout, case["expected_output"], row.get("comparison") or "trim_trailing")]
        if bad:
            raise ValueError(f"Q{index}: the reference solution does not produce expected_output for tests "
                             f"{', '.join(bad)}. Fix the reference program or the expected outputs.")
        row["tests_verified"] = True
