# Backend file purpose: Agent role logic for jd processing.
from __future__ import annotations

from typing import Any

import openai

from agents.openai_config import configure_agent_openai
from orchestration.tracing import trace_end, trace_start
from tools.jd_tools import load_jd_context


AGENT_NAME = "JD Agent"
PROMPT_VERSION = "jd-agent-v1"
OPENAI_MODEL = configure_agent_openai(openai)
JD_AGENT_SYSTEM_PROMPT = """
You are a JD Intelligence Agent for an HR recruitment platform.
Your job is to read job description data and extract factual hiring requirements.
Focus on job title, required skills, preferred skills, experience range, seniority,
education, responsibilities, location, domain, and hidden requirements.
Do not invent requirements that are not supported by the JD.
Return structured JSON only when asked to generate output.
"""


# Purpose: Builds jd agent prompt used by downstream code.
def build_jd_agent_prompt(jd_text: str | dict[str, Any]) -> str:
    """Create the JD extraction prompt that describes what facts the JD Agent should identify."""
    return f"""
{JD_AGENT_SYSTEM_PROMPT}

JD Input:
{jd_text}

Return ONLY valid JSON with:
- job_title
- required_skills
- preferred_skills
- experience_range
- seniority
- education_required
- responsibilities
- location
- domain
- hidden_requirements
"""


# Purpose: Runs the jd agent workflow or agent step.
def run_jd_agent(jd_id: int) -> dict[str, Any]:
    """Load a JD by id and return normalized JD context for the screening graph."""
    name = AGENT_NAME
    trace_start("agent", name, f"jd_id={jd_id}")
    context = load_jd_context(jd_id)
    context["agent_prompt"] = {"name": name, "version": PROMPT_VERSION, "model": OPENAI_MODEL}
    trace_end("agent", name, context["jd_row"].get("title") or "JD loaded")
    return context
