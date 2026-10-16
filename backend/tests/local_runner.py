"""TEST-ONLY execution backend: runs programs in a local subprocess.

It implements the same interface as assessment.code_execution.judge0.Judge0Runner so the
grading, verification and scoring code can be exercised against real program behaviour
(compile errors, crashes, timeouts, oversized output) in CI without a Judge0 server.

It provides no isolation and must never be used by the application: production
always executes code in the Judge0 sandbox (JUDGE0_URL).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from assessment.code_execution.judge0 import ExecutionLimits, ExecutionResult

_SOURCES = {"python": "main.py", "javascript": "main.js", "java": "Main.java"}


def available(language: str) -> bool:
    return {"python": True, "javascript": bool(shutil.which("node")),
            "java": bool(shutil.which("javac") and shutil.which("java"))}.get(language, False)


class LocalSubprocessRunner:
    def __init__(self):
        self.calls: list[tuple[str, int]] = []

    def default_limits(self) -> ExecutionLimits:
        return ExecutionLimits()

    def run(self, language: str, source: str, cases: list[dict], limits: ExecutionLimits | None = None) -> list[ExecutionResult]:
        limits = limits or self.default_limits()
        self.calls.append((language, len(cases)))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / _SOURCES[language]
            path.write_text(source, encoding="utf-8")
            if language == "java":
                built = subprocess.run(["javac", path.name], cwd=folder, capture_output=True, text=True, timeout=60)
                if built.returncode != 0:
                    return [ExecutionResult(str(c.get("id")), "compile_error", stderr=built.stderr[-1500:]) for c in cases]
                command = ["java", "-Xss8m", "-cp", folder, "Main"]
            elif language == "javascript":
                command = ["node", str(path)]
            else:
                command = [sys.executable, "-I", str(path)]
            return [self._run_case(command, folder, case, limits) for case in cases]

    @staticmethod
    def _run_case(command, folder, case, limits: ExecutionLimits) -> ExecutionResult:
        case_id = str(case.get("id"))
        try:
            done = subprocess.run(command, cwd=folder, input=str(case.get("input") or ""), capture_output=True,
                                  text=True, timeout=limits.cpu_time_limit + 1.5)
        except subprocess.TimeoutExpired:
            return ExecutionResult(case_id, "time_limit", stderr="Time limit exceeded")
        if len(done.stdout.encode("utf-8")) > limits.max_output_kb * 1024:
            return ExecutionResult(case_id, "output_limit", stderr="Output limit exceeded")
        if done.returncode != 0:
            return ExecutionResult(case_id, "runtime_error", stdout=done.stdout[:4000], stderr=done.stderr[-1500:])
        return ExecutionResult(case_id, "ok", stdout=done.stdout[:4000], stderr=done.stderr[-1500:])
