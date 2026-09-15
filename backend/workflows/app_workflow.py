# Backend file purpose: Workflow orchestration logic for app.
from __future__ import annotations

from typing import Any

import database as db
from services.candidate_service import candidate_profile_payload, candidates_payload, repair_all_candidates
from services.interview_service import (
    assert_slot_available,
    day_window,
    default_from_email,
    generate_interview_email,
    interview_window,
    schedule_context,
    send_email,
)
from services.jd_service import create_jd_from_upload, jd_details_payload, jd_summary_list_payload
from services.report_service import dashboard_payload, jd_performance_payload, reports_payload
from orchestration.tracing import trace_end, trace_start
from security.policy import ToolRequest
from tools.tool_gateway import gateway


# Purpose: Implements the agent backend behavior.
def _agent(name: str, fn, *args, **kwargs):
    """Wrap a service/database call with agent-style trace start/end logging."""
    trace_start("agent", name)
    result = fn(*args, **kwargs)
    trace_end("agent", name)
    return result


# Purpose: Implements the require user backend behavior.
def _require_user(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate that the routed task includes the authenticated user context."""
    user = payload.get("_user") if isinstance(payload.get("_user"), dict) else {}
    if not user:
        raise ValueError("Unauthorized")
    return user


def _run_controlled_tool(payload: dict[str, Any], user: dict[str, Any], tool: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a controlled mutation through the policy-enforced gateway."""
    result = gateway.execute(
        ToolRequest(
            tool=tool,
            params=params,
            user=user,
            confirmed=payload.get("confirmed") is True,
            run_id=str(payload.get("_run_id") or ""),
        )
    )
    return {"success": True, **(result.data or {})} if result.success else result.to_dict()


# Purpose: Implements the blocked slots backend behavior.
def _blocked_slots(user: dict[str, Any], date: str) -> dict[str, Any]:
    """Return interview slots already blocked for the current recruiter on one date."""
    if not date:
        raise ValueError("date is required")
    start, end = day_window(date)
    rows = db.get_interviews_for_recruiter_on_day(int(user["id"]), start, end)
    return {
        "blocked_slots": [
            {
                "start": str(row.get("interview_start") or "")[11:16],
                "end": str(row.get("interview_end") or "")[11:16],
                "candidate_name": row.get("candidate_name") or "",
                "job_role": row.get("job_role") or "",
            }
            for row in rows
        ]
    }


# Purpose: Implements the generate interview email backend behavior.
def _generate_interview_email(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Generate an interview invitation email draft for a selected candidate."""
    candidate_id = int(data.get("candidate_id") or 0)
    jd_id = int(data.get("jd_id") or 0)
    interview_date = str(data.get("interview_date") or "").strip()
    interview_time = str(data.get("interview_time") or "").strip()
    interview_start, interview_end = interview_window(interview_date, interview_time)
    assert_slot_available(int(user["id"]), interview_start, interview_end)
    ctx = schedule_context(candidate_id, jd_id)
    from_email = default_from_email(user)
    email = generate_interview_email(ctx["candidate"], ctx["jd"], interview_date, interview_time, from_email)
    return {
        "from_email": from_email,
        "to_email": ctx["candidate"].get("email") or "",
        "subject": email["subject"],
        "body": email["body"],
        "interview_start": interview_start.isoformat(),
        "interview_end": interview_end.isoformat(),
    }


# Purpose: Implements the schedule interview backend behavior.
def _schedule_interview(user: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Send an interview email and persist the scheduled interview record."""
    candidate_id = int(data.get("candidate_id") or 0)
    jd_id = int(data.get("jd_id") or 0)
    interview_date = str(data.get("interview_date") or "").strip()
    interview_time = str(data.get("interview_time") or "").strip()
    subject = str(data.get("subject") or "").strip()
    body = str(data.get("body") or "").strip()
    if not subject or not body:
        raise ValueError("Email subject and body are required.")

    interview_start, interview_end = interview_window(interview_date, interview_time)
    assert_slot_available(int(user["id"]), interview_start, interview_end)
    ctx = schedule_context(candidate_id, jd_id)
    from_email = default_from_email(user)
    to_email = ctx["candidate"].get("email") or ""
    send_email(to_email, subject, body, from_email)
    interview_id = db.create_interview(
        {
            "candidate_id": candidate_id,
            "candidate_email": to_email,
            "candidate_name": ctx["candidate"].get("name") or "",
            "jd_id": jd_id,
            "job_role": ctx["jd"].get("title") or "",
            "recruiter_id": int(user["id"]),
            "recruiter_email": user.get("email") or "",
            "interview_start": interview_start,
            "interview_end": interview_end,
            "from_email": from_email,
            "to_email": to_email,
            "email_subject": subject,
            "email_body": body,
            "status": "Scheduled",
        }
    )
    db.update_candidate(candidate_id, {"hiring_stage": "Interview Scheduled"})
    db.log_audit(
        "Interview Scheduled",
        user.get("username") or "",
        f"Scheduled interview for '{ctx['candidate'].get('name') or to_email}' against JD '{ctx['jd'].get('title') or jd_id}'.",
        jd_id,
    )
    return {"success": True, "interview_id": interview_id}


# Purpose: Runs the app workflow workflow or agent step.
def run_app_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch non-screening LangGraph routes to their existing app service functions."""
    name = "Application API Orchestrator"
    task = str(payload.get("task_type") or "").strip().lower()
    trace_start("orchestrator", name, task)
    user = payload.get("_user") if isinstance(payload.get("_user"), dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

    if task == "dashboard":
        result = _agent("Dashboard Agent", dashboard_payload)
    elif task == "dashboard_team":
        result = _agent("Team Metrics Agent", lambda: [])
    elif task == "jd_performance":
        result = _agent("JD Performance Agent", jd_performance_payload)
    elif task == "reports":
        result = _agent("Reports Agent", reports_payload)
    elif task == "jd_list":
        result = _agent("JD List Agent", jd_summary_list_payload)
    elif task == "jd_details":
        result = _agent("JD Details Agent", jd_details_payload, int(payload.get("jd_id") or 0))
        if not result:
            raise ValueError("JD not found")
    elif task == "jd_create":
        upload = payload.get("file")
        if not upload:
            raise ValueError("No file uploaded")
        user = _require_user(payload)
        result = _agent(
            "JD Creation Agent",
            _run_controlled_tool,
            payload,
            user,
            "jd.create",
            {
                "file": upload,
                "upload_folder": str(payload.get("upload_folder") or ""),
                "client_id": int(payload.get("client_id") or 0) or None,
                "required_candidate_count": int(payload.get("required_candidate_count") or 0),
            },
        )
    elif task == "jd_delete":
        user = _require_user(payload)
        jd_id = int(payload.get("jd_id") or 0)
        result = _agent("JD Delete Agent", _run_controlled_tool, payload, user, "jd.delete", {"jd_id": jd_id})
    elif task == "candidate_list":
        result = _agent("Candidate List Agent", candidates_payload, data or None)
    elif task == "client_list":
        result = _agent("Client List Agent", lambda: {"clients": db.get_all_clients()})
    elif task == "client_details":
        result = _agent("Client Details Agent", db.get_client_details, int(payload.get("client_id") or 0))
        if not result:
            raise ValueError("Client not found")
    elif task == "candidate_profile":
        result = _agent("Candidate Profile Agent", candidate_profile_payload, int(payload.get("candidate_id") or 0))
        if not result:
            raise ValueError("Candidate not found")
        result = {"candidate": result["candidate"], "timeline": result.get("timeline") or []}
    elif task == "candidate_delete":
        user = _require_user(payload)
        result = _agent(
            "Candidate Delete Agent",
            _run_controlled_tool,
            payload,
            user,
            "candidate.delete",
            {"candidate_id": int(payload.get("candidate_id") or 0)},
        )
    elif task == "candidate_repair":
        user = _require_user(payload)
        result = _agent(
            "Candidate Repair Agent",
            _run_controlled_tool,
            payload,
            user,
            "candidate.repair",
            {"row_count": len(db.get_all_candidates())},
        )
    elif task == "profile_get":
        user = _require_user(payload)
        result = {"user": user}
    elif task == "profile_update":
        user = _require_user(payload)
        result = _agent("Profile Agent", _run_controlled_tool, payload, user, "profile.update", data)
    elif task == "interview_defaults":
        user = _require_user(payload)
        result = {"from_email": _agent("Interview Defaults Agent", default_from_email, user)}
    elif task == "interview_blocked_slots":
        user = _require_user(payload)
        result = _agent("Interview Availability Agent", _blocked_slots, user, str(payload.get("date") or ""))
    elif task == "interview_generate_email":
        user = _require_user(payload)
        result = _agent("Interview Email Agent", _generate_interview_email, user, data)
    elif task == "interview_schedule":
        user = _require_user(payload)
        result = _agent("Interview Scheduling Agent", _run_controlled_tool, payload, user, "interview.schedule", data)
    else:
        raise ValueError(f"Unsupported application task_type: {task}")

    trace_end("orchestrator", name, task)
    return result
