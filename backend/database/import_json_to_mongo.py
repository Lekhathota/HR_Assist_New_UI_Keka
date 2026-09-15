# Backend file purpose: Database migration, import, or seed utility for import json to mongo.
"""
Import legacy Recruitment Assist JSON data into MongoDB.

Usage from project root:
  npm run import:json -- --data-dir "C:\\path\\to\\data"

To replace current demo/imported records first:
  npm run import:json -- --data-dir "C:\\path\\to\\data" --clear-existing
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv(BACKEND_DIR / ".env")

import database as db  # noqa: E402

DEFAULT_DATA_DIRS = [
    BACKEND_DIR / "data",
    Path(r"C:\Users\pendr\OneDrive\Desktop\Updated\Recruitment-Assist\data"),
]


# Purpose: Implements the load json backend behavior.
def _load_json(data_dir: Path, name: str) -> list[dict]:
    path = data_dir / name
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


# Purpose: Parses dt into structured values.
def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


# Purpose: Implements the list backend behavior.
def _list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return []


# Purpose: Implements the hash password backend behavior.
def _hash_password(password: str) -> str:
    password = password or ""
    if password.startswith(("scrypt:", "pbkdf2:", "argon2:")):
        return password
    return generate_password_hash(password)


# Purpose: Implements the resolve data dir backend behavior.
def _resolve_data_dir(arg: str | None) -> Path:
    if arg:
        path = Path(arg).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Data directory not found: {path}")
        return path
    for path in DEFAULT_DATA_DIRS:
        if path.exists():
            return path
    raise FileNotFoundError("No data directory found. Pass --data-dir.")


# Purpose: Implements the clear existing backend behavior.
def _clear_existing(mongo) -> None:
    collections = [
        "users",
        "user_session_tokens",
        "job_descriptions",
        "candidates",
        "comparisons",
        "audit_logs",
    ]
    for name in collections:
        mongo[name].delete_many({})
    mongo.counters.delete_many(
        {"_id": {"$in": ["users", "job_descriptions", "candidates", "comparisons", "audit_logs"]}}
    )


# Purpose: Implements the import users backend behavior.
def _import_users(mongo, users: list[dict]) -> int:
    count = 0
    for raw in users:
        if not isinstance(raw, dict) or not raw.get("username"):
            continue
        user_id = int(raw.get("id") or 0) or db._next_id("users")
        doc = {
            "id": user_id,
            "username": raw.get("username") or "",
            "password": _hash_password(raw.get("password") or ""),
            "email": raw.get("email") or "",
            "role": raw.get("role") or "user",
            "created_at": _parse_dt(raw.get("created_at")),
        }
        mongo.users.update_one({"id": user_id}, {"$set": doc}, upsert=True)
        db._ensure_counter_at_least("users", user_id)
        count += 1
    return count


# Purpose: Implements the import jds backend behavior.
def _import_jds(mongo, jds: list[dict]) -> int:
    count = 0
    for raw in jds:
        if not isinstance(raw, dict) or raw.get("id") is None:
            continue
        jd_id = int(raw["id"])
        structured = raw.get("structured_data") if isinstance(raw.get("structured_data"), dict) else {}
        responsibilities = raw.get("responsibilities")
        if responsibilities is None:
            responsibilities = structured.get("responsibilities") if isinstance(structured, dict) else []
        created = _parse_dt(raw.get("created") or raw.get("created_at"))
        doc = {
            "id": jd_id,
            "title": raw.get("title") or "",
            "department": raw.get("department") or "",
            "location": raw.get("location") or "",
            "experience_required": raw.get("experience_required") or raw.get("experience") or "",
            "skills": _list(raw.get("skills")),
            "responsibilities": _list(responsibilities),
            "structured_data": structured,
            "raw_text": raw.get("raw_text") or "",
            "file_name": raw.get("file_name") or raw.get("file") or "",
            "status": raw.get("status") or "Active",
            "created_at": created,
            "updated_at": _parse_dt(raw.get("updated_at") or raw.get("created") or raw.get("created_at")),
        }
        mongo.job_descriptions.update_one({"id": jd_id}, {"$set": doc}, upsert=True)
        db._ensure_counter_at_least("job_descriptions", jd_id)
        count += 1
    return count


# Purpose: Implements the import candidates backend behavior.
def _import_candidates(mongo, candidates: list[dict]) -> int:
    count = 0
    for raw in candidates:
        if not isinstance(raw, dict) or raw.get("id") is None:
            continue
        candidate_id = int(raw["id"])
        structured = raw.get("structured_data") if isinstance(raw.get("structured_data"), dict) else {}
        phone = raw.get("phone") or structured.get("phone") or ""
        doc = {
            "id": candidate_id,
            "name": raw.get("name") or "",
            "email": raw.get("email") or structured.get("email") or "",
            "phone": phone,
            "applied_roles": _list(raw.get("applied_roles")),
            "structured_data": structured,
            "match_score": int(raw.get("match_score") or 0),
            "status": raw.get("status") or "Pending",
            "screening_summary": raw.get("screening_summary") or "",
            "rejection_reason": raw.get("rejection_reason") or "",
            "hiring_stage": raw.get("hiring_stage") or "",
            "resume_file": raw.get("resume_file") or raw.get("file") or "",
            "uploaded_at": _parse_dt(raw.get("uploaded") or raw.get("uploaded_at")),
            "jd_id": int(raw["jd_id"]) if raw.get("jd_id") not in (None, "") else None,
        }
        mongo.candidates.update_one({"id": candidate_id}, {"$set": doc}, upsert=True)
        db._ensure_counter_at_least("candidates", candidate_id)
        count += 1
    return count


# Purpose: Implements the import comparisons backend behavior.
def _import_comparisons(mongo, comparisons: list[dict]) -> int:
    count = 0
    for raw in comparisons:
        if not isinstance(raw, dict) or raw.get("id") is None:
            continue
        comparison_id = int(raw["id"])
        doc = {
            "id": comparison_id,
            "jd_id": int(raw.get("jd_id") or 0),
            "candidate_id": int(raw.get("candidate_id") or 0),
            "match_score": int(raw.get("match_score") or 0),
            "status": raw.get("status") or "Pending",
            "strengths": _list(raw.get("strengths")),
            "gaps": _list(raw.get("gaps")),
            "recommendation": raw.get("recommendation") or "",
            "failure_reason": raw.get("failure_reason") or "",
            "comparison_date": _parse_dt(raw.get("comparison_date")),
            "matched_skills": _list(raw.get("matched_skills")),
            "missing_skills": _list(raw.get("missing_skills")),
            "match_details": raw.get("match_details") if isinstance(raw.get("match_details"), dict) else {},
        }
        mongo.comparisons.update_one({"id": comparison_id}, {"$set": doc}, upsert=True)
        db._ensure_counter_at_least("comparisons", comparison_id)
        count += 1
    return count


# Purpose: Implements the import audit logs backend behavior.
def _import_audit_logs(mongo, audit_logs: list[dict]) -> int:
    count = 0
    for raw in audit_logs:
        if not isinstance(raw, dict):
            continue
        timestamp = _parse_dt(raw.get("timestamp"))
        audit_id = int(raw.get("id") or 0) or db._next_id("audit_logs")
        jd_raw = raw.get("jd_id")
        jd_id = int(jd_raw) if jd_raw not in (None, "", 0) else None
        doc = {
            "id": audit_id,
            "action": raw.get("action") or "",
            "username": raw.get("username") or raw.get("user") or "",
            "details": raw.get("details") or "",
            "jd_id": jd_id,
            "timestamp": timestamp,
        }
        mongo.audit_logs.update_one({"id": audit_id}, {"$set": doc}, upsert=True)
        db._ensure_counter_at_least("audit_logs", audit_id)
        count += 1
    return count


# Purpose: Coordinates the main routine for this module.
def main() -> int:
    parser = argparse.ArgumentParser(description="Import legacy JSON data into MongoDB.")
    parser.add_argument("--data-dir", help="Folder containing users.json, jds.json, candidates.json, comparisons.json, audit_logs.json.")
    parser.add_argument("--clear-existing", action="store_true", help="Clear current MongoDB app data before import.")
    args = parser.parse_args()

    data_dir = _resolve_data_dir(args.data_dir)
    db.init_pool()
    mongo = db._database()

    if args.clear_existing:
        _clear_existing(mongo)
        print("Cleared existing MongoDB app data.")

    users = _load_json(data_dir, "users.json")
    jds = _load_json(data_dir, "jds.json")
    candidates = _load_json(data_dir, "candidates.json")
    comparisons = _load_json(data_dir, "comparisons.json")
    audit_logs = _load_json(data_dir, "audit_logs.json")

    imported = {
        "users": _import_users(mongo, users),
        "jds": _import_jds(mongo, jds),
        "candidates": _import_candidates(mongo, candidates),
        "comparisons": _import_comparisons(mongo, comparisons),
        "audit_logs": _import_audit_logs(mongo, audit_logs),
    }

    print(f"Imported JSON data from: {data_dir}")
    for name, count in imported.items():
        print(f"{name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
