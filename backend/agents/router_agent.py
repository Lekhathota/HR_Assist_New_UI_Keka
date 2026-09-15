# Backend file purpose: Agent role logic for router processing.
from __future__ import annotations

import json
import re
from typing import Any

from app.llm_extraction import llm_call
import database as db
from orchestration.tracing import trace_end, trace_start
from security.context_safety import detect_prompt_injection


AGENT_NAME = "LLM Router Agent"
PROMPT_VERSION = "router-agent-v1"
ALLOWED_ROUTES = {
    "screening",
    "chat",
    "jd",
    "candidate",
    "client",
    "interview",
    "dashboard",
    "reports",
    "unsupported",
}
MIN_ROUTER_CONFIDENCE = 0.45

JD_TASKS = {"jd_list", "jd_details", "jd_create", "jd_delete"}
CANDIDATE_TASKS = {"candidate_list", "candidate_profile", "candidate_delete", "candidate_repair"}
CLIENT_TASKS = {"client_list", "client_details"}
INTERVIEW_TASKS = {"interview_defaults", "interview_blocked_slots", "interview_generate_email", "interview_schedule"}
DASHBOARD_TASKS = {"dashboard", "dashboard_team", "jd_performance"}
REPORT_TASKS = {"reports"}
CHAT_TASKS = {"chat", "chat_action", "message", "msg", "recruiter_chat"}
SCREENING_TASKS = {"screening", "agentic_screening"}
KNOWN_TASKS = (
    SCREENING_TASKS
    | CHAT_TASKS
    | JD_TASKS
    | CANDIDATE_TASKS
    | CLIENT_TASKS
    | INTERVIEW_TASKS
    | DASHBOARD_TASKS
    | REPORT_TASKS
    | {"profile_get", "profile_update"}
)


# Purpose: Implements the deterministic route backend behavior.
def deterministic_route(payload: dict[str, Any]) -> dict[str, Any]:
    """Choose a safe route from known task_type/message fields without using an LLM."""
    task = str(payload.get("task_type") or payload.get("type") or "").strip().lower()
    route = "unsupported"
    reason = "No supported task signal was found."

    if task in SCREENING_TASKS:
        route = "screening"
        reason = "task_type maps to screening."
    elif task in CHAT_TASKS or payload.get("message") or payload.get("msg"):
        route = "chat"
        reason = "message payload maps to recruiter chat."
    elif task in JD_TASKS:
        route = "jd"
        reason = "task_type maps to JD agent path."
    elif task in CANDIDATE_TASKS or task in {"profile_get", "profile_update"}:
        route = "candidate"
        reason = "task_type maps to candidate/profile agent path."
    elif task in CLIENT_TASKS:
        route = "client"
        reason = "task_type maps to client account agent path."
    elif task in INTERVIEW_TASKS:
        route = "interview"
        reason = "task_type maps to interview agent path."
    elif task in DASHBOARD_TASKS:
        route = "dashboard"
        reason = "task_type maps to dashboard agent path."
    elif task in REPORT_TASKS:
        route = "reports"
        reason = "task_type maps to reports agent path."
    elif payload.get("jd_id"):
        route = "screening"
        reason = "jd_id without another task maps to screening."

    return {"route": route, "confidence": 1.0 if route != "unsupported" else 0.0, "reason": reason, "source": "deterministic"}


# Purpose: Implements the router prompt backend behavior.
def _router_prompt(payload: dict[str, Any]) -> str:
    """Build the strict JSON prompt used when the router needs LLM-based intent classification."""
    task = str(payload.get("task_type") or payload.get("type") or "").strip()
    message = str(payload.get("message") or payload.get("msg") or "").strip()
    hints = {
        "task_type": task,
        "has_message": bool(message),
        "message": message[:500],
        "has_jd_id": bool(payload.get("jd_id")),
        "has_candidate_id": bool(payload.get("candidate_id")),
        "has_resume_items": bool(payload.get("resume_items")),
        "has_file": bool(payload.get("file")),
        "data_keys": sorted((payload.get("data") or {}).keys()) if isinstance(payload.get("data"), dict) else [],
    }
    return f"""
You are the LLM Router Agent for an HR recruitment platform.
Choose exactly one route for the request.

Allowed routes:
- screening: compare resumes/candidates against a job description
- chat: answer recruiter questions
- jd: job description list/details/create/delete
- candidate: candidate list/profile/delete/repair or user profile tasks
- client: client account list/details
- interview: interview defaults, availability, email generation, or scheduling
- dashboard: dashboard metrics or JD performance
- reports: reports page data
- unsupported: request cannot be handled

Request hints:
{json.dumps(hints, ensure_ascii=True)}

Return ONLY strict JSON with:
{{
  "route": "screening|chat|jd|candidate|client|interview|dashboard|reports|unsupported",
  "confidence": 0.0,
  "reason": "short explanation"
}}
"""


# Purpose: Parses router json into structured values.
def _parse_router_json(raw: str) -> dict[str, Any]:
    """Parse router JSON, including recovery when the model wraps JSON in extra text."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw or "")
        if not match:
            return {}
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return {}


# Purpose: Implements the route request backend behavior.
def route_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the final route decision, preferring deterministic known-task routing over LLM routing."""
    name = AGENT_NAME
    fallback = deterministic_route(payload)
    trace_start("agent", name, f"fallback={fallback['route']}")
    explicit_task = str(payload.get("task_type") or payload.get("type") or "").strip().lower()

    if explicit_task in KNOWN_TASKS:
        trace_end("agent", name, f"{fallback['route']} via explicit task")
        return fallback

    message = str(payload.get("message") or payload.get("msg") or "")
    blocked, marker = detect_prompt_injection(message)
    if blocked:
        db.log_audit(
            "Prompt Injection Blocked",
            (payload.get("_user") or {}).get("username") if isinstance(payload.get("_user"), dict) else "",
            f"Router prompt blocked by marker: {marker}",
            int(payload["jd_id"]) if payload.get("jd_id") else None,
            run_id=str(payload.get("_run_id") or ""),
            tool="router",
            outcome="blocked",
            params={"marker": marker},
        )
        trace_end("agent", name, "blocked prompt injection")
        return {**fallback, "source": "blocked", "reason": "Prompt injection attempt blocked."}

    raw = llm_call(_router_prompt(payload), temperature=0.0)
    decision = _parse_router_json(raw)
    route = str(decision.get("route") or "").strip().lower()
    try:
        confidence = float(decision.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    if route not in ALLOWED_ROUTES or confidence < MIN_ROUTER_CONFIDENCE:
        result = {**fallback, "llm_route": route or "", "llm_confidence": confidence}
        trace_end("agent", name, f"{result['route']} via fallback")
        return result

    result = {
        "route": route,
        "confidence": confidence,
        "reason": str(decision.get("reason") or "LLM route selected.").strip(),
        "source": "llm",
        "fallback_route": fallback["route"],
    }
    trace_end("agent", name, f"{route} via llm")
    return result
