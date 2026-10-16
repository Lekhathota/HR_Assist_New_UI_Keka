"""Grade coding and SQL answers by executing them against visible and hidden test cases.

  SQL     -> executed in an in-memory SQLite sandbox          (method "sql_executed")
  Coding  -> executed in the Judge0 sandbox (JUDGE0_URL)      (method "executed")

Results are never estimated: when the sandbox is not configured, unreachable or fails
internally, ExecutionUnavailable is raised so the answer is recorded as an
infrastructure error that can be re-graded, never as a candidate failure.
Questions without test cases cannot be graded automatically (ExecutionUnavailable).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from assessment.code_execution import sql_runner
from assessment.code_execution.judge0 import (
    INFRASTRUCTURE_STATUSES, ExecutionLimits, ExecutionUnavailable, Judge0Runner, outputs_match,
)
from assessment.code_execution.languages import DEFAULT_LANGUAGE, LANGUAGES, normalize_language

_UNSET: Any = object()


@dataclass
class TestOutcome:
    id: str
    hidden: bool
    passed: bool
    # passed | failed | error | compile_error | runtime_error | time_limit | memory_limit | output_limit
    status: str
    input: Any = None
    expected: Any = None
    actual: Any = None
    error: str = ""
    time: Optional[float] = None
    memory: Optional[int] = None


@dataclass
class GradeResult:
    method: str
    language: str = ""
    outcomes: list[TestOutcome] = field(default_factory=list)
    fraction: Optional[float] = None  # only for answers graded without tests
    feedback: str = ""
    note: str = ""

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def passed(self) -> int:
        return sum(1 for o in self.outcomes if o.passed)

    @property
    def score_fraction(self) -> float:
        if self.fraction is not None:
            return self.fraction
        return self.passed / self.total if self.total else 0.0

    def summary(self) -> dict[str, Any]:
        visible = [o for o in self.outcomes if not o.hidden]
        hidden = [o for o in self.outcomes if o.hidden]
        times = [o.time for o in self.outcomes if o.time is not None]
        memory = [o.memory for o in self.outcomes if o.memory is not None]
        statuses = {o.status for o in self.outcomes}
        return {
            "method": self.method, "language": self.language,
            "tests_passed": self.passed, "tests_total": self.total,
            "visible_passed": sum(o.passed for o in visible), "visible_total": len(visible),
            "hidden_passed": sum(o.passed for o in hidden), "hidden_total": len(hidden),
            "score_fraction": round(self.score_fraction, 4), "feedback": self.feedback, "note": self.note,
            "compile_status": "compile_error" if "compile_error" in statuses else ("compiled" if self.outcomes else "not_run"),
            "max_time": max(times) if times else None, "max_memory_kb": max(memory) if memory else None,
        }


def _qtype(question: dict) -> str:
    raw = question.get("question_type") or ""
    return str(raw.value if hasattr(raw, "value") else raw).lower()


def resolve_language(question: dict, requested: object) -> str:
    allowed = [k for k in (question.get("allowed_languages") or list(LANGUAGES)) if k in LANGUAGES] or list(LANGUAGES)
    language = normalize_language(requested) or normalize_language(question.get("default_language")) or DEFAULT_LANGUAGE
    if language not in allowed:
        raise ValueError(f"{language} is not allowed for this question.")
    return language


def _cases(question: dict, include_hidden: bool) -> list[dict]:
    cases = [c for c in question.get("test_cases") or [] if isinstance(c, dict) and c.get("enabled", True) is not False]
    return cases if include_hidden else [c for c in cases if not c.get("hidden")]


def grade_sql(question: dict, query: str, *, include_hidden: bool = True) -> GradeResult:
    result = GradeResult(method="sql_executed", language="sql")
    order_matters = bool(question.get("order_matters"))
    for case in _cases(question, include_hidden):
        hidden = bool(case.get("hidden"))
        expected = case.get("expected") or {"columns": [], "rows": []}
        try:
            actual = sql_runner.run_query(question.get("sql_schema") or "", case.get("setup_sql") or "", query)
            passed = sql_runner.results_match(actual, expected, order_matters)
            result.outcomes.append(TestOutcome(
                id=str(case.get("id")), hidden=hidden, passed=passed, status="passed" if passed else "failed",
                input=None if hidden else case.get("setup_sql"), expected=None if hidden else expected,
                actual=None if hidden else sql_runner.preview_rows(actual)))
        except sql_runner.SqlExecutionError as exc:
            result.outcomes.append(TestOutcome(id=str(case.get("id")), hidden=hidden, passed=False, status="error",
                                               input=None if hidden else case.get("setup_sql"),
                                               expected=None if hidden else expected, error=str(exc)[:500]))
    return result


def execute_program(question: dict, code: str, language: str, cases: list[dict], *, runner: Any = _UNSET) -> list:
    """Run a program on the given cases in the sandbox with the question's limits; raises ExecutionUnavailable."""
    runner = Judge0Runner.from_env() if runner is _UNSET else runner
    if runner is None:
        raise ExecutionUnavailable("Code execution is not configured (set JUDGE0_URL).")
    default = runner.default_limits() if hasattr(runner, "default_limits") else None
    runs = runner.run(language, code, cases, limits=ExecutionLimits.for_question(question, default))
    if len(runs) != len(cases):
        raise ExecutionUnavailable("The sandbox returned an incomplete set of results.")
    broken = next((run for run in runs if run.status in INFRASTRUCTURE_STATUSES), None)
    if broken:
        raise ExecutionUnavailable(f"The sandbox failed internally: {broken.stderr or 'unknown error'}")
    return runs


def grade_code(question: dict, code: str, language: str, *, include_hidden: bool = True,
               runner: Any = _UNSET) -> GradeResult:
    cases = _cases(question, include_hidden)
    mode = question.get("comparison") or "trim_trailing"
    executions = execute_program(question, code, language, cases, runner=runner)
    result = GradeResult(method="executed", language=language)
    for case, run in zip(cases, executions):
        hidden = bool(case.get("hidden"))
        if run.status == "ok":
            passed = outputs_match(run.stdout, case.get("expected_output") or "", mode)
            status = "passed" if passed else "failed"
        else:
            passed, status = False, run.status
        result.outcomes.append(TestOutcome(
            id=str(case.get("id")), hidden=hidden, passed=passed, status=status,
            input=None if hidden else case.get("input"),
            expected=None if hidden else case.get("expected_output"),
            actual=None if hidden else run.stdout,
            # Hidden tests reveal only compiler output, never their data or the program's output on them.
            error="" if hidden and status != "compile_error" else run.stderr[:1500],
            time=run.time, memory=run.memory))
    return result


def grade_answer(question: dict, answer: str, language: object = "", *, include_hidden: bool = True,
                 runner: Any = _UNSET) -> GradeResult:
    qtype = _qtype(question)
    has_tests = bool(_cases(question, True))
    if qtype == "sql" and has_tests and question.get("sql_schema"):
        return grade_sql(question, answer, include_hidden=include_hidden)
    if qtype == "coding" and has_tests:
        return grade_code(question, answer, resolve_language(question, language),
                          include_hidden=include_hidden, runner=runner)
    raise ExecutionUnavailable("The question has no test cases, so it cannot be graded automatically; review it manually.")


def outcome_dicts(result: GradeResult) -> list[dict]:
    return [asdict(o) for o in result.outcomes]
