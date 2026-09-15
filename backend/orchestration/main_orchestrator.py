# Backend file purpose: LangGraph/orchestrator infrastructure for routing backend agent tasks.
from __future__ import annotations

from typing import Any

import database as db
from orchestration.hr_graph import run_hr_graph
from orchestration.tracing import new_run_id, trace_end, trace_start


# Purpose: Implements the task type backend behavior.
def _task_type(payload: dict[str, Any]) -> str:
    """Infer the high-level task name that should be recorded for this orchestrator run."""
    task = str(payload.get("task_type") or payload.get("type") or "").strip().lower()
    if task:
        return task
    if payload.get("msg") or payload.get("message"):
        return "chat"
    if payload.get("jd_id"):
        return "screening"
    return ""


# Purpose: Implements the safe input backend behavior.
def _safe_input(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove private user fields and uploaded file objects before saving run input metadata."""
    safe = {}
    for key, value in payload.items():
        if key.startswith("_") or key in {"resume_items", "file"}:
            continue
        safe[key] = value
    return safe


# Purpose: Runs the main orchestrator workflow or agent step.
def run_main_orchestrator(payload: dict[str, Any], username: str = "") -> dict[str, Any]:
    """Create an agent run record, invoke the LangGraph HR graph, and persist success/failure output."""
    name = "Main HR Orchestrator"
    task = _task_type(payload)
    run_id = new_run_id("hr")
    payload["_run_id"] = run_id
    trace_start("orchestrator", name, f"run_id={run_id}, task_type={task or 'unknown'}")
    db.create_agent_run(
        {
            "run_id": run_id,
            "task_type": task or "unknown",
            "status": "running",
            "username": username,
            "input": _safe_input(payload),
        }
    )
    try:
        result = run_hr_graph(payload, run_id=run_id, task_type=task or "unknown", username=username)
        db.update_agent_run(run_id, {"status": "completed", "output": result})
        trace_end("orchestrator", name, f"run_id={run_id}, status=completed")
        return result
    except Exception as exc:
        db.update_agent_run(run_id, {"status": "failed", "error": str(exc)})
        trace_end("orchestrator", name, f"run_id={run_id}, status=failed")
        raise
