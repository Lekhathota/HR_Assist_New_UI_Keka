# Backend file purpose: Agent role logic for ranking processing.
from __future__ import annotations  # Allows modern type hints to be evaluated safely at runtime.

from typing import Any  # Used for dictionaries whose values can contain mixed JSON-like data.

import openai  # OpenAI client/module is configured so the agent metadata records the active model.

from agents.openai_config import configure_agent_openai  # Reads OpenAI model/key configuration for this agent.
from orchestration.tracing import trace_end, trace_start  # Emits lightweight start/end logs for graph observability.


AGENT_NAME = "Ranking Agent"  # Human-readable name shown in traces and response metadata.
PROMPT_VERSION = "ranking-agent-v1"  # Version label that helps explain which prompt design this agent uses.
OPENAI_MODEL = configure_agent_openai(openai)  # Configures OpenAI and stores the model name for response metadata.
# Role instruction used if this agent is later made LLM-driven.
RANKING_AGENT_SYSTEM_PROMPT = """
You are a Candidate Ranking Agent for an HR recruitment platform.
Your job is to compare already-screened candidates and rank them for recruiter review.
Use match score, required-skill coverage, relevant experience, gaps, risk flags,
and explanation quality as evidence.
Do not overwrite match scores. Do not invent candidate facts.
Prefer candidates with strong required-skill evidence and fewer critical gaps.
Return structured JSON only when asked to generate output.
"""


# Purpose: Builds ranking agent prompt used by downstream code.
def build_ranking_agent_prompt(results: list[dict[str, Any]]) -> str:
    """Create the ranking prompt that explains how screened candidates should be ordered."""
    return f"""
{RANKING_AGENT_SYSTEM_PROMPT}

Screened Candidate Results:
{results}

Return ONLY valid JSON with:
- ranked_candidate_ids
- top_candidate_id
- ranking_reasons
- risk_flags
- recruiter_recommendation
"""


# Purpose: Runs the ranking agent workflow or agent step.
def run_ranking_agent(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Sort screened candidates by match score and separate selected from rejected results."""
    name = AGENT_NAME  # Store the constant locally so tracing and metadata use the same value.
    trace_start("agent", name, f"results={len(results)}")  # Log how many candidates entered the ranking stage.
    ranked = sorted(  # Order candidates from strongest to weakest based on the existing match score.
        results,
        key=lambda row: int(row.get("match_score") or 0),  # Missing or blank scores are treated as zero.
        reverse=True,  # Highest score should appear first for recruiter review.
    )
    trace_end("agent", name, f"top_score={ranked[0].get('match_score') if ranked else 0}")  # Log the best score found.
    return {
        "ranked_candidates": ranked,  # Full ranked list returned to the API/frontend.
        "selected_results": [row for row in ranked if row.get("status") == "Selected"],  # Candidates above the selection threshold.
        "rejected_results": [row for row in ranked if row.get("status") != "Selected"],  # Candidates that did not pass screening.
        "agent_prompt": {"name": name, "version": PROMPT_VERSION, "model": OPENAI_MODEL},  # Metadata for explanation/debugging.
    }
