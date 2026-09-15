# Backend file purpose: Workflow orchestration logic for recruiter chat.
from __future__ import annotations

from typing import Any

from agents.recruiter_agent import execute_recruiter_action, run_recruiter_agent
from orchestration.tracing import trace_end, trace_start


# Purpose: Runs the recruiter chat workflow workflow or agent step.
def run_recruiter_chat_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the chat branch by answering a message or executing a supported chat action."""
    name = "Recruiter Chat Orchestrator"
    task = str(payload.get("task_type") or "chat").strip().lower()
    message = str(payload.get("message") or payload.get("msg") or "").strip()
    trace_start("orchestrator", name, message[:80] or task)
    if task == "chat_action":
        result = execute_recruiter_action(payload, payload.get("_user") if isinstance(payload.get("_user"), dict) else {})
        trace_end("orchestrator", name, "action completed")
        return {"status": "completed", **result}
    if not message:
        raise ValueError("message is required for recruiter chat.")
    result = run_recruiter_agent(
        message,
        jd_id=int(payload["jd_id"]) if payload.get("jd_id") else None,
        candidate_id=int(payload["candidate_id"]) if payload.get("candidate_id") else None,
    )
    trace_end("orchestrator", name, "chat completed")
    return {"status": "completed", **result}
