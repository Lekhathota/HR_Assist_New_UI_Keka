# Backend file purpose: Tool/helper functions used by agents and workflows for matching.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import database as db
from app.llm_extraction import compare_resume_with_jd
from services.matching_service import _build_screening_summary, _fallback_candidate_name
from services.role_category_service import auto_categorize_candidate


# Purpose: Compares profile and returns the match result.
def compare_profile(jd_json: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Run the resume-vs-JD comparison helper for one normalized profile."""
    return compare_resume_with_jd(jd_json, profile.get("resume_json") or {})


# Purpose: Implements the persist match backend behavior.
def persist_match(jd_id: int, jd_row: dict[str, Any], profile: dict[str, Any], screening: dict[str, Any]) -> dict[str, Any]:
    """Save a screening result to candidate/comparison storage and return the API result row."""
    resume_json = profile.get("resume_json") or {}
    summary = _build_screening_summary(screening, resume_json)
    status = screening.get("status", "Rejected")
    match_score = int(screening.get("match_score") or 0)
    rejection_reason = screening.get("failure_reason", "")
    jd_title = jd_row.get("title") or "Unknown"

    if profile.get("source") in {"existing", "bench"}:
        candidate = profile.get("candidate") or {}
        candidate_id = int(profile.get("candidate_id") or 0)
        applied_roles = candidate.get("applied_roles") or []
        if jd_title not in applied_roles:
            db.update_candidate(candidate_id, {"applied_roles": [jd_title, *applied_roles]})
        name = candidate.get("name") or "Unknown"
    else:
        filename = str(profile.get("filename") or "")
        name = _fallback_candidate_name(resume_json, filename)
        candidate_id = db.create_candidate(
            {
                "name": name,
                "email": resume_json.get("email", ""),
                "phone": resume_json.get("phone", ""),
                "applied_roles": [jd_title],
                "structured_data": resume_json,
                "match_score": match_score,
                "status": status,
                "screening_summary": summary,
                "rejection_reason": rejection_reason,
                "hiring_stage": "Screening" if status == "Selected" else "Rejected",
                "resume_file": filename,
                "jd_id": jd_id,
                "source_vendor_id": profile.get("source_vendor_id"),
                "source_vendor_name": profile.get("source_vendor_name") or "",
            }
        )

    candidate_source = profile.get("candidate_source") or ("bench" if profile.get("source") == "bench" else "vendor" if profile.get("source_vendor_id") else "direct")
    db.upsert_comparison(
        {
            "jd_id": jd_id,
            "candidate_id": candidate_id,
            "match_score": match_score,
            "status": status,
            "strengths": screening.get("strengths") or [],
            "gaps": screening.get("gaps") or [],
            "recommendation": screening.get("recommendation", ""),
            "failure_reason": rejection_reason,
            "comparison_date": datetime.now(timezone.utc),
            "candidate_source": candidate_source,
            "selection_status": "vendor_submitted" if candidate_source == "vendor" else "",
            "qualification_status": "qualified" if status == "Selected" else "unqualified",
        }
    )
    auto_categorize_candidate(
        candidate_id,
        {"jd_titles": [jd_title], "screening_notes": summary, "recruiter_feedback": screening.get("recommendation", "")},
    )

    row = {
        "id": candidate_id,
        "name": name,
        "match_score": match_score,
        "status": status,
        "screening_summary": summary,
        "strengths": screening.get("strengths") or [],
        "gaps": screening.get("gaps") or [],
        "recommendation": screening.get("recommendation", ""),
    }
    if status != "Selected":
        row["rejection_reason"] = rejection_reason or "Does not meet requirements"
    return row
