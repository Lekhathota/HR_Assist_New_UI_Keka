# Backend file purpose: Agent role logic for matching processing.
from __future__ import annotations

from typing import Any

import openai

from agents.openai_config import configure_agent_openai
from orchestration.tracing import trace_end, trace_start
from tools.matching_tools import compare_profile, persist_match


AGENT_NAME = "Matching Agent"
PROMPT_VERSION = "matching-agent-v1"
OPENAI_MODEL = configure_agent_openai(openai)
MATCHING_AGENT_SYSTEM_PROMPT = """
You are a Resume Matching Agent for an HR recruitment platform.
Your job is to compare one candidate profile against one job description.
Evaluate required skills, preferred skills, experience fit, domain fit, education,
project relevance, recency, and tool alignment.
Required skills and relevant experience matter more than optional skills.
Do not invent candidate experience or JD requirements.
Explain strengths and gaps with evidence from the provided data.
Return structured JSON only when asked to generate output.
"""


# Purpose: Builds matching agent prompt used by downstream code.
def build_matching_agent_prompt(jd_json: dict[str, Any], resume_json: dict[str, Any]) -> str:
    """Create the matching prompt that defines how a candidate should be scored against a JD."""
    return f"""
{MATCHING_AGENT_SYSTEM_PROMPT}

Job Description JSON:
{jd_json}

Candidate Resume JSON:
{resume_json}

Return ONLY valid JSON with:
- match_score: integer 0-100
- status: "Selected" or "Rejected"
- strengths: list of concise evidence-backed strengths
- gaps: list of concise evidence-backed gaps
- failure_reason: short reason when rejected
- recommendation: recruiter-facing explanation
"""


# Purpose: Runs the matching agent workflow or agent step.
def run_matching_agent(jd_id: int, jd_row: dict[str, Any], jd_json: dict[str, Any], profiles: list[dict[str, Any]]) -> dict[str, Any]:
    """Screen every profile against the JD and persist each comparison result."""
    name = AGENT_NAME
    trace_start("agent", name, f"profiles={len(profiles)}")
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for profile in profiles:
        try:
            screening = compare_profile(jd_json, profile)
            results.append(persist_match(jd_id, jd_row, profile, screening))
        except Exception as exc:
            label = str(profile.get("candidate_id") or profile.get("filename") or "unknown")
            errors.append({"profile": label, "error": str(exc)})
    trace_end("agent", name, f"matches={len(results)}, errors={len(errors)}")
    return {"results": results, "errors": errors, "agent_prompt": {"name": name, "version": PROMPT_VERSION, "model": OPENAI_MODEL}}
