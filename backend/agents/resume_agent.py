# Backend file purpose: Agent role logic for resume processing.
from __future__ import annotations

from typing import Any

import openai

from agents.openai_config import configure_agent_openai
from orchestration.tracing import trace_end, trace_start
from tools.resume_tools import profile_from_existing_candidate, profile_from_resume_path


AGENT_NAME = "Resume Agent"
PROMPT_VERSION = "resume-agent-v1"
OPENAI_MODEL = configure_agent_openai(openai)
RESUME_AGENT_SYSTEM_PROMPT = """
You are a Resume Extraction Agent for an HR recruitment platform.
Your job is to extract factual candidate information from resumes.
Extract identity, contact details, skills, total experience, education, work history,
projects, certifications, current role, location, and links.
Do not score, reject, rank, or judge the candidate.
Do not invent missing details. Use empty strings or empty lists when evidence is missing.
Return structured JSON only when asked to generate output.
"""


# Purpose: Builds resume agent prompt used by downstream code.
def build_resume_agent_prompt(resume_text: str) -> str:
    """Create the resume extraction prompt that tells the Resume Agent what candidate fields to extract."""
    return f"""
{RESUME_AGENT_SYSTEM_PROMPT}

Resume Text:
{resume_text}

Return ONLY valid JSON with:
- candidate_name
- email
- phone
- linkedin_url
- location
- current_role
- total_experience_years
- skills
- technical_skills
- education
- work_experience
- projects
- certifications
"""


# Purpose: Runs the resume agent workflow or agent step.
def run_resume_agent(candidate_ids: list[str] | None = None, resume_items: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Convert selected existing candidates and uploaded resumes into normalized profile dictionaries."""
    name = AGENT_NAME
    trace_start("agent", name, f"existing={len(candidate_ids or [])}, uploads={len(resume_items or [])}")
    profiles: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for cid in candidate_ids or []:
        try:
            profile = profile_from_existing_candidate(int(cid))
            if profile:
                profiles.append(profile)
        except Exception as exc:
            errors.append({"candidate_id": str(cid), "error": str(exc)})

    for item in resume_items or []:
        try:
            profiles.append(profile_from_resume_path(str(item.get("path") or ""), str(item.get("filename") or ""), item))
        except Exception as exc:
            errors.append({"filename": str(item.get("filename") or ""), "error": str(exc)})

    trace_end("agent", name, f"profiles={len(profiles)}, errors={len(errors)}")
    return {"profiles": profiles, "errors": errors, "agent_prompt": {"name": name, "version": PROMPT_VERSION, "model": OPENAI_MODEL}}
