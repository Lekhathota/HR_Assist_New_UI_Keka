# Backend file purpose: Agent role logic for summary processing.
from __future__ import annotations

from typing import Any

import openai

from agents.openai_config import configure_agent_openai
from orchestration.tracing import trace_end, trace_start


AGENT_NAME = "Screening Summary Agent"
PROMPT_VERSION = "summary-agent-v1"
OPENAI_MODEL = configure_agent_openai(openai)
SUMMARY_AGENT_SYSTEM_PROMPT = """
You are a Screening Summary Agent for an HR recruitment platform.
Your job is to turn screening and ranking results into a clear recruiter summary.
Explain how many candidates were screened, who the strongest candidates are,
why candidates were selected, and what gaps caused rejection.
Be concise, evidence-backed, and recruiter-friendly.
Do not invent missing facts or change candidate scores.
Return structured JSON only when asked to generate output.
"""


# Purpose: Builds summary agent prompt used by downstream code.
def build_summary_agent_prompt(jd_row: dict[str, Any], ranked_candidates: list[dict[str, Any]], errors: list[dict[str, Any]]) -> str:
    """Create the summary prompt that defines the recruiter-facing screening summary format."""
    return f"""
{SUMMARY_AGENT_SYSTEM_PROMPT}

Job Description:
{jd_row}

Ranked Candidates:
{ranked_candidates}

Processing Errors:
{errors}

Return ONLY valid JSON with:
- jd_title
- total_candidates
- selected_count
- rejected_count
- top_candidate
- key_strengths
- key_gaps
- message
"""


# Purpose: Runs the summary agent workflow or agent step.
def run_summary_agent(jd_row: dict[str, Any], ranked_candidates: list[dict[str, Any]], errors: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a concise screening summary from ranked candidates and processing errors."""
    name = AGENT_NAME
    trace_start("agent", name, f"candidates={len(ranked_candidates)}")
    selected = [row for row in ranked_candidates if row.get("status") == "Selected"]
    rejected = [row for row in ranked_candidates if row.get("status") != "Selected"]
    top = ranked_candidates[0] if ranked_candidates else None
    summary = {
        "jd_title": jd_row.get("title") or "",
        "total_candidates": len(ranked_candidates),
        "selected_count": len(selected),
        "rejected_count": len(rejected),
        "top_candidate": top,
        "message": (
            f"Screened {len(ranked_candidates)} candidate(s) for {jd_row.get('title') or 'this JD'}. "
            f"Selected {len(selected)} and rejected {len(rejected)}."
        ),
        "errors": errors,
        "agent_prompt": {"name": name, "version": PROMPT_VERSION, "model": OPENAI_MODEL},
    }
    trace_end("agent", name, summary["message"])
    return summary
