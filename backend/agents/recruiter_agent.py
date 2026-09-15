# Backend file purpose: Agent role logic for recruiter processing.
from __future__ import annotations

import json
import re
from typing import Any

import openai

import database as db
from app.llm_extraction import llm_call
from agents.openai_config import configure_agent_openai
from orchestration.tracing import trace_end, trace_start
from security.context_safety import detect_prompt_injection, guard_context_window
from security.policy import ToolRequest
from services.candidate_service import normalize_candidate_record
from services.interview_service import (
    assert_slot_available,
    day_window,
    default_from_email,
    generate_interview_email,
    interview_window,
    schedule_context,
    send_email,
)
from tools.recruiter_tools import recruiter_context
from tools.tool_gateway import gateway


AGENT_NAME = "Recruiter Assistant Agent"
PROMPT_VERSION = "recruiter-agent-v1"
OPENAI_MODEL = configure_agent_openai(openai)
RECRUITER_AGENT_SYSTEM_PROMPT = """
You are a Recruiter Assistant Agent for an HR recruitment platform.
Your job is to answer recruiter questions using only available JD, candidate,
comparison, screening, and interview context.
Explain selection, rejection, ranking, gaps, and next steps clearly.
If context is missing, say what is missing instead of guessing.
Do not invent candidate facts, company policy, salary data, or interview outcomes.
Return concise recruiter-facing answers. Never invent facts. If the context does
not contain the answer, say what is missing and suggest what the recruiter can
open or ask next.
"""


# Purpose: Builds recruiter agent prompt used by downstream code.
def build_recruiter_agent_prompt(message: str, context: dict[str, Any]) -> str:
    """Create the grounded recruiter-assistant prompt from the user question and safe HR context."""
    return f"""
{RECRUITER_AGENT_SYSTEM_PROMPT}

Recruiter Message:
{message}

Available Context:
{context}

Return ONLY valid JSON with this shape:
{{
  "answer": "concise grounded answer",
  "suggested_questions": ["question 1", "question 2"],
  "actions": [
    {{
      "type": "open_candidate|open_jd|show_top_candidates|explain_candidate|check_interview_availability|generate_interview_email|schedule_interview|repair_candidate_profile",
      "label": "short button label",
      "params": {{}},
      "requires_confirmation": false
    }}
  ]
}}

Only include actions that are directly supported by IDs present in context.
Use requires_confirmation=true for schedule_interview and repair_candidate_profile.
"""


# Purpose: Parses json into structured values.
def _parse_json(raw: str) -> dict[str, Any]:
    """Parse an LLM JSON response, including responses that contain extra text around the JSON."""
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw or "")
        if not match:
            return {}
        try:
            parsed = json.loads(match.group())
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}


# Purpose: Implements the candidate from context backend behavior.
def _candidate_from_context(context: dict[str, Any]) -> dict[str, Any]:
    """Extract the candidate dictionary from a recruiter context payload if it is present."""
    profile = context.get("candidate_profile") if isinstance(context.get("candidate_profile"), dict) else {}
    return profile.get("candidate") if isinstance(profile.get("candidate"), dict) else {}


# Purpose: Implements the ids from context backend behavior.
def _ids_from_context(context: dict[str, Any], jd_id: int | None, candidate_id: int | None) -> tuple[int | None, int | None]:
    """Fill missing JD/candidate ids from resolved context records."""
    jd = context.get("jd") if isinstance(context.get("jd"), dict) else {}
    candidate = _candidate_from_context(context)
    resolved_jd = jd_id or (int(jd["id"]) if jd.get("id") else None)
    resolved_candidate = candidate_id or (int(candidate["id"]) if candidate.get("id") else None)
    return resolved_jd, resolved_candidate


# Purpose: Implements the actions for context backend behavior.
def _actions_for_context(context: dict[str, Any], jd_id: int | None, candidate_id: int | None) -> list[dict[str, Any]]:
    """Build safe UI actions based on the currently available JD and candidate context."""
    actions: list[dict[str, Any]] = []
    if jd_id:
        actions.extend(
            [
                {"type": "open_jd", "label": "Open JD", "params": {"jd_id": jd_id}, "requires_confirmation": False},
                {"type": "show_top_candidates", "label": "Top Candidates", "params": {"jd_id": jd_id}, "requires_confirmation": False},
            ]
        )
    if candidate_id:
        actions.extend(
            [
                {"type": "open_candidate", "label": "Open Candidate", "params": {"candidate_id": candidate_id}, "requires_confirmation": False},
                {"type": "explain_candidate", "label": "Explain Candidate", "params": {"candidate_id": candidate_id, **({"jd_id": jd_id} if jd_id else {})}, "requires_confirmation": False},
                {"type": "repair_candidate_profile", "label": "Repair Profile", "params": {"candidate_id": candidate_id}, "requires_confirmation": True},
            ]
        )
    candidate = _candidate_from_context(context)
    if jd_id and candidate_id and candidate.get("status") == "Selected":
        actions.append(
            {
                "type": "generate_interview_email",
                "label": "Draft Interview Email",
                "params": {"jd_id": jd_id, "candidate_id": candidate_id},
                "requires_confirmation": False,
            }
        )
    return actions[:5]


# Purpose: Implements the interview datetime from message backend behavior.
def _interview_datetime_from_message(message: str) -> tuple[str, str]:
    """Detect a simple YYYY-MM-DD and HH:MM interview time from a recruiter message."""
    date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", message or "")
    time_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", message or "")
    return (
        date_match.group(1) if date_match else "",
        f"{int(time_match.group(1)):02d}:{time_match.group(2)}" if time_match else "",
    )


# Purpose: Implements the message actions backend behavior.
def _message_actions(message: str, jd_id: int | None, candidate_id: int | None) -> list[dict[str, Any]]:
    """Infer immediate assistant actions from explicit wording in the recruiter message."""
    lowered = (message or "").lower()
    if not (jd_id and candidate_id):
        return []
    interview_date, interview_time = _interview_datetime_from_message(message)
    if ("draft" in lowered or "email" in lowered or "schedule" in lowered) and interview_date and interview_time:
        return [
            {
                "type": "generate_interview_email",
                "label": "Draft Email",
                "params": {
                    "jd_id": jd_id,
                    "candidate_id": candidate_id,
                    "interview_date": interview_date,
                    "interview_time": interview_time,
                },
                "requires_confirmation": False,
            }
        ]
    if "availability" in lowered and interview_date:
        return [
            {
                "type": "check_interview_availability",
                "label": "Check Availability",
                "params": {"interview_date": interview_date},
                "requires_confirmation": False,
            }
        ]
    return []


# Purpose: Implements the dashboard answer backend behavior.
def _dashboard_answer(message: str, context: dict[str, Any]) -> str:
    """Answer common general dashboard questions without requiring an LLM call."""
    lowered = (message or "").lower()
    metrics = context.get("dashboard") if isinstance(context.get("dashboard"), dict) else {}
    all_jds = context.get("all_jds") if isinstance(context.get("all_jds"), list) else []
    all_candidates = context.get("all_candidates") if isinstance(context.get("all_candidates"), list) else []
    recent_candidates = context.get("recent_candidates") if isinstance(context.get("recent_candidates"), list) else []
    selected = [row for row in all_candidates if row.get("status") == "Selected"]
    rejected = [row for row in all_candidates if row.get("status") == "Rejected"]

    if "what can i ask" in lowered or "help" in lowered:
        return (
            "You can ask about dashboard metrics, active jobs, recent candidates, top candidates for a JD, "
            "why a candidate was selected or rejected, and interview availability. For sharper answers, open a JD or candidate profile first."
        )
    if "insight" in lowered or "summary" in lowered or "dashboard" in lowered:
        return (
            f"Current dashboard snapshot: {metrics.get('total_jobs', len(all_jds))} total jobs, "
            f"{metrics.get('total_candidates', len(all_candidates))} candidates, "
            f"{metrics.get('selected_candidates', len(selected))} selected, "
            f"{metrics.get('rejected_candidates', len(rejected))} rejected, and "
            f"{metrics.get('avg_match_score', 0)}% average match score."
        )
    if "screening" in lowered or "result" in lowered:
        return (
            "Use screening results by reviewing selected candidates first, then checking each candidate's strengths, gaps, match score, "
            "and hiring stage. Rejected candidates should be reviewed when the score is close to the threshold or the JD skills were updated."
        )
    if "job" in lowered or "jd" in lowered:
        active = [row for row in all_jds if str(row.get("status") or "").lower() == "active"]
        if not active:
            return "I could not find active JDs yet. Create or upload a JD before running screening."
        top = sorted(active, key=lambda row: int(row.get("total_resumes") or 0), reverse=True)[:3]
        parts = [f"{row.get('title')} ({row.get('total_resumes', 0)} resumes)" for row in top]
        return f"I found {len(active)} active JD(s). Most active: " + "; ".join(parts) + "."
    if "candidate" in lowered or "talent" in lowered:
        if not all_candidates:
            return "I could not find candidates yet. Upload resumes or run screening to create candidate records."
        recent = ", ".join(row.get("name") or "Unknown" for row in recent_candidates[:3])
        return f"I found {len(all_candidates)} candidate(s): {len(selected)} selected and {len(rejected)} rejected. Recent candidates: {recent or 'none'}."
    return ""


# Purpose: Implements the fallback answer backend behavior.
def _fallback_answer(message: str, context: dict[str, Any], jd_id: int | None, candidate_id: int | None) -> str:
    """Return a deterministic grounded answer when the LLM response is unavailable or incomplete."""
    candidates = context.get("candidates") or []
    comparisons = context.get("comparisons") or context.get("candidate_comparisons") or []
    candidate = _candidate_from_context(context)
    if candidate:
        return (
            f"{candidate.get('name') or 'This candidate'} has {candidate.get('match_score', 0)}% match score, "
            f"status {candidate.get('status') or 'Unknown'}, and current stage {candidate.get('hiring_stage') or 'Unknown'}."
        )
    if jd_id and candidates:
        ranked = sorted(candidates, key=lambda row: int(row.get("match_score") or 0), reverse=True)
        top = ranked[0]
        return f"Top candidate is {top.get('name') or 'Unknown'} with {top.get('match_score', 0)}% match score. I found {len(ranked)} candidate(s) for this JD."
    if comparisons:
        return f"I found {len(comparisons)} comparison record(s). Add a candidate_id or jd_id for a sharper explanation."
    dashboard_response = _dashboard_answer(message, context)
    if dashboard_response:
        return dashboard_response
    return (
        "I could not find a matching JD or candidate for that message. Try asking about dashboard metrics, jobs, candidates, "
        "or open a specific JD/candidate page for detailed answers."
    )


# Purpose: Implements the safe context summary backend behavior.
def _safe_context_summary(context: dict[str, Any]) -> dict[str, Any]:
    """Reduce raw recruiter context into a compact, safe structure for the LLM prompt."""
    jd = context.get("jd") if isinstance(context.get("jd"), dict) else {}
    candidate = _candidate_from_context(context)
    candidates = context.get("candidates") or []
    comparisons = context.get("comparisons") or context.get("candidate_comparisons") or []
    ranked = sorted(candidates, key=lambda row: int(row.get("match_score") or 0), reverse=True)[:8]
    dashboard = context.get("dashboard") if isinstance(context.get("dashboard"), dict) else {}
    all_jds = context.get("all_jds") if isinstance(context.get("all_jds"), list) else []
    all_candidates = context.get("all_candidates") if isinstance(context.get("all_candidates"), list) else []
    return {
        "jd": {k: jd.get(k) for k in ("id", "title", "department", "location", "experience", "skills") if jd.get(k) is not None},
        "candidate": {
            k: candidate.get(k)
            for k in ("id", "name", "email", "status", "hiring_stage", "match_score", "screening_summary", "rejection_reason")
            if candidate.get(k) is not None
        },
        "top_candidates": [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "status": row.get("status"),
                "match_score": row.get("match_score"),
                "hiring_stage": row.get("hiring_stage"),
            }
            for row in ranked
        ],
        "comparison_count": len(comparisons),
        "dashboard": {
            k: dashboard.get(k)
            for k in ("total_jobs", "total_candidates", "selected_candidates", "rejected_candidates", "avg_match_score", "selection_rate")
            if dashboard.get(k) is not None
        },
        "job_count": len(all_jds),
        "candidate_count": len(all_candidates),
    }


# Purpose: Runs the recruiter agent workflow or agent step.
def run_recruiter_agent(message: str, jd_id: int | None = None, candidate_id: int | None = None) -> dict[str, Any]:
    """Answer recruiter questions using JD/candidate context and return suggested follow-up actions."""
    name = AGENT_NAME
    trace_start("agent", name, message[:80])
    context = recruiter_context(message, jd_id=jd_id, candidate_id=candidate_id)
    jd_id, candidate_id = _ids_from_context(context, jd_id, candidate_id)
    context_summary = guard_context_window(_safe_context_summary(context))
    answer = _fallback_answer(message, context, jd_id, candidate_id)
    suggested_questions = [
        "Who are the top candidates?",
        "Explain this candidate",
        "What are the main gaps?",
    ]
    blocked, marker = detect_prompt_injection(message)
    if blocked:
        db.log_audit(
            "Prompt Injection Blocked",
            "",
            f"Recruiter chat prompt blocked by marker: {marker}",
            jd_id,
            tool="recruiter.chat",
            outcome="blocked",
            params={"candidate_id": candidate_id, "marker": marker},
        )
        answer = "I cannot follow instructions that try to bypass system, security, or approval rules. Please ask a recruiting question using the available JD or candidate context."
    else:
        try:
            raw = llm_call(build_recruiter_agent_prompt(message, context_summary), temperature=0.2)
            parsed = _parse_json(raw)
            if parsed.get("answer"):
                answer = str(parsed["answer"]).strip()
            if isinstance(parsed.get("suggested_questions"), list):
                suggested_questions = [str(x).strip() for x in parsed["suggested_questions"] if str(x).strip()][:4]
        except Exception:
            # Keep the deterministic grounded answer if the LLM helper is unavailable.
            pass

    actions = [*_message_actions(message, jd_id, candidate_id), *_actions_for_context(context, jd_id, candidate_id)][:5]
    candidates = context.get("candidates") or []
    comparisons = context.get("comparisons") or context.get("candidate_comparisons") or []

    trace_end("agent", name, "response ready")
    return {
        "answer": answer,
        "actions": actions,
        "suggested_questions": suggested_questions,
        "context": {"candidate_count": len(candidates), "comparison_count": len(comparisons)},
        "agent_prompt": {"name": name, "version": PROMPT_VERSION, "model": OPENAI_MODEL},
    }


# Purpose: Implements the require confirmed backend behavior.
def _require_confirmed(payload: dict[str, Any]) -> None:
    """Reject side-effecting assistant actions unless the frontend sent explicit confirmation."""
    if payload.get("confirmed") is not True:
        raise ValueError("This action requires explicit confirmation.")


# Purpose: Implements the top candidates backend behavior.
def _top_candidates(jd_id: int) -> dict[str, Any]:
    """Return a concise ranked summary of the strongest candidates for one JD."""
    rows = sorted(recruiter_context("", jd_id=jd_id).get("candidates") or [], key=lambda row: int(row.get("match_score") or 0), reverse=True)
    top = rows[:5]
    if not top:
        return {"answer": "I could not find candidates for this JD yet.", "actions": [], "suggested_questions": ["Run screening for this JD"]}
    lines = [f"{idx + 1}. {row.get('name') or 'Unknown'} - {row.get('match_score', 0)}% - {row.get('status') or 'Unknown'}" for idx, row in enumerate(top)]
    return {
        "answer": "Top candidates:\n" + "\n".join(lines),
        "actions": [
            {"type": "open_candidate", "label": f"Open {row.get('name') or 'Candidate'}", "params": {"candidate_id": row.get("id")}, "requires_confirmation": False}
            for row in top[:3]
            if row.get("id")
        ],
        "suggested_questions": ["Explain the best candidate", "What are the common gaps?"],
    }


# Purpose: Implements the explain candidate backend behavior.
def _explain_candidate(candidate_id: int, jd_id: int | None = None) -> dict[str, Any]:
    """Explain one candidate's score, status, strengths, gaps, and rejection reason when available."""
    context = recruiter_context("", jd_id=jd_id, candidate_id=candidate_id)
    candidate = _candidate_from_context(context)
    if not candidate:
        raise ValueError("Candidate not found.")
    summaries = candidate.get("screening_summaries") or []
    latest = summaries[0] if summaries else {}
    gaps = ", ".join(latest.get("gaps") or []) if isinstance(latest, dict) else ""
    strengths = ", ".join(latest.get("strengths") or []) if isinstance(latest, dict) else ""
    answer = (
        f"{candidate.get('name') or 'This candidate'} has {candidate.get('match_score', 0)}% match score and status "
        f"{candidate.get('status') or 'Unknown'}. "
        f"Summary: {candidate.get('screening_summary') or latest.get('summary') or 'No screening summary available.'}"
    )
    if strengths:
        answer += f" Strengths: {strengths}."
    if gaps:
        answer += f" Gaps: {gaps}."
    if candidate.get("rejection_reason"):
        answer += f" Rejection reason: {candidate['rejection_reason']}."
    return {
        "answer": answer,
        "actions": [{"type": "open_candidate", "label": "Open Candidate", "params": {"candidate_id": candidate_id}, "requires_confirmation": False}],
        "suggested_questions": ["Show applied roles", "Can this candidate be scheduled?"],
    }


# Purpose: Implements the blocked slots backend behavior.
def _blocked_slots(user: dict[str, Any], interview_date: str) -> dict[str, Any]:
    """Report the current recruiter's blocked interview slots for a given date."""
    if not user:
        raise ValueError("Unauthorized")
    if not interview_date:
        return {"answer": "Please provide an interview date in YYYY-MM-DD format.", "actions": [], "suggested_questions": ["Check availability for tomorrow"]}
    start, end = day_window(interview_date)
    rows = db.get_interviews_for_recruiter_on_day(int(user["id"]), start, end)
    if not rows:
        return {"answer": f"No blocked interview slots found for {interview_date}.", "actions": [], "suggested_questions": ["Draft interview email"]}
    slots = [f"{str(row.get('interview_start') or '')[11:16]}-{str(row.get('interview_end') or '')[11:16]} {row.get('candidate_name') or ''}".strip() for row in rows]
    return {"answer": f"Blocked slots for {interview_date}: " + ", ".join(slots), "actions": [], "suggested_questions": ["Pick another time"]}


# Purpose: Implements the generate email backend behavior.
def _generate_email(user: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Generate an interview email draft for a selected candidate and JD without sending it."""
    candidate_id = int(params.get("candidate_id") or 0)
    jd_id = int(params.get("jd_id") or 0)
    interview_date = str(params.get("interview_date") or "").strip()
    interview_time = str(params.get("interview_time") or "").strip()
    if not candidate_id or not jd_id:
        raise ValueError("candidate_id and jd_id are required.")
    if not interview_date or not interview_time:
        return {
            "answer": "Please provide interview_date and interview_time to draft the interview email.",
            "actions": [],
            "suggested_questions": ["Draft email for 2026-06-10 at 10:00"],
        }
    interview_start, interview_end = interview_window(interview_date, interview_time)
    if user:
        assert_slot_available(int(user["id"]), interview_start, interview_end)
    ctx = schedule_context(candidate_id, jd_id)
    from_email = default_from_email(user)
    email = generate_interview_email(ctx["candidate"], ctx["jd"], interview_date, interview_time, from_email)
    params = {
        "candidate_id": candidate_id,
        "jd_id": jd_id,
        "interview_date": interview_date,
        "interview_time": interview_time,
        "subject": email["subject"],
        "body": email["body"],
    }
    return {
        "answer": f"Draft email ready.\nSubject: {email['subject']}\n\n{email['body']}",
        "actions": [{"type": "schedule_interview", "label": "Send and Schedule", "params": params, "requires_confirmation": True}],
        "suggested_questions": ["Check availability", "Open candidate profile"],
    }


# Purpose: Implements the schedule interview backend behavior.
def _schedule_interview(user: dict[str, Any], params: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Send a confirmed interview email and create the interview record."""
    result = gateway.execute(
        ToolRequest(
            tool="interview.schedule",
            params=params,
            user=user or {},
            confirmed=payload.get("confirmed") is True,
            run_id=str(payload.get("_run_id") or ""),
        )
    )
    if result.requires_approval:
        return {"answer": result.approval_reason, "actions": [], "suggested_questions": ["Confirm and send the interview email"]}
    if not result.success:
        return {"answer": result.error or "Interview scheduling failed.", "actions": [], "suggested_questions": ["Check availability"]}
    return {"answer": "Interview email sent and interview scheduled.", **(result.data or {}), "actions": [], "suggested_questions": ["Check blocked slots"]}


# Purpose: Implements the repair candidate backend behavior.
def _repair_candidate(params: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Force re-extraction/normalization for one candidate after explicit confirmation."""
    candidate_id = int(params.get("candidate_id") or 0)
    result = gateway.execute(
        ToolRequest(
            tool="candidate.repair",
            params={"candidate_id": candidate_id},
            user=payload.get("_user") if isinstance(payload.get("_user"), dict) else {},
            confirmed=payload.get("confirmed") is True,
            run_id=str(payload.get("_run_id") or ""),
        )
    )
    if result.requires_approval:
        return {"answer": result.approval_reason, "actions": [], "suggested_questions": ["Confirm profile repair"]}
    if not result.success:
        return {"answer": result.error or "Candidate repair failed.", "actions": [], "suggested_questions": ["Open candidate profile"]}
    normalized = (result.data or {}).get("candidate") or {}
    return {
        "answer": f"Candidate profile repair completed for {normalized.get('name') or 'candidate'}.",
        "actions": [{"type": "open_candidate", "label": "Open Candidate", "params": {"candidate_id": candidate_id}, "requires_confirmation": False}],
        "suggested_questions": ["Explain this candidate"],
    }


# Purpose: Implements the execute recruiter action backend behavior.
def execute_recruiter_action(payload: dict[str, Any], user: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a supported recruiter assistant action and return a chat-compatible response."""
    action = str(payload.get("action") or "").strip()
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    trace_start("agent", AGENT_NAME, f"action={action}")
    if action == "open_jd":
        jd_id = int(params.get("jd_id") or payload.get("jd_id") or 0)
        result = {"answer": "Opening job description.", "actions": [{"type": "open_jd", "label": "Open JD", "params": {"jd_id": jd_id}, "requires_confirmation": False}], "suggested_questions": []}
    elif action == "open_candidate":
        candidate_id = int(params.get("candidate_id") or payload.get("candidate_id") or 0)
        result = {"answer": "Opening candidate profile.", "actions": [{"type": "open_candidate", "label": "Open Candidate", "params": {"candidate_id": candidate_id}, "requires_confirmation": False}], "suggested_questions": []}
    elif action == "show_top_candidates":
        result = _top_candidates(int(params.get("jd_id") or payload.get("jd_id") or 0))
    elif action == "explain_candidate":
        result = _explain_candidate(int(params.get("candidate_id") or payload.get("candidate_id") or 0), int(params.get("jd_id") or payload.get("jd_id") or 0) or None)
    elif action == "check_interview_availability":
        result = _blocked_slots(user or {}, str(params.get("interview_date") or payload.get("interview_date") or ""))
    elif action == "generate_interview_email":
        result = _generate_email(user or {}, params)
    elif action == "schedule_interview":
        result = _schedule_interview(user or {}, params, payload)
    elif action == "repair_candidate_profile":
        result = _repair_candidate(params, payload)
    else:
        raise ValueError(f"Unsupported chat action: {action}")
    trace_end("agent", AGENT_NAME, f"action={action}")
    return {"action": action, **result, "context": result.get("context") or {}}
