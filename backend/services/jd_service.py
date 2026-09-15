# Backend file purpose: Service-layer business logic for jd features.
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

import database as db
from app.llm_extraction import extract_jd_json
from app.text_extractor import extract_text
from app.utils import clean_jd_text
from services.candidate_service import candidates_payload
from services.role_category_service import categorize_jd

ALLOWED_EXTENSIONS = {"pdf", "docx"}


def unique_upload_filename(filename: str) -> str:
    safe = secure_filename(filename or "") or "upload"
    path = Path(safe)
    stem = path.stem[:80] or "upload"
    suffix = path.suffix.lower()
    return f"{stem}-{uuid4().hex[:10]}{suffix}"


# Purpose: Implements the allowed file backend behavior.
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _apply_jd_category(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row or {})
    current = {
        "job_category": row.get("job_category") or "",
        "secondary_categories": row.get("secondary_categories") or [],
        "matched_keywords": row.get("matched_keywords") or [],
        "categorization_source": row.get("categorization_source") or "",
        "confidence_score": int(row.get("confidence_score") or 0),
        "categorized_date": row.get("categorized_date"),
        "category_reason": row.get("category_reason") or "",
        "sub_tags": row.get("sub_tags") or [],
    }
    payload = categorize_jd(row)
    comparable_keys = [key for key in payload if key != "categorized_date"]
    if current.get("categorized_date") and all(current.get(key) == payload.get(key) for key in comparable_keys):
        payload["categorized_date"] = current.get("categorized_date")
    row.update(payload)
    if row.get("id") and any(current.get(key) != payload.get(key) for key in payload):
        db.update_jd(int(row["id"]), payload)
    return row


# Purpose: Creates jd from upload records or payloads.
def create_jd_from_upload(file: FileStorage, upload_folder: str, client_id: int | None = None, required_candidate_count: int | None = None) -> dict[str, Any]:
    filename = unique_upload_filename(file.filename or "")
    os.makedirs(upload_folder, exist_ok=True)
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)

    raw_text = extract_text(filepath)
    cleaned = clean_jd_text(raw_text)
    jd_json = extract_jd_json(cleaned)
    title = jd_json.get("job_title") or filename
    department = jd_json.get("industry") or "Unknown"
    skills = jd_json.get("required_skills") or []
    responsibilities = jd_json.get("responsibilities") or []
    experience = jd_json.get("experience_range") or ""
    location = jd_json.get("location") or ""

    new_id = db.create_jd(
        {
            "title": title,
            "department": department,
            "location": location,
            "experience_required": experience,
            "skills": skills,
            "responsibilities": responsibilities,
            "structured_data": jd_json,
            "raw_text": cleaned,
            "file_name": filename,
            "status": "Active",
            "client_id": client_id,
            "required_candidate_count": required_candidate_count,
        }
    )
    jd = _apply_jd_category(db.get_jd_by_id(new_id, include_raw_text=True) or {})
    jd.pop("raw_text", None)
    return {"id": new_id, "jd": jd, "title": title}


# Purpose: Creates jd from path records or payloads.
def create_jd_from_path(filename: str, filepath: str, client_id: int | None = None, required_candidate_count: int | None = None) -> dict[str, Any]:
    """
    Celery-safe JD creation from an already saved file path.
    """
    raw_text = extract_text(filepath)
    cleaned = clean_jd_text(raw_text)
    jd_json = extract_jd_json(cleaned)
    title = jd_json.get("job_title") or filename
    department = jd_json.get("industry") or "Unknown"
    skills = jd_json.get("required_skills") or []
    responsibilities = jd_json.get("responsibilities") or []
    experience = jd_json.get("experience_range") or ""
    location = jd_json.get("location") or ""

    new_id = db.create_jd(
        {
            "title": title,
            "department": department,
            "location": location,
            "experience_required": experience,
            "skills": skills,
            "responsibilities": responsibilities,
            "structured_data": jd_json,
            "raw_text": cleaned,
            "file_name": filename,
            "status": "Active",
            "client_id": client_id,
            "required_candidate_count": required_candidate_count,
        }
    )
    jd = _apply_jd_category(db.get_jd_by_id(new_id, include_raw_text=True) or {})
    jd.pop("raw_text", None)
    return {"id": new_id, "jd": jd, "title": title}


# Purpose: Implements the candidate counts for jd backend behavior.
def _candidate_counts_for_jd(jd_id: int) -> dict[str, int]:
    return db.jd_candidate_counts(jd_id)


# Purpose: Implements the jd summary list payload backend behavior.
def jd_summary_list_payload() -> list[dict[str, Any]]:
    out = []
    for row in db.get_all_jds():
        row = _apply_jd_category(db.get_jd_by_id(int(row["id"]), include_raw_text=True) or row)
        created = row.get("created_at") or ""
        out.append(
            {
                "id": row["id"],
                "title": row.get("title", ""),
                "department": row.get("department", ""),
                "location": row.get("location", ""),
                "experience": row.get("experience_required", ""),
                "skills": row.get("skills") or [],
                "status": row.get("status", "Active"),
                "client_id": row.get("client_id"),
                "client_account_id": row.get("client_account_id", ""),
                "client_name": row.get("client_name", ""),
                "job_category": row.get("job_category") or "Others",
                "secondary_categories": row.get("secondary_categories") or [],
                "matched_keywords": row.get("matched_keywords") or [],
                "categorization_source": row.get("categorization_source") or "",
                "confidence_score": row.get("confidence_score") or 0,
                "categorized_date": row.get("categorized_date") or "",
                "category_reason": row.get("category_reason") or "",
                "sub_tags": row.get("sub_tags") or [],
                "required_candidate_count": row.get("required_candidate_count"),
                "workflow_status": row.get("workflow_status") or "ACTIVE",
                "bench_matched_count": int(row.get("bench_matched_count") or 0),
                "bench_analyzed_count": int(row.get("bench_analyzed_count") or 0),
                "bench_qualified_count": int(row.get("bench_qualified_count") or 0),
                "selected_bench_count": int(row.get("selected_bench_count") or 0),
                "accepted_vendor_count": int(row.get("accepted_vendor_count") or 0),
                "remaining_vendor_requirement": int(row.get("remaining_vendor_requirement") or 0),
                "created": created,
                "created_date": str(created)[:10],
                "file": row.get("file_name", ""),
                **_candidate_counts_for_jd(int(row["id"])),
            }
        )
    return out


# Purpose: Implements the jd details payload backend behavior.
def jd_details_payload(jd_id: int) -> dict[str, Any] | None:
    row = db.get_jd_by_id(jd_id, include_raw_text=True)
    if not row:
        return None
    row = _apply_jd_category(row)
    row.pop("raw_text", None)
    row["experience"] = row.get("experience") or row.get("experience_required") or ""
    row["file"] = row.get("file") or row.get("file_name") or ""
    created = row.get("created") or row.get("created_at") or ""
    row["created"] = created
    row["created_date"] = row.get("created_date") or str(created)[:10]
    candidates = candidates_payload({"jd_id": jd_id})
    selected = [row for row in candidates if row.get("status") == "Selected"]
    rejected = [row for row in candidates if row.get("status") == "Rejected"]
    counts = {"selected_count": len(selected), "rejected_count": len(rejected), "total_resumes": len(candidates)}
    return {"jd": {**row, **counts}, "selected": selected, "rejected": rejected}
