# Backend file purpose: Tool/helper functions used by agents and workflows for recruiter.
from __future__ import annotations

from typing import Any

import database as db
from services.candidate_service import candidates_payload


# Purpose: Implements the tokens backend behavior.
def _tokens(value: str) -> set[str]:
    """Return searchable word tokens for loose candidate/JD matching."""
    return {part for part in "".join(ch.lower() if ch.isalnum() else " " for ch in str(value or "")).split() if len(part) > 2}


# Purpose: Implements the resolve candidate id backend behavior.
def _resolve_candidate_id(message: str) -> int | None:
    """Find a candidate id from a name mentioned in the chat message."""
    message_tokens = _tokens(message)
    if not message_tokens:
        return None
    best_id = None
    best_score = 0
    for row in db.get_all_candidates():
        name_tokens = _tokens(row.get("name") or "")
        if not name_tokens:
            continue
        overlap = len(message_tokens.intersection(name_tokens))
        if overlap > best_score:
            best_id = int(row["id"])
            best_score = overlap
    return best_id if best_score else None


# Purpose: Implements the resolve jd id backend behavior.
def _resolve_jd_id(message: str) -> int | None:
    """Find a JD id from a title mentioned in the chat message."""
    message_tokens = _tokens(message)
    if not message_tokens:
        return None
    best_id = None
    best_score = 0
    for row in db.get_jds_summary_list():
        title_tokens = _tokens(row.get("title") or "")
        overlap = len(message_tokens.intersection(title_tokens))
        if overlap > best_score:
            best_id = int(row["id"])
            best_score = overlap
    return best_id if best_score else None


# Purpose: Implements the recruiter context backend behavior.
def recruiter_context(message: str, jd_id: int | None = None, candidate_id: int | None = None) -> dict[str, Any]:
    """Collect JD, candidate, and comparison data needed to answer a recruiter chat message."""
    context: dict[str, Any] = {"message": message}
    all_candidates = db.get_all_candidates()
    all_jds = db.get_jds_summary_list()
    resolved_jd_id = _resolve_jd_id(message)
    resolved_candidate_id = _resolve_candidate_id(message)
    jd_id = resolved_jd_id or jd_id
    candidate_id = resolved_candidate_id or candidate_id

    if jd_id:
        context["jd"] = db.get_jd_by_id(int(jd_id), include_raw_text=False)
        context["candidates"] = candidates_payload({"jd_id": int(jd_id)})
        context["comparisons"] = db.get_comparisons(jd_id=int(jd_id))
    if candidate_id:
        candidate = db.get_candidate_by_id(int(candidate_id))
        context["candidate_profile"] = {"candidate": candidate} if candidate else {}
        context["candidate_comparisons"] = db.get_comparisons(candidate_id=int(candidate_id))
    if not jd_id and not candidate_id:
        applications = len(all_candidates)
        selected = sum(1 for row in all_candidates if row.get("status") == "Selected")
        rejected = sum(1 for row in all_candidates if row.get("status") == "Rejected")
        avg_match = int(sum(int(row.get("match_score") or 0) for row in all_candidates) / applications) if applications else 0
        context["dashboard"] = {
            "total_jobs": len(all_jds),
            "total_candidates": applications,
            "selected_candidates": selected,
            "rejected_candidates": rejected,
            "avg_match_score": avg_match,
            "selection_rate": int((selected / applications) * 100) if applications else 0,
        }
        context["recent_jds"] = all_jds[:5]
        context["recent_candidates"] = all_candidates[:5]
    context["all_candidates"] = all_candidates
    context["all_jds"] = all_jds
    return context
