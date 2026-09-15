# Backend file purpose: Agent role logic for interview processing.
from __future__ import annotations

from typing import Any

import openai

from agents.openai_config import configure_agent_openai
from app.llm_extraction import llm_call
from orchestration.tracing import trace_end, trace_start


AGENT_NAME = "Interview Question Agent"
PROMPT_VERSION = "interview-agent-v1"
OPENAI_MODEL = configure_agent_openai(openai)
INTERVIEW_AGENT_SYSTEM_PROMPT = """
You are an Interview Question Agent for an HR recruitment platform.
Your job is to generate interview questions tailored to a candidate and job.
Use the JD skills, candidate experience, candidate gaps, and role seniority.
Include technical questions, role-fit questions, and follow-up probes.
Do not invent company policy, interviewer names, meeting links, or candidate facts.
"""


# Purpose: Builds interview question prompt used by downstream code.
def build_interview_question_prompt(candidate: dict[str, Any], jd: dict[str, Any]) -> str:
    """Create a prompt for generating role-specific interview questions for one candidate and JD."""
    return f"""
{INTERVIEW_AGENT_SYSTEM_PROMPT}

Job:
{jd.get('title') or ''}

Skills:
{', '.join(str(x) for x in (jd.get('skills') or [])[:10])}

Candidate:
{candidate.get('name') or ''}

Candidate Profile:
{candidate.get('structured_data') or {}}

Return 8 concise numbered interview questions only.
"""


# Purpose: Runs the interview question agent workflow or agent step.
def run_interview_question_agent(candidate: dict[str, Any], jd: dict[str, Any]) -> dict[str, Any]:
    """Call the LLM helper to generate interview questions and return them as a list."""
    name = AGENT_NAME
    trace_start("agent", name, jd.get("title") or "interview questions")
    prompt = build_interview_question_prompt(candidate, jd)
    raw = llm_call(prompt, temperature=0.4)
    questions = [line.strip(" -") for line in raw.splitlines() if line.strip()]
    trace_end("agent", name, f"questions={len(questions)}")
    return {"questions": questions, "agent_prompt": {"name": name, "version": PROMPT_VERSION, "model": OPENAI_MODEL}}
