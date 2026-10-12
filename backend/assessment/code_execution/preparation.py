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
from assessment.code_execution.judge0 import ExecutionUnavailable, Judge0Runner, outputs_match
from assessment.code_execution.languages import DEFAULT_LANGUAGE, LANGUAGES, normalize_language

MIN_VISIBLE = {"coding": 2, "sql": 1}
MIN_HIDDEN = {"coding": 3, "sql": 2}
MAX_TESTS = 20
_UNSET: Any = object()


def validate_test_fields(item: dict, qtype: str, label: str) -> dict:
    """Return the executable fields for a generated coding/SQL question, or raise ValueError."""
    raw_cases = item.get("test_cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"{label}: {qtype.upper()} questions need test_cases.")
    if len(raw_cases) > MAX_TESTS:
        raise ValueError(f"{label}: at most {MAX_TESTS} test cases are allowed.")
    cases = []
    for number, case in enumerate(raw_cases, start=1):
        if not isinstance(case, dict) or not isinstance(case.get("hidden"), bool):
            raise ValueError(f"{label}: each test case must be an object with a boolean hidden flag.")
        if qtype == "coding":
            if not isinstance(case.get("input"), str) or not isinstance(case.get("expected_output"), str):
                raise ValueError(f"{label}: coding tests need string input and expected_output.")
            if not case["expected_output"].strip():
                raise ValueError(f"{label}: coding test {number} has an empty expected_output.")
            if len(case["input"]) > 20_000 or len(case["expected_output"]) > 20_000:
                raise ValueError(f"{label}: coding test {number} is too large.")
            cases.append({"id": f"t{number}", "input": case["input"], "expected_output": case["expected_output"],
                          "hidden": case["hidden"]})
        else:
            setup = case.get("setup_sql")
            if not isinstance(setup, str) or "insert" not in setup.lower():
                raise ValueError(f"{label}: each SQL test needs setup_sql INSERT statements.")
            cases.append({"id": f"t{number}", "setup_sql": setup, "hidden": case["hidden"]})
    visible = sum(1 for c in cases if not c["hidden"])
    hidden = len(cases) - visible
    if visible < MIN_VISIBLE[qtype] or hidden < MIN_HIDDEN[qtype]:
        raise ValueError(f"{label}: {qtype.upper()} needs at least {MIN_VISIBLE[qtype]} visible and "
                         f"{MIN_HIDDEN[qtype]} hidden test cases.")
    if qtype == "coding":
        if len({c["input"] for c in cases}) != len(cases):
            raise ValueError(f"{label}: coding test inputs must be distinct.")
        return {
            "test_cases": cases,
            "input_format": str(item.get("input_format") or "").strip(),
            "output_format": str(item.get("output_format") or "").strip(),
            "allowed_languages": list(LANGUAGES),
            "default_language": normalize_language(item.get("default_language")) or DEFAULT_LANGUAGE,
        }
    schema = item.get("sql_schema")
    if not isinstance(schema, str) or "create table" not in schema.lower():
        raise ValueError(f"{label}: SQL questions need sql_schema with CREATE TABLE statements.")
    return {"test_cases": cases, "sql_schema": schema, "order_matters": item.get("order_matters") is True}


def prepare_executable_questions(rows: list[dict], *, runner: Any = _UNSET) -> list[dict]:
    """Attach verified expected results. Raises ValueError so generation can retry."""
    runner = Judge0Runner.from_env() if runner is _UNSET else runner
    for index, row in enumerate(rows, start=1):
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
                continue
            try:
                results = runner.run("python", row["correct_answer"], row["test_cases"])
            except ExecutionUnavailable:
                continue  # keep the generated tests; they are marked unverified
            bad = [case["id"] for case, run in zip(row["test_cases"], results)
                   if run.status != "ok" or not outputs_match(run.stdout, case["expected_output"])]
            if bad:
                raise ValueError(f"Q{index}: the Python reference solution does not produce expected_output for tests "
                                 f"{', '.join(bad)}. Fix the reference program or the expected outputs.")
            row["tests_verified"] = True
    return rows
