# Backend file purpose: Workflow orchestration logic for screening.
from __future__ import annotations

from typing import Any

from agents.jd_agent import run_jd_agent
from agents.matching_agent import run_matching_agent
from agents.ranking_agent import run_ranking_agent
from agents.resume_agent import run_resume_agent
from agents.summary_agent import run_summary_agent
from orchestration.tracing import trace_end, trace_start


# Purpose: Runs the screening workflow workflow or agent step.
def run_screening_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the legacy sequential screening pipeline outside the LangGraph node wrapper."""
    name = "Screening Workflow Orchestrator"
    jd_id = int(payload.get("jd_id") or 0)
    trace_start("orchestrator", name, f"jd_id={jd_id}")
    if not jd_id:
        raise ValueError("jd_id is required for screening.")

    jd_context = run_jd_agent(jd_id)
    resume_context = run_resume_agent(payload.get("candidate_ids") or [], payload.get("resume_items") or [])
    match_context = run_matching_agent(
        jd_id,
        jd_context["jd_row"],
        jd_context["jd_json"],
        resume_context["profiles"],
    )
    ranked_context = run_ranking_agent(match_context["results"])
    errors = [*resume_context["errors"], *match_context["errors"]]
    summary = run_summary_agent(jd_context["jd_row"], ranked_context["ranked_candidates"], errors)

    result = {
        "status": "completed",
        **ranked_context,
        "summary": summary,
        "errors": errors,
    }
    trace_end("orchestrator", name, f"ranked={len(ranked_context['ranked_candidates'])}")
    return result
