# Backend file purpose: Database migration, import, or seed utility for import uploads to mongo.
"""
Import existing files from backend/static/uploads into MongoDB.

Usage from project root:
  npm run import:uploads

The importer is idempotent by file name: files already represented in MongoDB
are skipped.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")

import database as db  # noqa: E402
from app.regex_extractor import extract_jd_regex, extract_resume_regex  # noqa: E402
from app.text_extractor import extract_text  # noqa: E402
from app.utils import clean_jd_text, clean_resume_text  # noqa: E402

UPLOAD_DIR = BACKEND_DIR / "static" / "uploads"
ALLOWED = {".pdf", ".docx", ".txt"}
SELECTION_MATCH_THRESHOLD = 75

JD_NAME_HINTS = (
    "jd",
    "job_description",
    "job description",
    "description",
    "data_engineer_datamatica",
    "mysql_data_base_administrator",
    "service_now_developer",
    "document_2",
)

RESUME_NAME_HINTS = (
    "resume",
    "avula",
    "kotireddy",
    "kusuma",
    "lallithaa",
    "lekha",
    "rama",
    "ramineni",
    "yelike",
)

SKILL_WORDS = [
    "python", "java", "javascript", "typescript", "react", "node", "flask", "django", "fastapi",
    "sql", "postgresql", "postgres", "mysql", "mongodb", "redis", "docker", "kubernetes",
    "aws", "azure", "gcp", "git", "jenkins", "terraform", "ansible", "linux", "devops",
    "selenium", "manual testing", "automation testing", "qa", "postman", "cypress",
    "servicenow", "service now", "snow", "data engineering", "etl", "spark", "airflow",
    "generative ai", "llm", "machine learning", "pandas", "numpy",
]


# Purpose: Implements the name stem backend behavior.
def _name_stem(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").strip()


# Purpose: Normalizes skill into the app's expected format.
def _normalize_skill(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


# Purpose: Implements the skills from text backend behavior.
def _skills_from_text(text: str) -> list[str]:
    lowered = text.lower()
    found = []
    for skill in SKILL_WORDS:
        if skill in lowered:
            found.append(skill.title() if skill not in {"qa", "llm"} else skill.upper())
    return list(dict.fromkeys(found))


# Purpose: Checks whether resume text is true.
def _is_resume_text(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
        or "curriculum vitae" in lowered
        or "professional summary" in lowered
        or "education" in lowered and "experience" in lowered and "skills" in lowered
    )


# Purpose: Implements the classify backend behavior.
def _classify(path: Path, text: str) -> str:
    stem = path.stem.lower()
    for hint in RESUME_NAME_HINTS:
        if hint in stem:
            return "resume"
    for hint in JD_NAME_HINTS:
        if hint in stem:
            return "jd"

    lowered = text.lower()
    if _is_resume_text(text) and "job description" not in lowered:
        return "resume"
    if "job description" in lowered or "responsibilities" in lowered and "required skills" in lowered:
        return "jd"
    return "resume"


# Purpose: Implements the candidate name from file backend behavior.
def _candidate_name_from_file(path: Path, resume_json: dict[str, Any]) -> str:
    extracted = str(resume_json.get("candidate_name") or "").strip()
    if extracted and extracted.lower() != "unknown":
        return extracted
    stem = _name_stem(path)
    stem = re.sub(r"\b(resume|main|exp|years?|of|pdf|docx)\b", " ", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\d+|[_\-]+", " ", stem)
    return re.sub(r"\s+", " ", stem).strip().title() or "Unknown Candidate"


# Purpose: Implements the jd title from file backend behavior.
def _jd_title_from_file(path: Path, jd_json: dict[str, Any]) -> str:
    extracted = str(jd_json.get("job_title") or "").strip()
    if extracted and extracted.lower() != "unknown position":
        return extracted
    stem = _name_stem(path)
    stem = re.sub(r"\b(jd|job description|document)\b", " ", stem, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", stem).strip().title() or "Imported Job Description"


# Purpose: Implements the existing file names backend behavior.
def _existing_file_names() -> tuple[set[str], set[str]]:
    jds = {str(row.get("file_name") or row.get("file") or "") for row in db.get_all_jds()}
    candidates = {str(row.get("resume_file") or "") for row in db.get_all_candidates()}
    return jds, candidates


# Purpose: Creates jd records or payloads.
def _create_jd(path: Path, text: str) -> int:
    cleaned = clean_jd_text(text)
    jd_json = extract_jd_regex(cleaned)
    title = _jd_title_from_file(path, jd_json)
    skills = jd_json.get("required_skills") or _skills_from_text(cleaned)
    new_id = db.create_jd(
        {
            "title": title,
            "department": jd_json.get("industry") or "Imported",
            "location": jd_json.get("location") or "Not specified",
            "experience_required": jd_json.get("experience_range") or "Not specified",
            "skills": skills,
            "responsibilities": jd_json.get("responsibilities") or [],
            "structured_data": {**jd_json, "required_skills": skills},
            "raw_text": cleaned,
            "file_name": path.name,
            "status": "Active",
        }
    )
    return new_id


# Purpose: Implements the score resume backend behavior.
def _score_resume(jd: dict[str, Any], resume_json: dict[str, Any]) -> dict[str, Any]:
    jd_data = jd.get("structured_data") or {}
    jd_skills = {
        _normalize_skill(x)
        for x in (jd_data.get("required_skills") or jd.get("skills") or [])
        if _normalize_skill(x)
    }
    resume_skills = {
        _normalize_skill(x)
        for x in ((resume_json.get("skills") or []) + (resume_json.get("technical_skills") or []))
        if _normalize_skill(x)
    }
    matched = sorted(jd_skills.intersection(resume_skills))
    missing = sorted(jd_skills.difference(resume_skills))
    skill_score = int((len(matched) / len(jd_skills)) * 100) if jd_skills else 50
    exp = float(resume_json.get("total_experience_years") or 0)
    exp_score = min(100, int(exp * 20)) if exp else 40
    score = max(0, min(100, int((skill_score * 0.75) + (exp_score * 0.25))))
    status = "Selected" if score >= SELECTION_MATCH_THRESHOLD else "Rejected"
    return {
        "score": score,
        "status": status,
        "matched": [x.title() for x in matched],
        "missing": [x.title() for x in missing],
    }


# Purpose: Implements the best jd match backend behavior.
def _best_jd_match(jds: list[dict[str, Any]], resume_json: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not jds:
        return None, {"score": 0, "status": "Pending", "matched": [], "missing": []}
    ranked = [(jd, _score_resume(jd, resume_json)) for jd in jds]
    ranked.sort(key=lambda item: item[1]["score"], reverse=True)
    return ranked[0]


# Purpose: Creates candidate records or payloads.
def _create_candidate(path: Path, text: str, jds: list[dict[str, Any]]) -> int:
    cleaned = clean_resume_text(text)
    resume_json = extract_resume_regex(cleaned)
    skills = list(dict.fromkeys((resume_json.get("skills") or []) + _skills_from_text(cleaned)))
    resume_json["skills"] = skills
    resume_json["technical_skills"] = skills
    name = _candidate_name_from_file(path, resume_json)
    best_jd, match = _best_jd_match(jds, resume_json)
    jd_id = int(best_jd["id"]) if best_jd else None
    role = best_jd.get("title") if best_jd else "Imported Resume"
    summary = (
        f"Imported from existing upload. Match score: {match['score']}%. "
        f"Matched skills: {', '.join(match['matched'][:8]) or 'None'}."
    )
    candidate_id = db.create_candidate(
        {
            "name": name,
            "email": resume_json.get("email", ""),
            "phone": resume_json.get("phone", ""),
            "applied_roles": [role],
            "structured_data": resume_json,
            "match_score": match["score"],
            "status": match["status"],
            "screening_summary": summary,
            "rejection_reason": "" if match["status"] == "Selected" else "Imported match score below selection threshold.",
            "hiring_stage": "Imported" if match["status"] == "Selected" else "Rejected",
            "resume_file": path.name,
            "jd_id": jd_id,
        }
    )
    if jd_id is not None:
        db.upsert_comparison(
            {
                "jd_id": jd_id,
                "candidate_id": candidate_id,
                "match_score": match["score"],
                "status": match["status"],
                "strengths": [f"Matched skills: {', '.join(match['matched'][:8])}"] if match["matched"] else [],
                "gaps": [f"Missing skills: {', '.join(match['missing'][:8])}"] if match["missing"] else [],
                "recommendation": summary,
                "failure_reason": "" if match["status"] == "Selected" else "Imported match score below selection threshold.",
                "comparison_date": datetime.now(timezone.utc),
            }
        )
    return candidate_id


# Purpose: Coordinates the main routine for this module.
def main() -> int:
    db.init_pool()
    clear_existing = "--clear-existing" in sys.argv
    if clear_existing:
        mongo = db._database()  # Import utility for local/dev data reset.
        for name in ("job_descriptions", "candidates", "comparisons", "audit_logs"):
            mongo[name].delete_many({})
        mongo.counters.delete_many({"_id": {"$in": ["job_descriptions", "candidates", "comparisons", "audit_logs"]}})
        print("Cleared existing jobs, candidates, comparisons, and audit logs.")

    if not UPLOAD_DIR.exists():
        print(f"Upload folder not found: {UPLOAD_DIR}")
        return 1

    paths = sorted(p for p in UPLOAD_DIR.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED)
    if not paths:
        print("No upload files found.")
        return 0

    existing_jd_files, existing_resume_files = _existing_file_names()
    parsed: list[tuple[Path, str, str]] = []
    failed: list[tuple[str, str]] = []

    for path in paths:
        try:
            text = extract_text(str(path))
            kind = _classify(path, text)
            parsed.append((path, kind, text))
        except Exception as exc:
            failed.append((path.name, str(exc)))

    created_jds = 0
    skipped_jds = 0
    for path, kind, text in parsed:
        if kind != "jd":
            continue
        if path.name in existing_jd_files:
            skipped_jds += 1
            continue
        _create_jd(path, text)
        created_jds += 1

    jds = db.get_all_jds()
    created_candidates = 0
    skipped_candidates = 0
    for path, kind, text in parsed:
        if kind != "resume":
            continue
        if path.name in existing_resume_files:
            skipped_candidates += 1
            continue
        _create_candidate(path, text, jds)
        created_candidates += 1

    db.log_audit(
        "Upload Import",
        "system",
        (
            f"Imported uploads into MongoDB. JDs created={created_jds}, candidates created={created_candidates}, "
            f"JDs skipped={skipped_jds}, candidates skipped={skipped_candidates}, failed={len(failed)}."
        ),
        None,
    )

    print("Upload import complete.")
    print(f"Files scanned: {len(paths)}")
    print(f"JDs created: {created_jds}; skipped: {skipped_jds}")
    print(f"Candidates created: {created_candidates}; skipped: {skipped_candidates}")
    if failed:
        print("Failed files:")
        for name, error in failed:
            print(f"  - {name}: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
