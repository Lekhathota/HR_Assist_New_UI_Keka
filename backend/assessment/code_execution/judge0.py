"""Execute candidate programs in a Judge0 sandbox (hosted RapidAPI or self-hosted).

Candidate code never runs inside the HR Assist server: it would otherwise be
able to read server secrets. Configure one of:

  JUDGE0_URL=https://judge0-ce.p.rapidapi.com  JUDGE0_RAPIDAPI_KEY=...   (hosted)
  JUDGE0_URL=https://judge0.your-company.com   JUDGE0_AUTH_TOKEN=...    (self-hosted)
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from assessment.code_execution.languages import judge0_language_id

BATCH_SIZE = 20
_OUTPUT_LIMIT = 4000  # characters kept per stream for display; the sandbox limit is ExecutionLimits.max_output_kb
# Statuses caused by the sandbox itself, not by the submitted program: never a candidate failure.
INFRASTRUCTURE_STATUSES = frozenset({"error"})


class ExecutionUnavailable(Exception):
    """The sandbox could not run the code (not configured, auth, outage, timeout)."""


@dataclass
class ExecutionResult:
    case_id: str
    # ok | compile_error | runtime_error | time_limit | memory_limit | output_limit | error (sandbox failure)
    status: str
    stdout: str = ""
    stderr: str = ""
    time: Optional[float] = None
    memory: Optional[int] = None


@dataclass
class ExecutionLimits:
    """Per-run sandbox limits. Judge0 enforces them inside isolate; network is always disabled."""
    cpu_time_limit: float = 2.0      # seconds of CPU per test
    wall_time_limit: float = 5.0     # seconds of wall-clock per test
    memory_limit_kb: int = 128_000
    max_output_kb: int = 64          # stdout/stderr file size limit

    @classmethod
    def for_question(cls, question: dict, default: "ExecutionLimits | None" = None) -> "ExecutionLimits":
        base = default or cls()
        cpu = float(question.get("time_limit_seconds") or base.cpu_time_limit)
        memory_mb = question.get("memory_limit_mb")
        return cls(cpu_time_limit=cpu, wall_time_limit=max(base.wall_time_limit, cpu * 2.5),
                   memory_limit_kb=int(memory_mb) * 1024 if memory_mb else base.memory_limit_kb,
                   max_output_kb=int(question.get("max_output_kb") or base.max_output_kb))


def _b64(text: str) -> str:
    return base64.b64encode((text or "").encode("utf-8")).decode("ascii")


def _unb64(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return base64.b64decode(value).decode("utf-8", errors="replace")[:_OUTPUT_LIMIT]
    except (ValueError, TypeError):
        return ""


def _status(status_id: int, memory: Optional[int] = None, memory_limit_kb: int = 0) -> str:
    """Judge0 status ids: 3 accepted, 4 wrong answer, 5 TLE, 6 compile error, 7-12 runtime errors
    (8 = SIGXFSZ, output file too large), 13 internal error, 14 exec format error."""
    if status_id in (3, 4):  # accepted / wrong answer: we compare output ourselves
        return "ok"
    if status_id == 5:
        return "time_limit"
    if status_id == 6:
        return "compile_error"
    if status_id == 8:
        return "output_limit"
    if 7 <= status_id <= 12:
        # isolate kills a process at its memory cap; Judge0 reports a signal with memory at the limit.
        if memory and memory_limit_kb and memory >= memory_limit_kb * 0.95:
            return "memory_limit"
        return "runtime_error"
    return "error"  # 13 internal error, 14 exec format error, unknown: the sandbox failed, not the program


class Judge0Runner:
    def __init__(self, base_url: str, *, rapidapi_key: str = "", auth_token: str = "",
                 cpu_time_limit: float = 2.0, memory_limit_kb: int = 128_000, wait_seconds: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.rapidapi_key = rapidapi_key
        self.auth_token = auth_token
        self.cpu_time_limit = cpu_time_limit
        self.memory_limit_kb = memory_limit_kb
        self.wait_seconds = wait_seconds

    @classmethod
    def from_env(cls) -> Optional["Judge0Runner"]:
        url = (os.environ.get("JUDGE0_URL") or "").strip()
        if not url:
            return None
        return cls(
            url,
            rapidapi_key=(os.environ.get("JUDGE0_RAPIDAPI_KEY") or "").strip(),
            auth_token=(os.environ.get("JUDGE0_AUTH_TOKEN") or "").strip(),
            cpu_time_limit=float(os.environ.get("JUDGE0_CPU_TIME_LIMIT") or 2),
            memory_limit_kb=int(os.environ.get("JUDGE0_MEMORY_LIMIT_KB") or 128_000),
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.rapidapi_key:
            headers["X-RapidAPI-Key"] = self.rapidapi_key
            headers["X-RapidAPI-Host"] = urllib.parse.urlsplit(self.base_url).hostname or ""
        if self.auth_token:
            headers["X-Auth-Token"] = self.auth_token
        return headers

    def _request(self, method: str, path: str, body: Optional[dict] = None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(f"{self.base_url}{path}", data=data, method=method, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8") or "null")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ExecutionUnavailable("Judge0 rejected the credentials (check JUDGE0_RAPIDAPI_KEY / JUDGE0_AUTH_TOKEN).") from exc
            if exc.code == 429:
                raise ExecutionUnavailable("Judge0 rate limit reached.") from exc
            raise ExecutionUnavailable(f"Judge0 returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise ExecutionUnavailable(f"Judge0 is unreachable: {exc}") from exc

    def default_limits(self) -> ExecutionLimits:
        return ExecutionLimits(cpu_time_limit=self.cpu_time_limit, memory_limit_kb=self.memory_limit_kb)

    def run(self, language: str, source: str, cases: list[dict], limits: Optional[ExecutionLimits] = None) -> list[ExecutionResult]:
        """Run source once per case (stdin = case['input']). Returns results in case order."""
        limits = limits or self.default_limits()
        results: list[ExecutionResult] = []
        for start in range(0, len(cases), BATCH_SIZE):
            chunk = cases[start:start + BATCH_SIZE]
            payload = {"submissions": [{
                "language_id": judge0_language_id(language),
                "source_code": _b64(source),
                "stdin": _b64(str(case.get("input") or "")),
                "cpu_time_limit": limits.cpu_time_limit,
                "wall_time_limit": limits.wall_time_limit,
                "memory_limit": limits.memory_limit_kb,
                "max_file_size": limits.max_output_kb,
                "enable_network": False,
            } for case in chunk]}
            created = self._request("POST", "/submissions/batch?base64_encoded=true", payload)
            tokens = [row.get("token") for row in created or [] if isinstance(row, dict)]
            if len(tokens) != len(chunk) or not all(tokens):
                raise ExecutionUnavailable("Judge0 did not accept the submissions.")
            results.extend(self._collect(tokens, chunk, limits))
        return results

    def _collect(self, tokens: list[str], cases: list[dict], limits: Optional[ExecutionLimits] = None) -> list[ExecutionResult]:
        limits = limits or self.default_limits()
        deadline = time.monotonic() + self.wait_seconds
        fields = "token,status,stdout,stderr,compile_output,time,memory"
        query = f"/submissions/batch?tokens={','.join(tokens)}&base64_encoded=true&fields={fields}"
        delay = 0.5
        while True:
            rows = (self._request("GET", query) or {}).get("submissions") or []
            if len(rows) == len(tokens) and all((row.get("status") or {}).get("id", 0) >= 3 for row in rows):
                break
            if time.monotonic() > deadline:
                raise ExecutionUnavailable("Judge0 did not finish running the tests in time.")
            time.sleep(delay)
            delay = min(delay * 1.5, 2.0)
        by_token = {row.get("token"): row for row in rows}
        out = []
        for token, case in zip(tokens, cases):
            row = by_token.get(token) or {}
            memory = int(row["memory"]) if row.get("memory") not in (None, "") else None
            status = _status(int((row.get("status") or {}).get("id") or 0), memory, limits.memory_limit_kb)
            stderr = _unb64(row.get("compile_output")) if status == "compile_error" else _unb64(row.get("stderr"))
            if status == "error":
                stderr = stderr or str((row.get("status") or {}).get("description") or "Judge0 internal error")
            out.append(ExecutionResult(
                case_id=str(case.get("id")), status=status, stdout=_unb64(row.get("stdout")), stderr=stderr,
                time=float(row["time"]) if row.get("time") not in (None, "") else None, memory=memory,
            ))
        return out


COMPARISON_MODES = {
    "trim_trailing": "Ignore trailing spaces on each line and trailing blank lines (default)",
    "exact": "Exact match (only line-ending style is normalised)",
    "tokens": "Compare whitespace-separated tokens (ignore all spacing and line breaks)",
}


def outputs_match(actual: str, expected: str, mode: str = "trim_trailing") -> bool:
    """Compare program output with the expected output under the question's comparison rule."""
    actual = str(actual or "").replace("\r\n", "\n")
    expected = str(expected or "").replace("\r\n", "\n")
    if mode == "exact":
        return actual == expected
    if mode == "tokens":
        return actual.split() == expected.split()

    def norm(text: str) -> list[str]:
        lines = [line.rstrip() for line in text.split("\n")]
        while lines and not lines[-1]:
            lines.pop()
        return lines
    return norm(actual) == norm(expected)
