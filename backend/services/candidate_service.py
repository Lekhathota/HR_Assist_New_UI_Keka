# Backend file purpose: Service-layer business logic for candidate features.
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import database as db
from app.regex_extractor import extract_resume_regex
from app.text_extractor import extract_text
from app.utils import clean_resume_text
from services.role_category_service import categorize_candidate


BACKEND_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BACKEND_DIR / "static" / "uploads"
SELECTION_MATCH_THRESHOLD = 75


_EDUCATION_FIELD_HINTS = {
    "computer science",
    "information technology",
    "software engineering",
    "electronics",
    "communication",
    "electrical",
    "mechanical",
    "civil",
    "data science",
    "artificial intelligence",
    "machine learning",
    "business administration",
    "commerce",
    "mathematics",
    "statistics",
    "physics",
    "chemistry",
}


# Purpose: Implements the experience years backend behavior.
def _experience_years(value: Any) -> float:
    try:
        years = float(value or 0)
    except Exception:
        return 0.0
    return 0.0 if years < 1 else round(years, 1)


# Purpose: Implements the match score backend behavior.
def _match_score(value: Any) -> int:
    try:
        return max(0, min(100, int(value or 0)))
    except Exception:
        return 0


# Purpose: Implements the status from score backend behavior.
def _status_from_score(score: Any) -> str:
    return "Selected" if _match_score(score) >= SELECTION_MATCH_THRESHOLD else "Rejected"


# Purpose: Cleans and normalizes education field values.
def _clean_education_field(value: Any) -> str:
    field = str(value or "").replace("\ufb01", "fi").replace("\ufb02", "fl").strip()
    if not field or field.lower() in {"not specified", "unknown", "n/a", "na", "none", "null"}:
        return ""
    field = " ".join(field.split()).strip(" .,-:;|")
    field = field.split(" from ")[0].split(" at ")[0].strip(" ,-")
    lowered = field.lower()
    if len(field) > 60 or len(field.split()) > 6:
        return ""
    if any(bad in lowered for bad in ("agile", "outcome", "environment", "project", "experience", "intern", "responsibil")):
        return ""
    if any(hint in lowered for hint in _EDUCATION_FIELD_HINTS):
        return field
    if lowered in {"cse", "cs", "it", "ece", "eee", "me", "ce", "ai", "ml", "bca", "mca", "mba"}:
        return field.upper()
    return ""


# Purpose: Cleans and normalizes institution name values.
def _clean_institution_name(value: Any) -> str:
    institution = " ".join(str(value or "").split()).strip(" .,-:;|")
    if not institution or institution.lower() in {"not specified", "unknown", "n/a", "na", "none", "null"}:
        return ""
    for sep in (" - ", " | "):
        institution = institution.split(sep)[0].strip()
    lowered = institution.lower()
    if len(institution) > 90 or len(institution.split()) > 10:
        return ""
    if any(bad in lowered for bad in ("agile", "outcome", "environment", "project", "experience", "intern", "responsibil")):
        return ""
    return institution


# Purpose: Normalizes structured data into the app's expected format.
def _normalize_structured_data(sd: Any) -> dict[str, Any]:
    data = sd if isinstance(sd, dict) else {}
    education = data.get("education")
    if isinstance(education, dict):
        edu = {
            "degree": education.get("degree") or "",
            "field": _clean_education_field(education.get("field")),
            "institution": _clean_institution_name(education.get("institution")),
            "graduation_year": education.get("graduation_year") or "",
        }
    else:
        # Fallback for malformed/legacy structures where education may be a string.
        edu_text = str(education or "").strip()
        edu = {
            "degree": edu_text,
            "field": "",
            "institution": "",
            "graduation_year": "",
        }
    data["education"] = edu

    work = data.get("work_experience")
    if not isinstance(work, list):
        data["work_experience"] = []
    else:
        normalized_work = []
        for x in work:
            if not isinstance(x, dict):
                continue
            normalized_work.append(
                {
                    "company": x.get("company") or "",
                    "position": x.get("position") or x.get("job_title") or x.get("designation") or x.get("role") or "",
                    "start_date": x.get("start_date") or "",
                    "end_date": x.get("end_date") or "",
                }
            )
        data["work_experience"] = normalized_work

    skills = data.get("skills")
    data["skills"] = skills if isinstance(skills, list) else []
    tech = data.get("technical_skills")
    data["technical_skills"] = tech if isinstance(tech, list) else []
    data["total_experience_years"] = _experience_years(data.get("total_experience_years"))
    return data


# Purpose: Implements the profile data looks incomplete backend behavior.
def _profile_data_looks_incomplete(sd: dict[str, Any]) -> bool:
    years = _experience_years(sd.get("total_experience_years"))
    work = sd.get("work_experience") if isinstance(sd.get("work_experience"), list) else []
    has_present_role = any(str(row.get("end_date") or "").lower() == "present" for row in work if isinstance(row, dict))
    education = sd.get("education") if isinstance(sd.get("education"), dict) else {}
    education_incomplete = bool(education.get("institution") or education.get("graduation_year")) and not (
        education.get("degree") and education.get("field")
    )
    return education_incomplete or years < 3 or (work and not has_present_role and years < 5)


# Purpose: Implements the file key backend behavior.
def _file_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", Path(value or "").stem.lower())


# Purpose: Implements the resolve resume path backend behavior.
def _resolve_resume_path(resume_file: str) -> Path | None:
    wanted_name = Path(resume_file).name
    candidates = [UPLOAD_DIR / wanted_name]
    wanted_key = _file_key(wanted_name)
    for folder in (UPLOAD_DIR,):
        if not folder.exists():
            continue
        for path in folder.glob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".pdf", ".docx", ".txt"}:
                continue
            if path.name == wanted_name or (wanted_key and _file_key(path.name) == wanted_key):
                candidates.append(path)
    for path in candidates:
        resolved = path.resolve()
        if resolved.exists():
            return resolved
    return None


# Purpose: Implements the sync candidate status backend behavior.
def _sync_candidate_status(candidate: dict[str, Any]) -> None:
    score = _match_score(candidate.get("match_score"))
    status = _status_from_score(score)
    stage = "Screening" if status == "Selected" else "Rejected"
    candidate["match_score"] = score
    candidate["status"] = status
    candidate["hiring_stage"] = stage


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _interview_stage(candidate_id: int) -> str:
    interviews = db.get_interviews({"candidate_id": candidate_id})
    if not interviews:
        return ""
    now = datetime.now(timezone.utc)
    latest = sorted(interviews, key=lambda row: str(row.get("interview_start") or ""), reverse=True)[0]
    status = str(latest.get("status") or "").strip().lower()
    if status in {"cancelled", "canceled"}:
        return "Interview Cancelled"
    if status == "rescheduled":
        return "Interview Rescheduled"
    if status == "rejected after interview":
        return "Rejected After Interview"
    if status == "client interview pending":
        return "Client Interview Pending"
    end_at = _parse_datetime(latest.get("interview_end"))
    if end_at and end_at < now:
        return "Interview Completed"
    return "Interview Scheduled"


def _apply_current_hiring_stage(candidate: dict[str, Any]) -> dict[str, Any]:
    if str(candidate.get("status") or "").lower() == "rejected":
        candidate["hiring_stage"] = "Rejected"
        return candidate
    stage = _interview_stage(int(candidate.get("id") or 0))
    if stage:
        candidate["hiring_stage"] = stage
    return candidate


def _split_summary_items(values: list[str], prefixes: tuple[str, ...]) -> list[str]:
    items: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        lowered = text.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix):
                text = text[len(prefix):].strip(" :.-")
                break
        for part in re.split(r",|\n|;", text):
            cleaned = part.strip(" .:-")
            if cleaned:
                items.append(cleaned)
    return list(dict.fromkeys(items))[:8]


# Purpose: Implements the sync comparison statuses backend behavior.
def _sync_comparison_statuses(candidate_id: int) -> None:
    for co in db.get_comparisons(candidate_id=candidate_id):
        score = _match_score(co.get("match_score"))
        status = _status_from_score(score)
        if co.get("status") == status and co.get("match_score") == score:
            continue
        db.upsert_comparison(
            {
                **co,
                "match_score": score,
                "status": status,
                "failure_reason": co.get("failure_reason") or ("" if status == "Selected" else "Match score below 75% threshold."),
            }
        )


# Purpose: Implements the merge reextracted profile backend behavior.
def _merge_reextracted_profile(candidate: dict[str, Any], *, force: bool = False) -> bool:
    resume_file = str(candidate.get("resume_file") or "").strip()
    if not resume_file:
        return False

    resume_path = _resolve_resume_path(resume_file)
    if not resume_path:
        return False

    current = candidate.get("structured_data") if isinstance(candidate.get("structured_data"), dict) else {}
    if not force and not _profile_data_looks_incomplete(current):
        return False

    try:
        raw_text = extract_text(str(resume_path))
        repaired = extract_resume_regex(clean_resume_text(raw_text))
        repaired = _normalize_structured_data(repaired)
    except Exception as exc:
        print(f"[WARN] Could not repair candidate {candidate.get('id')} resume extraction: {exc}")
        return False

    current_edu = current.get("education") if isinstance(current.get("education"), dict) else {}
    repaired_edu = repaired.get("education") if isinstance(repaired.get("education"), dict) else {}
    repaired_better_experience = _experience_years(repaired.get("total_experience_years")) > _experience_years(current.get("total_experience_years"))
    repaired_better_education = bool(repaired_edu.get("degree") or repaired_edu.get("field")) and (
        not current_edu.get("degree") or not current_edu.get("field")
    )
    repaired_has_identity = bool(repaired.get("candidate_name") or repaired.get("email") or repaired.get("phone"))
    if not force and not (repaired_better_experience or repaired_better_education):
        return False

    merged = {**current, **repaired}
    candidate["structured_data"] = _normalize_structured_data(merged)
    if repaired.get("candidate_name") and (force or str(candidate.get("name") or "").lower() in {"", "unknown", "unknown candidate"}):
        candidate["name"] = repaired["candidate_name"]
    if repaired.get("email"):
        candidate["email"] = repaired["email"]
    if repaired.get("phone"):
        candidate["phone"] = repaired["phone"]
    if not repaired_has_identity and not (repaired_better_experience or repaired_better_education):
        return False
    _sync_candidate_status(candidate)
    db.update_candidate(
        int(candidate["id"]),
        {
            "name": candidate.get("name", ""),
            "email": candidate.get("email", ""),
            "phone": candidate.get("phone", ""),
            "structured_data": candidate["structured_data"],
            "match_score": candidate.get("match_score", 0),
            "status": candidate.get("status", "Rejected"),
            "hiring_stage": candidate.get("hiring_stage", "Rejected"),
        },
    )
    _sync_comparison_statuses(int(candidate["id"]))
    return True


# Purpose: Normalizes candidate record into the app's expected format.
def normalize_candidate_record(candidate: dict[str, Any], *, repair: bool = True, force_reextract: bool = False) -> dict[str, Any]:
    candidate = dict(candidate or {})
    candidate["structured_data"] = _normalize_structured_data(candidate.get("structured_data"))
    if repair:
        _merge_reextracted_profile(candidate, force=force_reextract)
    if not candidate.get("email") and candidate["structured_data"].get("email"):
        candidate["email"] = candidate["structured_data"]["email"]
    if not candidate.get("phone") and candidate["structured_data"].get("phone"):
        candidate["phone"] = candidate["structured_data"]["phone"]
    current_category = {
        "primary_category": candidate.get("primary_category") or "",
        "secondary_categories": candidate.get("secondary_categories") or [],
        "matched_keywords": candidate.get("matched_keywords") or [],
        "categorization_source": candidate.get("categorization_source") or "",
        "confidence_score": int(candidate.get("confidence_score") or 0),
        "categorized_date": candidate.get("categorized_date"),
        "category_reason": candidate.get("category_reason") or "",
        "sub_tags": candidate.get("sub_tags") or [],
    }
    category_payload = categorize_candidate(candidate)
    comparable_keys = [key for key in category_payload if key != "categorized_date"]
    if current_category.get("categorized_date") and all(
        current_category.get(key) == category_payload.get(key) for key in comparable_keys
    ):
        category_payload["categorized_date"] = current_category.get("categorized_date")
    candidate.update(category_payload)
    should_persist_category = int(candidate.get("id") or 0) and any(current_category.get(key) != category_payload.get(key) for key in category_payload)
    if should_persist_category:
        db.update_candidate(int(candidate["id"]), category_payload)
    _sync_candidate_status(candidate)
    _apply_current_hiring_stage(candidate)
    return candidate


# Purpose: Implements the candidates payload backend behavior.
def candidates_payload(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    if filters.get("jd_id") is not None:
        rows = db.get_candidates_for_jd(int(filters["jd_id"]), str(filters.get("status") or "").strip() or None)
        rows = [normalize_candidate_record(row) for row in rows]
        search = str(filters.get("search") or "").strip().lower()
        if search:
            rows = [
                row
                for row in rows
                if search in str(row.get("name") or "").lower() or search in str(row.get("email") or "").lower()
            ]
        return rows

    db_filters = {k: v for k, v in filters.items() if k not in {"status"}}
    rows = [normalize_candidate_record(row) for row in db.get_all_candidates(db_filters if db_filters else None)]
    status_filter = str(filters.get("status") or "").strip().lower()
    if status_filter:
        rows = [row for row in rows if str(row.get("status") or "").lower() == status_filter]
    return rows


# Purpose: Implements the repair all candidates backend behavior.
def repair_all_candidates(*, force_reextract: bool = True) -> dict[str, int]:
    checked = repaired = status_updates = 0
    for row in db.get_all_candidates():
        checked += 1
        before_status = row.get("status")
        before_stage = row.get("hiring_stage")
        before_data = row.get("structured_data") if isinstance(row.get("structured_data"), dict) else {}
        normalized = normalize_candidate_record(row, repair=True, force_reextract=force_reextract)
        changed_data = normalized.get("structured_data") != before_data
        changed_status = normalized.get("status") != before_status or normalized.get("hiring_stage") != before_stage
        if changed_data or changed_status:
            db.update_candidate(
                int(normalized["id"]),
                {
                    "name": normalized.get("name", ""),
                    "email": normalized.get("email", ""),
                    "phone": normalized.get("phone", ""),
                    "structured_data": normalized.get("structured_data") or {},
                    "match_score": normalized.get("match_score", 0),
                    "status": normalized.get("status", "Rejected"),
                    "hiring_stage": normalized.get("hiring_stage", "Rejected"),
                },
            )
            repaired += 1
        if changed_status:
            status_updates += 1
        _sync_comparison_statuses(int(normalized["id"]))
    return {"checked": checked, "repaired": repaired, "status_updates": status_updates}


# Purpose: Implements the candidate profile payload backend behavior.
def candidate_profile_payload(candidate_id: int) -> dict[str, Any] | None:
    candidate = db.get_candidate_by_id(candidate_id)
    if not candidate:
        return None
    candidate = normalize_candidate_record(candidate)
    _apply_current_hiring_stage(candidate)
    comps = db.get_comparisons(candidate_id=candidate_id)
    for co in comps:
        co["match_score"] = _match_score(co.get("match_score"))
        co["status"] = _status_from_score(co["match_score"])
    timeline = [
        {
            "label": co.get("jd_title") or "Screening",
            "date": (co.get("comparison_date") or "")[:19],
            "status": co.get("status"),
            "score": co.get("match_score"),
            "summary": co.get("recommendation") or candidate.get("screening_summary") or "",
            "type": "screening",
        }
        for co in comps
    ]
    interviews = db.get_interviews({"candidate_id": candidate_id})
    for interview in interviews:
        email_status = interview.get("email_status") or "sent"
        text_status = interview.get("text_status") or "sent"
        timeline.append(
            {
                "label": f"Interview scheduled - {interview.get('job_role') or 'Role'}",
                "date": str(interview.get("interview_start") or "")[:19],
                "status": interview.get("status") or "Scheduled",
                "summary": f"Email: {email_status} | Text: {text_status}",
                "type": "interview",
            }
        )
        if interview.get("followup_status") == "sent":
            timeline.append(
                {
                    "label": f"Follow-up sent - {interview.get('job_role') or 'Role'}",
                    "date": str(interview.get("followup_sent_at") or interview.get("updated_at") or "")[:19],
                    "status": "Sent",
                    "summary": interview.get("followup_subject") or "Follow-up sent",
                    "type": "followup",
                }
            )
    timeline.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
    strengths = []
    gaps = []
    for co in comps:
        strengths.extend(str(x) for x in (co.get("strengths") or []) if x)
        gaps.extend(str(x) for x in (co.get("gaps") or []) if x)
    matched_skills = _split_summary_items(strengths, ("matched skills", "strengths"))
    missing_skills = _split_summary_items(gaps, ("missing required skills", "missing skills", "gaps"))
    ai_summary = {
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "strengths": matched_skills or list(dict.fromkeys(strengths))[:5],
        "risks": missing_skills or list(dict.fromkeys(gaps))[:5],
        "interview_focus": list(dict.fromkeys((missing_skills or []) + (matched_skills or [])))[:8],
        "recommendation": (
            candidate.get("screening_summary")
            or (comps[0].get("recommendation") if comps else "")
            or "Review the screening results and validate role fit during the interview."
        ),
    }
    payload = {
        **candidate,
        "ai_summary": ai_summary,
        "interviews": interviews,
        "jd_history": [
            {
                "jd_title": x.get("jd_title", ""),
                "match_score": x.get("match_score", 0),
                "comparison_date": x.get("comparison_date", ""),
            }
            for x in comps
        ],
        "match_scores": [
            {"jd_title": x.get("jd_title", ""), "score": x.get("match_score", 0), "date": (x.get("comparison_date") or "")[:10]}
            for x in comps
        ],
        "screening_summaries": [
            {
                "jd_title": x.get("jd_title", ""),
                "summary": x.get("recommendation") or candidate.get("screening_summary", ""),
                "status": x.get("status", ""),
                "rejection_reason": x.get("failure_reason") or candidate.get("rejection_reason", ""),
                "strengths": x.get("strengths") or [],
                "gaps": x.get("gaps") or [],
                "recommendation": x.get("recommendation") or "",
            }
            for x in comps
        ],
    }

    if not payload["screening_summaries"]:
        payload["screening_summaries"] = [
            {
                "jd_title": "Screening",
                "summary": candidate.get("screening_summary", ""),
                "status": candidate.get("status", ""),
                "rejection_reason": candidate.get("rejection_reason", ""),
                "strengths": [],
                "gaps": [],
                "recommendation": "",
            }
        ]
    return {"candidate": payload, "timeline": timeline}
