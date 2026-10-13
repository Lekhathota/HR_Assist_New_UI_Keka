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
_OUTPUT_LIMIT = 4000


class ExecutionUnavailable(Exception):
    """The sandbox could not run the code (not configured, auth, outage, timeout)."""


@dataclass
class ExecutionResult:
    case_id: str
    status: str  # ok | compile_error | runtime_error | time_limit | memory_limit | error
    stdout: str = ""
    stderr: str = ""
    time: Optional[float] = None
    memory: Optional[int] = None


def _b64(text: str) -> str:
    return base64.b64encode((text or "").encode("utf-8")).decode("ascii")


def _unb64(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return base64.b64decode(value).decode("utf-8", errors="replace")[:_OUTPUT_LIMIT]
    except (ValueError, TypeError):
        return ""


def _status(status_id: int) -> str:
    if status_id in (3, 4):  # accepted / wrong answer: we compare output ourselves
        return "ok"
    if status_id == 5:
        return "time_limit"
    if status_id == 6:
        return "compile_error"
    if 7 <= status_id <= 12:
        return "runtime_error"
    return "error"


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

    def run(self, language: str, source: str, cases: list[dict]) -> list[ExecutionResult]:
        """Run source once per case (stdin = case['input']). Returns results in case order."""
        results: list[ExecutionResult] = []
        for start in range(0, len(cases), BATCH_SIZE):
            chunk = cases[start:start + BATCH_SIZE]
            payload = {"submissions": [{
                "language_id": judge0_language_id(language),
                "source_code": _b64(source),
                "stdin": _b64(str(case.get("input") or "")),
                "cpu_time_limit": self.cpu_time_limit,
                "memory_limit": self.memory_limit_kb,
            } for case in chunk]}
            created = self._request("POST", "/submissions/batch?base64_encoded=true", payload)
            tokens = [row.get("token") for row in created or [] if isinstance(row, dict)]
            if len(tokens) != len(chunk) or not all(tokens):
                raise ExecutionUnavailable("Judge0 did not accept the submissions.")
            results.extend(self._collect(tokens, chunk))
        return results

    def _collect(self, tokens: list[str], cases: list[dict]) -> list[ExecutionResult]:
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
            status = _status(int((row.get("status") or {}).get("id") or 0))
            stderr = _unb64(row.get("compile_output")) if status == "compile_error" else _unb64(row.get("stderr"))
            out.append(ExecutionResult(
                case_id=str(case.get("id")), status=status, stdout=_unb64(row.get("stdout")), stderr=stderr,
                time=float(row["time"]) if row.get("time") not in (None, "") else None,
                memory=int(row["memory"]) if row.get("memory") not in (None, "") else None,
            ))
        return out


def outputs_match(actual: str, expected: str) -> bool:
    """Compare program output ignoring trailing whitespace and line-ending style."""
    def norm(text: str) -> list[str]:
        lines = [line.rstrip() for line in str(text or "").replace("\r\n", "\n").split("\n")]
        while lines and not lines[-1]:
            lines.pop()
        return lines
    return norm(actual) == norm(expected)
