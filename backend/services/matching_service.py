# Backend file purpose: Service-layer business logic for matching features.
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

import database as db
from app.llm_extraction import compare_resume_with_jd, extract_resume_json
from app.text_extractor import extract_text
from app.utils import clean_resume_text
from services.candidate_service import normalize_candidate_record
from services.jd_service import allowed_file, unique_upload_filename
from services.role_category_service import auto_categorize_candidate


# Purpose: Implements the fallback candidate name backend behavior.
def _fallback_candidate_name(resume_json: dict, filename: str) -> str:
    name = str(resume_json.get("candidate_name") or "").strip()
    if name:
        return name
    stem = (filename or "").rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()
    return stem.title() if stem else "Unknown Candidate"


# Purpose: Builds screening summary used by downstream code.
def _build_screening_summary(screening: dict, resume_json: dict) -> str:
    strengths = screening.get("strengths") or []
    gaps = screening.get("gaps") or []
    recommendation = screening.get("recommendation") or "N/A"
    summary = (
        f"Match Score: {screening.get('match_score', 0)}%\nStatus: {screening.get('status', 'Rejected')}\n\n"
        f"Strengths: {', '.join(strengths)}\n"
        f"Gaps: {', '.join(gaps)}\n"
        f"Recommendation: {recommendation}"
    )
    if strengths or gaps:
        return summary

    # Fallback summary if model/regex returns minimal comparison detail
    skills = resume_json.get("skills") or []
    exp_years = resume_json.get("total_experience_years")
    fallback_bits = []
    if isinstance(exp_years, (int, float)):
        fallback_bits.append(f"Experience: {exp_years} years")
    if skills:
        fallback_bits.append(f"Skills: {', '.join(skills[:8])}")
    fallback_suffix = "\n".join(fallback_bits) if fallback_bits else "Resume extracted with limited details."
    return f"{summary}\n\n{fallback_suffix}"


# Purpose: Normalizes d jd payload into the app's expected format.
def _normalized_jd_payload(jd_row: dict) -> dict:
    jd_json = jd_row.get("structured_data") or {}
    if isinstance(jd_json, str):
        jd_json = json.loads(jd_json)
    if not isinstance(jd_json, dict):
        jd_json = {}

    skills = jd_json.get("required_skills") or jd_row.get("skills") or []
    jd_json.setdefault("job_title", jd_row.get("title", "Unknown"))
    jd_json.setdefault("required_skills", skills)
    jd_json.setdefault("preferred_skills", [])
    jd_json.setdefault("experience_range", jd_row.get("experience_required") or jd_row.get("experience") or "")
    jd_json.setdefault("experience_required", jd_json.get("experience_range", ""))
    jd_json.setdefault("education_required", "")
    jd_json.setdefault("responsibilities", jd_row.get("responsibilities") or [])
    return jd_json


# Purpose: Implements the screen existing candidate backend behavior.
def _screen_existing_candidate(jd_id: int, jd_row: dict, jd_json: dict, candidate_id: int) -> dict | None:
    cand = db.get_candidate_by_id(candidate_id)
    if not cand:
        return None

    cand = normalize_candidate_record(cand)
    resume_json = cand.get("structured_data") or {}
    if isinstance(resume_json, str):
        resume_json = json.loads(resume_json)
    if not isinstance(resume_json, dict):
        resume_json = {}

    screening = compare_resume_with_jd(jd_json, resume_json)
    summary = _build_screening_summary(screening, resume_json)
    status = screening.get("status", "Rejected")
    match_score = int(screening.get("match_score") or 0)
    rejection_reason = screening.get("failure_reason", "")
    hiring_stage = "Screening" if status == "Selected" else "Rejected"
    applied_roles = cand.get("applied_roles") or []
    jd_title = jd_row.get("title", "Unknown")
    if jd_title not in applied_roles:
        applied_roles = [jd_title, *applied_roles]

    if applied_roles != (cand.get("applied_roles") or []):
        db.update_candidate(candidate_id, {"applied_roles": applied_roles})
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
        }
    )
    auto_categorize_candidate(
        candidate_id,
        {"jd_titles": [jd_title], "screening_notes": summary, "recruiter_feedback": screening.get("recommendation", "")},
    )

    row = {
        "id": candidate_id,
        "name": cand.get("name", "Unknown"),
        "match_score": match_score,
        "status": status,
        "screening_summary": summary,
    }
    if status != "Selected":
        row["rejection_reason"] = rejection_reason or "Does not meet requirements"
    return row


# Purpose: Runs the matching workflow or agent step.
def run_matching(jd_id: int, candidate_ids: list[str], resume_files: list[FileStorage], upload_folder: str) -> dict[str, Any]:
    jd_row = db.get_jd_by_id(jd_id, include_raw_text=True)
    if not jd_row:
        return {"error": "JD not found"}

    jd_json = _normalized_jd_payload(jd_row)

    selected_results: list[dict] = []
    rejected_results: list[dict] = []
    # Multipart parts with a filename (what the user selected to upload)
    resume_parts_received = 0
    # PDF/DOCX only — others are skipped without failing the run
    resume_parts_skipped_bad_ext = 0
    uploaded_count = 0
    processed_count = 0

    for cid in candidate_ids:
        row = _screen_existing_candidate(jd_id, jd_row, jd_json, int(cid))
        if not row:
            continue
        (selected_results if row.get("status") == "Selected" else rejected_results).append(row)
        processed_count += 1

    for rf in resume_files:
        if not rf or not rf.filename:
            continue
        resume_parts_received += 1
        if not allowed_file(rf.filename):
            resume_parts_skipped_bad_ext += 1
            continue
        uploaded_count += 1
        os.makedirs(upload_folder, exist_ok=True)
        filename = unique_upload_filename(rf.filename or "")
        resume_path = os.path.join(upload_folder, filename)
        rf.save(resume_path)
        raw_text = extract_text(resume_path)
        cleaned = clean_resume_text(raw_text)
        resume_json = extract_resume_json(cleaned)
        resume_json = normalize_candidate_record({"structured_data": resume_json}, repair=False)["structured_data"]
        screening = compare_resume_with_jd(jd_json, resume_json)
        summary = _build_screening_summary(screening, resume_json)
        name = _fallback_candidate_name(resume_json, rf.filename or filename)
        status = screening.get("status", "Rejected")
        hiring_stage = "Screening" if status == "Selected" else "Rejected"
        new_cid = db.create_candidate(
            {
                "name": name,
                "email": resume_json.get("email", ""),
                "phone": resume_json.get("phone", ""),
                "applied_roles": [jd_row.get("title", "Unknown")],
                "structured_data": resume_json,
                "match_score": int(screening.get("match_score") or 0),
                "status": status,
                "screening_summary": summary,
                "rejection_reason": screening.get("failure_reason", ""),
                "hiring_stage": hiring_stage,
                "resume_file": filename,
                "jd_id": jd_id,
            }
        )
        db.upsert_comparison(
            {
                "jd_id": jd_id,
                "candidate_id": new_cid,
                "match_score": int(screening.get("match_score") or 0),
                "status": status,
                "strengths": screening.get("strengths") or [],
                "gaps": screening.get("gaps") or [],
                "recommendation": screening.get("recommendation", ""),
                "failure_reason": screening.get("failure_reason", ""),
                "comparison_date": datetime.now(timezone.utc),
            }
        )
        auto_categorize_candidate(
            new_cid,
            {
                "jd_titles": [jd_row.get("title", "Unknown")],
                "screening_notes": summary,
                "recruiter_feedback": screening.get("recommendation", ""),
            },
        )
        result = {
            "id": new_cid,
            "name": name,
            "match_score": screening.get("match_score", 0),
            "status": status,
            "screening_summary": summary,
        }
        if status != "Selected":
            result["rejection_reason"] = screening.get("failure_reason", "Does not meet requirements")
        (selected_results if status == "Selected" else rejected_results).append(result)
        processed_count += 1

    return {
        "jd_row": jd_row,
        "selected_results": selected_results,
        "rejected_results": rejected_results,
        "resume_parts_received": resume_parts_received,
        "resume_parts_skipped_bad_ext": resume_parts_skipped_bad_ext,
        "uploaded_count": uploaded_count,
        "processed_count": processed_count,
    }


# Purpose: Runs the matching from paths workflow or agent step.
def run_matching_from_paths(
    jd_id: int,
    candidate_ids: list[str],
    resume_items: list[dict[str, str]],
) -> dict[str, Any]:
    """
    Celery-safe variant that reads already-saved files from disk.
    resume_items expects: [{"path": "...", "filename": "..."}]
    """
    jd_row = db.get_jd_by_id(jd_id, include_raw_text=True)
    if not jd_row:
        return {"error": "JD not found"}

    jd_json = _normalized_jd_payload(jd_row)

    selected_results: list[dict] = []
    rejected_results: list[dict] = []
    resume_parts_received = 0
    resume_parts_skipped_bad_ext = 0
    uploaded_count = 0
    processed_count = 0

    for cid in candidate_ids:
        row = _screen_existing_candidate(jd_id, jd_row, jd_json, int(cid))
        if not row:
            continue
        (selected_results if row.get("status") == "Selected" else rejected_results).append(row)
        processed_count += 1

    for item in resume_items:
        filename = str(item.get("filename") or "").strip()
        resume_path = str(item.get("path") or "").strip()
        if not filename or not resume_path:
            continue
        resume_parts_received += 1
        if not allowed_file(filename):
            resume_parts_skipped_bad_ext += 1
            continue
        if not os.path.exists(resume_path):
            continue

        uploaded_count += 1
        raw_text = extract_text(resume_path)
        cleaned = clean_resume_text(raw_text)
        resume_json = extract_resume_json(cleaned)
        resume_json = normalize_candidate_record({"structured_data": resume_json}, repair=False)["structured_data"]
        screening = compare_resume_with_jd(jd_json, resume_json)
        summary = _build_screening_summary(screening, resume_json)
        safe_name = secure_filename(filename)
        name = _fallback_candidate_name(resume_json, safe_name)
        status = screening.get("status", "Rejected")
        hiring_stage = "Screening" if status == "Selected" else "Rejected"
        new_cid = db.create_candidate(
            {
                "name": name,
                "email": resume_json.get("email", ""),
                "phone": resume_json.get("phone", ""),
                "applied_roles": [jd_row.get("title", "Unknown")],
                "structured_data": resume_json,
                "match_score": int(screening.get("match_score") or 0),
                "status": status,
                "screening_summary": summary,
                "rejection_reason": screening.get("failure_reason", ""),
                "hiring_stage": hiring_stage,
                "resume_file": safe_name,
                "jd_id": jd_id,
                "source_vendor_id": item.get("source_vendor_id"),
                "source_vendor_name": item.get("source_vendor_name") or "",
            }
        )
        db.upsert_comparison(
            {
                "jd_id": jd_id,
                "candidate_id": new_cid,
                "match_score": int(screening.get("match_score") or 0),
                "status": status,
                "strengths": screening.get("strengths") or [],
                "gaps": screening.get("gaps") or [],
                "recommendation": screening.get("recommendation", ""),
                "failure_reason": screening.get("failure_reason", ""),
                "comparison_date": datetime.now(timezone.utc),
            }
        )
        auto_categorize_candidate(
            new_cid,
            {
                "jd_titles": [jd_row.get("title", "Unknown")],
                "screening_notes": summary,
                "recruiter_feedback": screening.get("recommendation", ""),
            },
        )
        result = {
            "id": new_cid,
            "name": name,
            "match_score": screening.get("match_score", 0),
            "status": status,
            "screening_summary": summary,
        }
        if status != "Selected":
            result["rejection_reason"] = screening.get("failure_reason", "Does not meet requirements")
        (selected_results if status == "Selected" else rejected_results).append(result)
        processed_count += 1

    return {
        "jd_row": jd_row,
        "selected_results": selected_results,
        "rejected_results": rejected_results,
        "resume_parts_received": resume_parts_received,
        "resume_parts_skipped_bad_ext": resume_parts_skipped_bad_ext,
        "uploaded_count": uploaded_count,
        "processed_count": processed_count,
    }
