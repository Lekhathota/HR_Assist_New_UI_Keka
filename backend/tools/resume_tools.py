# Backend file purpose: Tool/helper functions used by agents and workflows for resume.
from __future__ import annotations

from typing import Any

import database as db
from app.llm_extraction import extract_resume_json
from app.text_extractor import extract_text
from app.utils import clean_resume_text
from services.candidate_service import normalize_candidate_record


# Purpose: Implements the profile from existing candidate backend behavior.
def profile_from_existing_candidate(candidate_id: int) -> dict[str, Any] | None:
    """Build a screening profile from a candidate already stored in the database."""
    candidate = db.get_candidate_by_id(int(candidate_id))
    if not candidate:
        return None
    candidate = normalize_candidate_record(candidate)
    resume_json = candidate.get("structured_data") if isinstance(candidate.get("structured_data"), dict) else {}
    is_bench = (
        str(candidate.get("worker_type") or "Internal").lower() == "internal"
        and str(candidate.get("bench_status") or "On Bench").lower() == "on bench"
    )
    return {
        "source": "bench" if is_bench else "existing",
        "candidate_source": "bench" if is_bench else "direct",
        "candidate_id": int(candidate_id),
        "candidate": candidate,
        "primary_category": candidate.get("primary_category") or "",
        "availability_status": candidate.get("availability_status") or "",
        "allocation_status": candidate.get("allocation_status") or "",
        "resume_json": resume_json,
    }


# Purpose: Implements the profile from resume path backend behavior.
def profile_from_resume_path(path: str, filename: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extract and normalize resume JSON from an uploaded resume file path."""
    metadata = metadata or {}
    raw_text = extract_text(path)
    resume_json = extract_resume_json(clean_resume_text(raw_text))
    resume_json = normalize_candidate_record({"structured_data": resume_json}, repair=False)["structured_data"]
    return {
        "source": "uploaded",
        "filename": filename,
        "path": path,
        "source_vendor_id": metadata.get("source_vendor_id"),
        "source_vendor_name": metadata.get("source_vendor_name") or "",
        "resume_json": resume_json,
    }
