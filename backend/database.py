# Backend file purpose: Backend entrypoint or shared infrastructure for database.
"""
MongoDB Atlas data layer for Recruitment Assist.

The rest of the Flask app expects numeric IDs in URLs and payloads, so MongoDB
documents keep an integer `id` field in addition to Mongo's internal `_id`.
"""

from __future__ import annotations

import os
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure
from werkzeug.security import check_password_hash, generate_password_hash

_client: Optional[MongoClient] = None
_db: Any = None

DEFAULT_CLIENT_ACCOUNT_ID = "SHIMENTOX"
DEFAULT_CLIENT_NAME = "ShimentoX"
DEFAULT_PROJECT_NAME = "ShimentoX Internal"
LEGACY_DEFAULT_PROJECT_NAMES = ["Internal Bench"]


# Purpose: Fetches mongo uri from storage or service context.
def get_mongo_uri() -> str:
    # Vercel's MongoDB integration commonly exposes MONGODB_URL, while the
    # application historically documented MONGODB_URI. Accept both names.
    uri = (
        os.environ.get("MONGODB_URI")
        or os.environ.get("MONGODB_URL")
        or os.environ.get("MONGO_URI")
    )
    if not uri:
        legacy = os.environ.get("DATABASE_URL") or ""
        if legacy.startswith(("mongodb://", "mongodb+srv://")):
            uri = legacy
    if not uri:
        raise RuntimeError("Set MONGODB_URI or MONGODB_URL in the environment.")
    return uri


# Purpose: Fetches db name from storage or service context.
def get_db_name() -> str:
    return os.environ.get("MONGODB_DB") or os.environ.get("MONGO_DB") or "recruitment_assist"


# Purpose: Implements the init pool backend behavior.
def init_pool() -> None:
    """Compatibility name used by app.py; initializes the MongoDB client."""
    global _client, _db
    if _client is not None:
        return
    candidate_client = MongoClient(get_mongo_uri(), serverSelectionTimeoutMS=5000)
    candidate_db = candidate_client[get_db_name()]
    try:
        candidate_client.admin.command("ping")
        _client = candidate_client
        _db = candidate_db
        _ensure_indexes()
        _sync_counters()
        backfill_workflow_defaults()
        _migrate_legacy_user_passwords()
        _seed_default_users()
        ensure_default_client_and_backfill()
        refresh_dashboard_metrics()
    except Exception:
        candidate_client.close()
        _client = None
        _db = None
        raise


# Purpose: Implements the close pool backend behavior.
def close_pool() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


# Purpose: Implements the init db backend behavior.
def init_db() -> None:
    """Compatibility wrapper for older app.py startup code."""
    init_pool()


# Purpose: Implements the seed data backend behavior.
def seed_data() -> None:
    """Compatibility wrapper; default users are seeded during init_pool()."""
    init_pool()
    _seed_default_users()


# Purpose: Implements the database backend behavior.
def _database():
    if _db is None:
        init_pool()
    return _db


def get_database():
    return _database()


# Purpose: Fetches conn from storage or service context.
def get_conn():
    raise RuntimeError("SQL connections are not available. This project is configured for MongoDB.")


# Purpose: Implements the now backend behavior.
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _session_token_ttl_seconds() -> int:
    try:
        hours = int(os.environ.get("SESSION_TOKEN_TTL_HOURS") or "12")
    except ValueError:
        hours = 12
    return max(1, hours) * 60 * 60


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


# Purpose: Implements the next id backend behavior.
def _next_id(name: str) -> int:
    row = _database().counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(row["seq"])


# Purpose: Implements the ensure counter at least backend behavior.
def _ensure_counter_at_least(name: str, value: int) -> None:
    _database().counters.update_one(
        {"_id": name},
        {"$max": {"seq": int(value)}},
        upsert=True,
    )


# Purpose: Implements the ensure indexes backend behavior.
def _ensure_indexes() -> None:
    db = _database()
    db.users.create_index([("username", ASCENDING)], unique=True)
    db.job_descriptions.create_index([("id", ASCENDING)], unique=True)
    db.job_descriptions.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    db.job_descriptions.create_index([("client_id", ASCENDING)])
    db.job_descriptions.create_index([("project_id", ASCENDING)])
    db.job_descriptions.create_index([("job_category", ASCENDING)])
    db.clients.create_index([("id", ASCENDING)], unique=True)
    db.clients.create_index([("client_account_id", ASCENDING)], unique=True)
    db.clients.create_index([("status", ASCENDING), ("name", ASCENDING)])
    db.projects.create_index([("id", ASCENDING)], unique=True)
    db.projects.create_index([("client_id", ASCENDING), ("name", ASCENDING)])
    db.candidates.create_index([("id", ASCENDING)], unique=True)
    db.candidates.create_index([("status", ASCENDING)])
    db.candidates.create_index([("jd_id", ASCENDING)])
    db.candidates.create_index([("client_id", ASCENDING)])
    db.candidates.create_index([("project_id", ASCENDING)])
    db.candidates.create_index([("primary_category", ASCENDING)])
    db.candidates.create_index([("worker_type", ASCENDING), ("bench_status", ASCENDING), ("availability_status", ASCENDING), ("primary_category", ASCENDING)])
    db.comparisons.create_index([("id", ASCENDING)], unique=True)
    db.comparisons.create_index([("jd_id", ASCENDING), ("candidate_id", ASCENDING)], unique=True)
    db.comparisons.create_index([("jd_id", ASCENDING), ("selection_status", ASCENDING)])
    db.interviews.create_index([("id", ASCENDING)], unique=True)
    db.interviews.create_index([("recruiter_id", ASCENDING), ("interview_start", ASCENDING), ("interview_end", ASCENDING)])
    db.vendors.create_index([("id", ASCENDING)], unique=True)
    db.vendors.create_index(
        [("email_normalized", ASCENDING)],
        unique=True,
        partialFilterExpression={"deleted_at": None},
    )
    db.vendors.create_index([("status", ASCENDING), ("company_name", ASCENDING)])
    db.vendors.create_index([("status", ASCENDING), ("supported_categories", ASCENDING)])
    db.jd_vendor_assignments.create_index([("id", ASCENDING)], unique=True)
    db.jd_vendor_assignments.create_index(
        [("jd_id", ASCENDING), ("vendor_id", ASCENDING)],
        unique=True,
        partialFilterExpression={"status": "Active"},
    )
    db.jd_vendor_assignments.create_index([("jd_id", ASCENDING), ("status", ASCENDING)])
    db.jd_vendor_assignments.create_index([("jd_id", ASCENDING), ("status", ASCENDING), ("allocated_count", ASCENDING)])
    db.jd_vendor_assignments.create_index([("vendor_id", ASCENDING), ("status", ASCENDING)])
    db.vendor_email_logs.create_index([("id", ASCENDING)], unique=True)
    db.vendor_email_logs.create_index([("assignment_id", ASCENDING), ("sent_at", DESCENDING)])
    db.vendor_email_logs.create_index([("jd_id", ASCENDING), ("sent_at", DESCENDING)])
    db.vendor_email_logs.create_index([("vendor_id", ASCENDING), ("sent_at", DESCENDING)])
    db.vendor_email_logs.create_index([("sent_at", DESCENDING)])
    db.audit_logs.create_index([("id", ASCENDING)], unique=True)
    db.audit_logs.create_index([("timestamp", DESCENDING)])
    db.agent_runs.create_index([("run_id", ASCENDING)], unique=True)
    db.agent_runs.create_index([("task_type", ASCENDING), ("created_at", DESCENDING)])
    db.agent_runs.create_index([("username", ASCENDING), ("created_at", DESCENDING)])
    db.user_session_tokens.create_index([("token", ASCENDING)], unique=True)
    db.user_session_tokens.create_index([("user_id", ASCENDING)])
    db.user_session_tokens.create_index([("created_at", ASCENDING)], expireAfterSeconds=_session_token_ttl_seconds())
    db.dashboard_metrics.create_index([("updated_at", DESCENDING)])
    from assessment.repository import ensure_assessment_indexes

    ensure_assessment_indexes()


# Purpose: Implements the sync counters backend behavior.
def _sync_counters() -> None:
    db = _database()
    for name in (
        "users",
        "clients",
        "projects",
        "job_descriptions",
        "candidates",
        "comparisons",
        "audit_logs",
        "interviews",
        "vendors",
        "jd_vendor_assignments",
        "vendor_email_logs",
        "assessments",
        "questions",
        "candidate_answers",
        "assessment_results",
        "agent_runs",
    ):
        row = db[name].find_one({}, sort=[("id", DESCENDING)])
        if row and row.get("id") is not None:
            _ensure_counter_at_least(name, int(row["id"]))


def backfill_workflow_defaults(default_required_candidate_count: Optional[int] = None) -> dict[str, int]:
    """Populate nullable workflow fields for legacy records without guessing business counts."""
    db = _database()
    now = _now()
    try:
        env_default = int(os.environ.get("BACKFILL_DEFAULT_REQUIRED_CANDIDATE_COUNT") or 0)
    except ValueError:
        env_default = 0
    required_count = int(default_required_candidate_count or env_default or 0)

    jd_modified = 0
    for field, value in {
        "workflow_status": "ACTIVE",
        "workflow_version": 1,
        "bench_matched_count": 0,
        "bench_analyzed_count": 0,
        "bench_qualified_count": 0,
        "selected_bench_count": 0,
        "accepted_vendor_count": 0,
        "remaining_vendor_requirement": 0,
    }.items():
        jd_modified += int(
            db.job_descriptions.update_many(
                {field: {"$exists": False}},
                {"$set": {field: value, "updated_at": now}},
            ).modified_count
            or 0
        )
    if required_count > 0:
        jd_modified += int(
            db.job_descriptions.update_many(
                {"$or": [{"required_candidate_count": {"$exists": False}}, {"required_candidate_count": None}]},
                {"$set": {"required_candidate_count": required_count, "updated_at": now}},
            ).modified_count
            or 0
        )

    candidate_modified = 0
    candidate_base = {"worker_type": {"$in": ["Internal", "internal", "", None]}}
    for field, value in {"availability_status": "Available", "allocation_status": "Bench"}.items():
        candidate_modified += int(
            db.candidates.update_many(
                {**candidate_base, field: {"$exists": False}},
                {"$set": {field: value, "updated_at": now}},
            ).modified_count
            or 0
        )

    vendor_modified = 0
    for field in ("supported_categories", "supported_sub_tags"):
        vendor_modified += int(
            db.vendors.update_many(
                {field: {"$exists": False}},
                {"$set": {field: [], "updated_at": now}},
            ).modified_count
            or 0
        )

    assignment_modified = 0
    for field, value in {
        "total_required_count": 0,
        "bench_fulfilled_count": 0,
        "remaining_requirement_at_assignment": 0,
        "allocated_count": 0,
        "accepted_count": 0,
        "assignment_source": "manual",
        "delivery_status": "not_sent",
    }.items():
        assignment_modified += int(
            db.jd_vendor_assignments.update_many(
                {field: {"$exists": False}},
                {"$set": {field: value, "updated_at": now}},
            ).modified_count
            or 0
        )
    return {
        "job_descriptions_updated": jd_modified,
        "candidates_updated": candidate_modified,
        "vendors_updated": vendor_modified,
        "assignments_updated": assignment_modified,
    }


# Purpose: Detects password values already stored in a supported hash format.
def _is_password_hash(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("scrypt:", "pbkdf2:", "argon2:"))


def _migrate_legacy_user_passwords() -> int:
    """Replace legacy plaintext user passwords with Werkzeug hashes."""
    users = _database().users
    migrated = 0
    for row in users.find({}, {"_id": 1, "password": 1}):
        password = row.get("password")
        if not isinstance(password, str) or not password or _is_password_hash(password):
            continue
        result = users.update_one(
            {"_id": row["_id"], "password": password},
            {"$set": {"password": generate_password_hash(password)}},
        )
        migrated += int(result.modified_count or 0)
    return migrated


# Purpose: Implements the seed default users backend behavior.
def _seed_default_users() -> None:
    if not _truthy_env("SEED_DEFAULT_USERS"):
        return
    db = _database()
    defaults = [
        ("admin", os.environ.get("DEFAULT_ADMIN_PASSWORD"), "admin@localhost", "admin"),
        ("recruiter", os.environ.get("DEFAULT_RECRUITER_PASSWORD"), "recruiter@localhost", "Recruiter"),
        ("manager", os.environ.get("DEFAULT_MANAGER_PASSWORD"), "manager@localhost", "Hiring Manager"),
    ]
    for username, password, email, role in defaults:
        if not password:
            continue
        if db.users.find_one({"username": username}):
            continue
        user_id = _next_id("users")
        db.users.insert_one(
            {
                "id": user_id,
                "username": username,
                "password": generate_password_hash(password),
                "email": email,
                "role": role,
                "created_at": _now(),
            }
        )


# Purpose: Implements the serialize value backend behavior.
def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items() if k != "_id"}
    return value


# Purpose: Implements the serialize doc backend behavior.
def _serialize_doc(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    return {k: _serialize_value(v) for k, v in doc.items() if k != "_id"}


# Purpose: Implements the serialize docs backend behavior.
def _serialize_docs(rows: list[dict]) -> list[dict]:
    return [_serialize_doc(r) or {} for r in rows]


# Purpose: Implements the list backend behavior.
def _list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return []


# Purpose: Implements the int or none backend behavior.
def _int_or_none(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(value)


def _client_snapshot(client: Optional[dict]) -> dict[str, Any]:
    client = client or get_default_client()
    if not client:
        return {}
    return {
        "client_id": int(client.get("id") or 0),
        "client_account_id": client.get("client_account_id") or "",
        "client_name": client.get("name") or client.get("client_name") or "",
    }


def _client_for_data(data: dict) -> dict[str, Any]:
    client = None
    if data.get("client_id"):
        client = get_client_by_id(int(data["client_id"]))
    if not client and data.get("client_account_id"):
        client = get_client_by_account_id(str(data["client_account_id"]))
    if not client:
        client = get_default_client()
    return _client_snapshot(client)


def _project_snapshot(project: Optional[dict]) -> dict[str, Any]:
    if not project:
        return {}
    return {
        "project_id": int(project.get("id") or 0),
        "project_name": project.get("name") or "",
    }


def _is_default_client(client: Optional[dict]) -> bool:
    return str((client or {}).get("client_account_id") or "").strip().upper() == DEFAULT_CLIENT_ACCOUNT_ID


def _default_project_payload_for_client(client_id: int) -> dict[str, Any]:
    client = get_client_by_id(client_id) or {}
    if _is_default_client(client):
        return {
            "name": DEFAULT_PROJECT_NAME,
            "project_type": "Internal",
            "notes": "Default project for internal bench candidates and existing recruitment data.",
        }
    client_name = str(client.get("name") or "Client").strip() or "Client"
    return {
        "name": f"{client_name} Project",
        "project_type": "Client",
        "notes": "Default project for this client account.",
    }


def _project_for_data(data: dict, client_fields: dict[str, Any]) -> dict[str, Any]:
    project = None
    if data.get("project_id"):
        project = get_project_by_id(int(data["project_id"]))
    if not project:
        client_id = int(client_fields.get("client_id") or 0)
        if client_id:
            project = get_default_project_for_client(client_id)
    return _project_snapshot(project)


# Purpose: Implements the regex filter backend behavior.
def _regex_filter(fields: list[str], search: str) -> dict:
    return {"$or": [{field: {"$regex": search, "$options": "i"}} for field in fields]}


# Clients


def get_default_client() -> Optional[dict]:
    return get_client_by_account_id(DEFAULT_CLIENT_ACCOUNT_ID)


def get_client_by_account_id(client_account_id: str) -> Optional[dict]:
    row = _database().clients.find_one({"client_account_id": str(client_account_id or "").strip().upper()})
    return _serialize_doc(row)


def get_client_by_id(client_id: int) -> Optional[dict]:
    row = _database().clients.find_one({"id": int(client_id)})
    return _serialize_doc(row)


def create_client(data: dict) -> int:
    account_id = str(data.get("client_account_id") or data.get("account_id") or "").strip().upper()
    name = str(data.get("name") or data.get("client_name") or "").strip()
    if not name:
        raise ValueError("Client name is required.")
    if not account_id:
        account_id = "".join(ch for ch in name.upper() if ch.isalnum())[:24] or f"CLIENT{_next_id('clients')}"
    existing = get_client_by_account_id(account_id)
    if existing:
        return int(existing["id"])
    new_id = _next_id("clients")
    now = _now()
    _database().clients.insert_one(
        {
            "id": new_id,
            "client_account_id": account_id,
            "name": name,
            "industry": data.get("industry") or "",
            "location": data.get("location") or "",
            "website": data.get("website") or "",
            "contact_person": data.get("contact_person") or "",
            "contact_email": data.get("contact_email") or "",
            "contact_phone": data.get("contact_phone") or "",
            "account_owner": data.get("account_owner") or "",
            "status": data.get("status") or "Active",
            "notes": data.get("notes") or "",
            "created_at": now,
            "updated_at": now,
        }
    )
    create_project({"client_id": new_id, "status": "Active", **_default_project_payload_for_client(new_id)})
    return new_id


def update_client(client_id: int, data: dict) -> bool:
    allowed = {
        "name",
        "industry",
        "location",
        "website",
        "contact_person",
        "contact_email",
        "contact_phone",
        "account_owner",
        "status",
        "notes",
    }
    patch = {key: data[key] for key in allowed if key in data}
    if not patch:
        return False
    patch["updated_at"] = _now()
    result = _database().clients.update_one({"id": int(client_id)}, {"$set": patch})
    return result.modified_count > 0


def get_all_clients(filters: Optional[dict] = None) -> list[dict]:
    filters = filters or {}
    query: dict[str, Any] = {}
    if filters.get("status"):
        query["status"] = filters["status"]
    if filters.get("search"):
        query.update(_regex_filter(["name", "client_account_id", "industry", "contact_person"], str(filters["search"])))
    clients = _serialize_docs(list(_database().clients.find(query).sort("name", ASCENDING)))
    return [client_summary(row) for row in clients]


def get_project_by_id(project_id: int) -> Optional[dict]:
    return _serialize_doc(_database().projects.find_one({"id": int(project_id)}))


def get_default_project_for_client(client_id: int) -> Optional[dict]:
    client_id = int(client_id)
    payload = _default_project_payload_for_client(client_id)
    row = _database().projects.find_one({"client_id": client_id, "name": payload["name"]})
    if not row:
        legacy_names = [*LEGACY_DEFAULT_PROJECT_NAMES]
        if payload["name"] != DEFAULT_PROJECT_NAME:
            legacy_names.append(DEFAULT_PROJECT_NAME)
        row = _database().projects.find_one({"client_id": client_id, "name": {"$in": legacy_names}})
        if row:
            _database().projects.update_one(
                {"id": int(row["id"])},
                {
                    "$set": {
                        "name": payload["name"],
                        "project_type": payload["project_type"],
                        "notes": row.get("notes") or payload["notes"],
                        "updated_at": _now(),
                    }
                },
            )
            row = _database().projects.find_one({"id": int(row["id"])})
    if row:
        return _serialize_doc(row)
    project_id = create_project({"client_id": client_id, "status": "Active", **payload})
    return get_project_by_id(project_id)


def create_project(data: dict) -> int:
    client_id = int(data.get("client_id") or 0)
    name = str(data.get("name") or "").strip()
    if not client_id or not name:
        raise ValueError("Project client_id and name are required.")
    existing = _database().projects.find_one({"client_id": client_id, "name": name})
    if existing:
        return int(existing["id"])
    project_id = _next_id("projects")
    now = _now()
    client = get_client_by_id(client_id) or {}
    _database().projects.insert_one(
        {
            "id": project_id,
            "client_id": client_id,
            "client_name": client.get("name") or "",
            "name": name,
            "status": data.get("status") or "Active",
            "project_type": data.get("project_type") or "Client",
            "required_roles": data.get("required_roles") if isinstance(data.get("required_roles"), list) else [],
            "notes": data.get("notes") or "",
            "created_at": now,
            "updated_at": now,
        }
    )
    return project_id


def _role_key(value: Any) -> str:
    text = " ".join(str(value or "").replace("_", " ").replace("-", " ").split()).strip()
    return text or "General Bench"


def _candidate_skill_names(candidate: dict) -> list[str]:
    structured = candidate.get("structured_data") if isinstance(candidate.get("structured_data"), dict) else {}
    values = []
    for key in ("skills", "technical_skills"):
        raw = structured.get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if item)
    return list(dict.fromkeys(values))[:8]


def _bench_cards(project_id: int) -> list[dict]:
    rows = _serialize_docs(
        list(
            _database()
            .candidates.find({"project_id": int(project_id), "bench_status": "On Bench"})
            .sort("match_score", DESCENDING)
        )
    )
    groups: dict[str, dict[str, Any]] = {}
    for candidate in rows:
        roles = candidate.get("applied_roles") if isinstance(candidate.get("applied_roles"), list) else []
        skills = _candidate_skill_names(candidate)
        role = _role_key(roles[0] if roles else (skills[0] if skills else "General Bench"))
        group = groups.setdefault(
            role,
            {"role": role, "count": 0, "skills": [], "avg_match": 0, "availability": "Immediate", "candidate_ids": [], "_score_total": 0},
        )
        group["count"] += 1
        group["_score_total"] += int(candidate.get("match_score") or 0)
        group["candidate_ids"].append(candidate.get("id"))
        for skill in skills:
            if skill not in group["skills"]:
                group["skills"].append(skill)
    cards = []
    for group in groups.values():
        count = int(group["count"] or 0)
        cards.append(
            {
                "role": group["role"],
                "count": count,
                "skills": group["skills"][:6],
                "avg_match": int(group["_score_total"] / count) if count else 0,
                "availability": group["availability"],
                "candidate_ids": group["candidate_ids"][:12],
            }
        )
    return sorted(cards, key=lambda item: (-int(item["count"]), str(item["role"]).lower()))[:12]


def _required_role_cards(project: dict, project_id: int) -> list[dict]:
    db = _database()
    required: dict[str, dict[str, Any]] = {}
    for item in project.get("required_roles") or []:
        if not isinstance(item, dict):
            continue
        role = _role_key(item.get("role"))
        required[role] = {
            "role": role,
            "required_count": int(item.get("required_count") or 1),
            "priority": item.get("priority") or "Medium",
            "skills": _list(item.get("skills")),
            "linked_jobs": [],
        }

    jobs = _serialize_docs(list(db.job_descriptions.find({"project_id": int(project_id), "status": "Active"}).sort("created_at", DESCENDING)))
    for job in jobs:
        role = _role_key(job.get("title") or "Required Role")
        row = required.setdefault(
            role,
            {"role": role, "required_count": 0, "priority": "Medium", "skills": [], "linked_jobs": []},
        )
        row["required_count"] = max(1, int(row.get("required_count") or 0) + 1)
        row["linked_jobs"].append({"id": job.get("id"), "title": job.get("title") or role})
        for skill in job.get("skills") or []:
            if skill not in row["skills"]:
                row["skills"].append(skill)

    bench = _serialize_docs(list(db.candidates.find({"project_id": int(project_id), "bench_status": "On Bench"})))
    cards = []
    for row in required.values():
        role_tokens = set(str(row["role"]).lower().split())
        skill_tokens = {str(skill).lower() for skill in row.get("skills") or []}
        available = 0
        for candidate in bench:
            roles = " ".join(str(role) for role in (candidate.get("applied_roles") or [])).lower()
            skills = {skill.lower() for skill in _candidate_skill_names(candidate)}
            if str(row["role"]).lower() in roles or role_tokens.intersection(set(roles.split())) or skill_tokens.intersection(skills):
                available += 1
        required_count = int(row.get("required_count") or 0)
        gap = max(0, required_count - available)
        cards.append(
            {
                "role": row["role"],
                "required_count": required_count,
                "available_count": available,
                "gap": gap,
                "priority": "High" if gap > 0 and required_count >= 2 else row.get("priority") or "Medium",
                "skills": (row.get("skills") or [])[:6],
                "linked_jobs": (row.get("linked_jobs") or [])[:6],
            }
        )
    return sorted(cards, key=lambda item: (-int(item["gap"]), str(item["role"]).lower()))[:12]


def project_summary(project: dict) -> dict:
    db = _database()
    project_id = int(project.get("id") or 0)
    active_jobs = db.job_descriptions.count_documents({"project_id": project_id, "status": "Active"})
    total_jobs = db.job_descriptions.count_documents({"project_id": project_id})
    total_candidates = db.candidates.count_documents({"project_id": project_id})
    current_candidates = db.candidates.count_documents({"project_id": project_id, "bench_status": "On Bench"})
    jd_ids = [int(row.get("id")) for row in db.job_descriptions.find({"project_id": project_id}, {"id": 1}) if row.get("id")]
    interviews = 0
    if jd_ids:
        interviews = db.interviews.count_documents({"jd_id": {"$in": jd_ids}, "status": {"$in": ["Scheduled", "Rescheduled", "Email Sent"]}})
    return {
        **project,
        "active_jobs": active_jobs,
        "total_jobs": total_jobs,
        "current_candidates": current_candidates,
        "total_candidates": total_candidates,
        "interviews": interviews,
        "bench_cards": _bench_cards(project_id),
        "required_role_cards": _required_role_cards(project, project_id),
    }


def get_projects_for_client(client_id: int) -> list[dict]:
    get_default_project_for_client(client_id)
    rows = _serialize_docs(list(_database().projects.find({"client_id": int(client_id)}).sort("created_at", ASCENDING)))
    return [project_summary(row) for row in rows]


def client_summary(client: dict) -> dict:
    db = _database()
    client_id = int(client.get("id") or 0)
    active_jobs = db.job_descriptions.count_documents({"client_id": client_id, "status": "Active"})
    total_jobs = db.job_descriptions.count_documents({"client_id": client_id})
    total_candidates = db.candidates.count_documents({"client_id": client_id})
    upcoming_interviews = 0
    jd_ids = [int(row.get("id")) for row in db.job_descriptions.find({"client_id": client_id}, {"id": 1}) if row.get("id")]
    if jd_ids:
        upcoming_interviews = db.interviews.count_documents({"jd_id": {"$in": jd_ids}, "status": {"$in": ["Scheduled", "Rescheduled", "Email Sent"]}})
    return {
        **client,
        "active_jobs": active_jobs,
        "total_jobs": total_jobs,
        "total_candidates": total_candidates,
        "upcoming_interviews": upcoming_interviews,
    }


def get_client_details(client_id: int) -> Optional[dict]:
    client = get_client_by_id(client_id)
    if not client:
        return None
    projects = get_projects_for_client(client_id)
    return {
        "client": client_summary(client),
        "projects": projects,
    }


def ensure_default_client_and_backfill() -> dict[str, int]:
    default = get_default_client()
    if not default:
        default_id = create_client(
            {
                "client_account_id": DEFAULT_CLIENT_ACCOUNT_ID,
                "name": DEFAULT_CLIENT_NAME,
                "industry": "Technology",
                "website": "https://shimentox.ai/",
                "status": "Active",
                "notes": "Default client account for existing recruitment data.",
            }
        )
        default = get_client_by_id(default_id)
    snapshot = _client_snapshot(default)
    project = get_default_project_for_client(int(snapshot["client_id"]))
    project_fields = _project_snapshot(project)
    db = _database()
    legacy_client_query = {
        "$or": [
            {"client_id": {"$exists": False}},
            {"client_id": None},
            {"client_id": snapshot["client_id"]},
            {"client_account_id": {"$exists": False}},
            {"client_account_id": None},
            {"client_account_id": ""},
            {"client_account_id": DEFAULT_CLIENT_ACCOUNT_ID},
            {"client_name": {"$in": [None, "", DEFAULT_CLIENT_NAME]}},
        ]
    }
    legacy_project_query = {
        "$or": [
            {"project_id": {"$exists": False}},
            {"project_id": None},
            {"project_id": project_fields.get("project_id")},
            {"project_name": {"$exists": False}},
            {"project_name": None},
            {"project_name": ""},
            {"project_name": DEFAULT_PROJECT_NAME},
            {"project_name": {"$in": LEGACY_DEFAULT_PROJECT_NAMES}},
        ]
    }
    jd_result = db.job_descriptions.update_many(
        {"$and": [legacy_client_query, legacy_project_query]},
        {"$set": {**snapshot, **project_fields, "requirement_type": "Required Job"}},
    )
    db.job_descriptions.update_many(
        {"client_account_id": DEFAULT_CLIENT_ACCOUNT_ID, "$or": [{"project_name": {"$in": LEGACY_DEFAULT_PROJECT_NAMES}}, {"project_id": {"$exists": False}}, {"project_id": None}]},
        {"$set": {**project_fields, "requirement_type": "Required Job"}},
    )
    candidate_result = db.candidates.update_many(
        {"$and": [legacy_client_query, legacy_project_query]},
        {"$set": {**snapshot, **project_fields, "worker_type": "Internal", "bench_status": "On Bench"}},
    )
    db.candidates.update_many(
        {"client_account_id": DEFAULT_CLIENT_ACCOUNT_ID, "$or": [{"project_name": {"$in": LEGACY_DEFAULT_PROJECT_NAMES}}, {"project_id": {"$exists": False}}, {"project_id": None}]},
        {"$set": {**project_fields, "worker_type": "Internal", "bench_status": "On Bench"}},
    )
    return {"jobs_updated": jd_result.modified_count, "candidates_updated": candidate_result.modified_count}


# Job descriptions


# Purpose: Fetches all jds from storage or service context.
def get_all_jds(filters: Optional[dict] = None) -> list[dict]:
    filters = filters or {}
    query: dict[str, Any] = {}
    if filters.get("status"):
        query["status"] = filters["status"]
    if filters.get("client_id") is not None:
        query["client_id"] = int(filters["client_id"])
    if filters.get("project_id") is not None:
        query["project_id"] = int(filters["project_id"])
    if filters.get("client_account_id"):
        query["client_account_id"] = str(filters["client_account_id"]).strip().upper()
    if filters.get("search"):
        query.update(_regex_filter(["title", "department", "location", "client_name", "job_category"], str(filters["search"])))
    rows = list(_database().job_descriptions.find(query).sort("created_at", DESCENDING))
    return _serialize_docs(rows)


# Purpose: Fetches jd by id from storage or service context.
def get_jd_by_id(jd_id: int, include_raw_text: bool = False) -> Optional[dict]:
    projection = None if include_raw_text else {"raw_text": 0}
    row = _database().job_descriptions.find_one({"id": int(jd_id)}, projection)
    return _serialize_doc(row)


# Purpose: Creates jd records or payloads.
def create_jd(data: dict) -> int:
    new_id = _next_id("job_descriptions")
    now = _now()
    client_fields = _client_for_data(data)
    project_fields = _project_for_data(data, client_fields)
    doc = {
        "id": new_id,
        "title": data.get("title") or "",
        "department": data.get("department") or "",
        "location": data.get("location") or "",
        "experience_required": data.get("experience_required") or data.get("experience") or "",
        "skills": _list(data.get("skills")),
        "responsibilities": _list(data.get("responsibilities")),
        "structured_data": data.get("structured_data") if isinstance(data.get("structured_data"), dict) else {},
        "raw_text": data.get("raw_text") or "",
        "file_name": data.get("file_name") or data.get("file") or "",
        "status": data.get("status") or "Active",
        "required_candidate_count": _int_or_none(data.get("required_candidate_count")),
        "workflow_status": data.get("workflow_status") or "ACTIVE",
        "workflow_version": int(data.get("workflow_version") or 1),
        "bench_matched_count": int(data.get("bench_matched_count") or 0),
        "bench_analyzed_count": int(data.get("bench_analyzed_count") or 0),
        "bench_qualified_count": int(data.get("bench_qualified_count") or 0),
        "selected_bench_count": int(data.get("selected_bench_count") or 0),
        "accepted_vendor_count": int(data.get("accepted_vendor_count") or 0),
        "remaining_vendor_requirement": int(data.get("remaining_vendor_requirement") or 0),
        "job_category": data.get("job_category") or "",
        "secondary_categories": _list(data.get("secondary_categories")),
        "matched_keywords": _list(data.get("matched_keywords")),
        "categorization_source": data.get("categorization_source") or "",
        "confidence_score": int(data.get("confidence_score") or 0),
        "categorized_date": data.get("categorized_date"),
        "category_reason": data.get("category_reason") or "",
        "sub_tags": _list(data.get("sub_tags")),
        "created_at": now,
        "updated_at": now,
        **client_fields,
        **project_fields,
    }
    _database().job_descriptions.insert_one(doc)
    refresh_dashboard_metrics()
    return new_id


# Purpose: Updates jd records or payloads.
def update_jd(jd_id: int, data: dict) -> bool:
    mapping = {
        "title": "title",
        "department": "department",
        "location": "location",
        "experience_required": "experience_required",
        "experience": "experience_required",
        "skills": "skills",
        "responsibilities": "responsibilities",
        "structured_data": "structured_data",
        "raw_text": "raw_text",
        "file_name": "file_name",
        "file": "file_name",
        "status": "status",
        "required_candidate_count": "required_candidate_count",
        "workflow_status": "workflow_status",
        "workflow_version": "workflow_version",
        "bench_matched_count": "bench_matched_count",
        "bench_analyzed_count": "bench_analyzed_count",
        "bench_qualified_count": "bench_qualified_count",
        "selected_bench_count": "selected_bench_count",
        "accepted_vendor_count": "accepted_vendor_count",
        "remaining_vendor_requirement": "remaining_vendor_requirement",
        "job_category": "job_category",
        "secondary_categories": "secondary_categories",
        "matched_keywords": "matched_keywords",
        "categorization_source": "categorization_source",
        "confidence_score": "confidence_score",
        "categorized_date": "categorized_date",
        "category_reason": "category_reason",
        "sub_tags": "sub_tags",
        "client_id": "client_id",
        "client_account_id": "client_account_id",
        "client_name": "client_name",
        "project_id": "project_id",
        "project_name": "project_name",
    }
    patch: dict[str, Any] = {}
    for key, col in mapping.items():
        if key not in data:
            continue
        value = data[key]
        if col in {"skills", "responsibilities", "secondary_categories", "matched_keywords", "sub_tags"}:
            value = _list(value)
        elif col == "structured_data" and not isinstance(value, dict):
            value = {}
        elif col == "confidence_score":
            value = int(value or 0)
        elif col in {"client_id", "project_id"}:
            value = _int_or_none(value)
        elif col == "required_candidate_count":
            value = _int_or_none(value)
        elif col in {
            "workflow_version",
            "bench_matched_count",
            "bench_analyzed_count",
            "bench_qualified_count",
            "selected_bench_count",
            "accepted_vendor_count",
            "remaining_vendor_requirement",
        }:
            value = int(value or 0)
        patch[col] = value
    if not patch:
        return False
    patch["updated_at"] = _now()
    result = _database().job_descriptions.update_one({"id": int(jd_id)}, {"$set": patch})
    if result.modified_count:
        refresh_dashboard_metrics()
    return result.modified_count > 0


# Purpose: Deletes jd records or payloads.
def delete_jd(jd_id: int) -> bool:
    db = _database()
    result = db.job_descriptions.delete_one({"id": int(jd_id)})
    if result.deleted_count:
        db.comparisons.delete_many({"jd_id": int(jd_id)})
        db.candidates.update_many({"jd_id": int(jd_id)}, {"$set": {"jd_id": None}})
        db.audit_logs.update_many({"jd_id": int(jd_id)}, {"$set": {"jd_id": None}})
        refresh_dashboard_metrics()
    return result.deleted_count > 0


# Purpose: Implements the jd candidate counts backend behavior.
def jd_candidate_counts(jd_id: int) -> dict[str, int]:
    db = _database()
    query = {"jd_id": int(jd_id)}
    total = db.comparisons.count_documents(query)
    selected = db.comparisons.count_documents({**query, "status": "Selected"})
    rejected = db.comparisons.count_documents({**query, "status": "Rejected"})
    return {"selected_count": selected, "rejected_count": rejected, "total_resumes": total}


# Vendors and JD vendor assignments


def _vendor_public_fields(row: dict) -> dict[str, Any]:
    vendor = _serialize_doc(row) or {}
    vendor.setdefault("status", "Active")
    vendor.setdefault("assigned_jds_count", 0)
    vendor.setdefault("candidates_provided_count", 0)
    return vendor


def _vendor_stats(vendor_id: int) -> dict[str, Any]:
    db = _database()
    assignment_query = {"vendor_id": int(vendor_id), "status": "Active"}
    candidate_query = {"source_vendor_id": int(vendor_id)}
    return {
        "assigned_jds_count": db.jd_vendor_assignments.count_documents(assignment_query),
        "candidates_provided_count": db.candidates.count_documents(candidate_query),
    }


def get_all_vendors(filters: Optional[dict] = None) -> list[dict]:
    filters = filters or {}
    query: dict[str, Any] = {"deleted_at": None}
    status = str(filters.get("status") or "").strip()
    if status and status.lower() != "all":
        query["status"] = status
    if filters.get("search"):
        query.update(_regex_filter(["vendor_name", "company_name", "contact_person", "email", "phone"], str(filters["search"])))

    sort_key = str(filters.get("sort") or "company_name").strip()
    sort_map = {
        "vendor_name": ("vendor_name", ASCENDING),
        "company_name": ("company_name", ASCENDING),
        "created_at": ("created_at", DESCENDING),
        "updated_at": ("updated_at", DESCENDING),
        "last_jd_sent_at": ("last_jd_sent_at", DESCENDING),
    }
    field, direction = sort_map.get(sort_key, sort_map["company_name"])
    rows = _serialize_docs(list(_database().vendors.find(query).sort(field, direction)))
    return [{**row, **_vendor_stats(int(row["id"]))} for row in rows]


def get_vendor_by_id(vendor_id: int, include_deleted: bool = False) -> Optional[dict]:
    query: dict[str, Any] = {"id": int(vendor_id)}
    if not include_deleted:
        query["deleted_at"] = None
    row = _database().vendors.find_one(query)
    if not row:
        return None
    vendor = _vendor_public_fields(row)
    return {**vendor, **_vendor_stats(int(vendor["id"]))}


def get_vendor_by_email(email_normalized: str, include_deleted: bool = False) -> Optional[dict]:
    query: dict[str, Any] = {"email_normalized": str(email_normalized or "").strip().lower()}
    if not include_deleted:
        query["deleted_at"] = None
    row = _database().vendors.find_one(query)
    return _vendor_public_fields(row) if row else None


def create_vendor(data: dict) -> int:
    vendor_id = _next_id("vendors")
    now = _now()
    email_normalized = str(data.get("email_normalized") or data.get("email") or "").strip().lower()
    doc = {
        "id": vendor_id,
        "vendor_name": data.get("vendor_name") or data.get("name") or "",
        "company_name": data.get("company_name") or "",
        "contact_person": data.get("contact_person") or "",
        "email": data.get("email") or email_normalized,
        "email_normalized": email_normalized,
        "phone": data.get("phone") or "",
        "status": data.get("status") or "Active",
        "supported_categories": _list(data.get("supported_categories")),
        "supported_sub_tags": _list(data.get("supported_sub_tags")),
        "notes": data.get("notes") or "",
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    try:
        _database().vendors.insert_one(doc)
    except DuplicateKeyError as exc:
        raise ValueError("A vendor with this email already exists.") from exc
    return vendor_id


def update_vendor(vendor_id: int, data: dict) -> bool:
    allowed = {"vendor_name", "company_name", "contact_person", "email", "email_normalized", "phone", "status", "notes", "supported_categories", "supported_sub_tags"}
    patch = {key: data[key] for key in allowed if key in data}
    if "email" in patch and "email_normalized" not in patch:
        patch["email_normalized"] = str(patch["email"] or "").strip().lower()
    for key in ("supported_categories", "supported_sub_tags"):
        if key in patch:
            patch[key] = _list(patch[key])
    if not patch:
        return False
    patch["updated_at"] = _now()
    try:
        result = _database().vendors.update_one({"id": int(vendor_id), "deleted_at": None}, {"$set": patch})
    except DuplicateKeyError as exc:
        raise ValueError("A vendor with this email already exists.") from exc
    return result.modified_count > 0


def soft_delete_vendor(vendor_id: int) -> bool:
    db = _database()
    now = _now()
    result = db.vendors.update_one(
        {"id": int(vendor_id), "deleted_at": None},
        {"$set": {"status": "Inactive", "deleted_at": now, "updated_at": now}},
    )
    if result.modified_count:
        db.jd_vendor_assignments.update_many(
            {"vendor_id": int(vendor_id), "status": "Active"},
            {"$set": {"status": "Removed", "removed_at": now, "updated_at": now}},
        )
    return result.modified_count > 0


def _assignment_summary(assignment: dict, vendor: dict) -> dict[str, Any]:
    return {
        **vendor,
        "assignment_id": assignment.get("id"),
        "assignment_status": assignment.get("status") or "Active",
        "assigned_at": assignment.get("assigned_at"),
        "assigned_by": assignment.get("assigned_by"),
        "assigned_by_username": assignment.get("assigned_by_username") or "",
        "email_status": assignment.get("email_status") or "not_sent",
        "last_email_sent_at": assignment.get("last_email_sent_at"),
        "last_email_log_id": assignment.get("last_email_log_id"),
        "total_required_count": int(assignment.get("total_required_count") or 0),
        "bench_fulfilled_count": int(assignment.get("bench_fulfilled_count") or 0),
        "remaining_requirement_at_assignment": int(assignment.get("remaining_requirement_at_assignment") or 0),
        "allocated_count": int(assignment.get("allocated_count") or 0),
        "accepted_count": int(assignment.get("accepted_count") or 0),
        "assignment_source": assignment.get("assignment_source") or "manual",
        "delivery_status": assignment.get("delivery_status") or assignment.get("email_status") or "not_sent",
    }


def get_jd_vendor_assignments(jd_id: int, include_removed: bool = False) -> list[dict]:
    query: dict[str, Any] = {"jd_id": int(jd_id)}
    if not include_removed:
        query["status"] = "Active"
    rows = _serialize_docs(list(_database().jd_vendor_assignments.find(query).sort("assigned_at", DESCENDING)))
    out = []
    for assignment in rows:
        vendor = get_vendor_by_id(int(assignment.get("vendor_id") or 0), include_deleted=True)
        if vendor:
            out.append(_assignment_summary(assignment, vendor))
    return out


def get_vendor_jd_assignments(vendor_id: int) -> list[dict]:
    rows = _serialize_docs(
        list(
            _database()
            .jd_vendor_assignments.find({"vendor_id": int(vendor_id), "status": "Active"})
            .sort("assigned_at", DESCENDING)
        )
    )
    return rows


def get_active_jd_vendor_assignment(jd_id: int, vendor_id: int) -> Optional[dict]:
    row = _database().jd_vendor_assignments.find_one({"jd_id": int(jd_id), "vendor_id": int(vendor_id), "status": "Active"})
    return _serialize_doc(row)


def assign_vendors_to_jd(jd_id: int, vendor_ids: list[int], assigned_by: Optional[int] = None, assigned_by_username: str = "", allocation: Optional[dict[int, dict[str, Any]]] = None) -> list[dict]:
    db = _database()
    jd_id = int(jd_id)
    wanted = {int(vendor_id) for vendor_id in vendor_ids}
    now = _now()
    active_rows = list(db.jd_vendor_assignments.find({"jd_id": jd_id, "status": "Active"}))
    active_ids = {int(row.get("vendor_id") or 0) for row in active_rows}

    for vendor_id in active_ids - wanted:
        db.jd_vendor_assignments.update_one(
            {"jd_id": jd_id, "vendor_id": vendor_id, "status": "Active"},
            {"$set": {"status": "Removed", "removed_at": now, "updated_at": now}},
        )

    for vendor_id in wanted - active_ids:
        assignment_id = _next_id("jd_vendor_assignments")
        doc = {
            "id": assignment_id,
            "jd_id": jd_id,
            "vendor_id": vendor_id,
            "assigned_by": int(assigned_by) if assigned_by is not None else None,
            "assigned_by_username": assigned_by_username or "",
            "assigned_at": now,
            "status": "Active",
            "email_status": "not_sent",
            "last_email_sent_at": None,
            "last_email_log_id": None,
            "created_at": now,
            "updated_at": now,
            "removed_at": None,
            **(allocation or {}).get(vendor_id, {}),
        }
        try:
            db.jd_vendor_assignments.insert_one(doc)
        except DuplicateKeyError:
            db.jd_vendor_assignments.update_one(
                {"jd_id": jd_id, "vendor_id": vendor_id, "status": "Active"},
                {"$set": {"updated_at": now, **(allocation or {}).get(vendor_id, {})}},
            )
    for vendor_id in wanted & active_ids:
        metadata = (allocation or {}).get(vendor_id)
        if metadata:
            db.jd_vendor_assignments.update_one(
                {"jd_id": jd_id, "vendor_id": vendor_id, "status": "Active"},
                {"$set": {"updated_at": now, **metadata}},
            )
    return get_jd_vendor_assignments(jd_id)


def get_eligible_vendors_for_category(category: str) -> list[dict]:
    rows = _database().vendors.find({"status": "Active", "deleted_at": None, "supported_categories": str(category or "").strip()}).sort("created_at", ASCENDING)
    return _serialize_docs(list(rows))


def assign_jds_to_vendor(vendor_id: int, jd_ids: list[int], assigned_by: Optional[int] = None, assigned_by_username: str = "") -> list[dict]:
    db = _database()
    vendor_id = int(vendor_id)
    wanted = {int(jd_id) for jd_id in jd_ids}
    now = _now()
    active_rows = list(db.jd_vendor_assignments.find({"vendor_id": vendor_id, "status": "Active"}))
    active_ids = {int(row.get("jd_id") or 0) for row in active_rows}

    for jd_id in active_ids - wanted:
        db.jd_vendor_assignments.update_one(
            {"jd_id": jd_id, "vendor_id": vendor_id, "status": "Active"},
            {"$set": {"status": "Removed", "removed_at": now, "updated_at": now}},
        )

    for jd_id in wanted - active_ids:
        assignment_id = _next_id("jd_vendor_assignments")
        doc = {
            "id": assignment_id,
            "jd_id": jd_id,
            "vendor_id": vendor_id,
            "assigned_by": int(assigned_by) if assigned_by is not None else None,
            "assigned_by_username": assigned_by_username or "",
            "assigned_at": now,
            "status": "Active",
            "email_status": "not_sent",
            "last_email_sent_at": None,
            "last_email_log_id": None,
            "created_at": now,
            "updated_at": now,
            "removed_at": None,
        }
        try:
            db.jd_vendor_assignments.insert_one(doc)
        except DuplicateKeyError:
            db.jd_vendor_assignments.update_one(
                {"jd_id": jd_id, "vendor_id": vendor_id, "status": "Active"},
                {"$set": {"updated_at": now}},
            )

    return get_vendor_jd_assignments(vendor_id)


def remove_vendor_assignment(jd_id: int, vendor_id: int) -> bool:
    now = _now()
    result = _database().jd_vendor_assignments.update_one(
        {"jd_id": int(jd_id), "vendor_id": int(vendor_id), "status": "Active"},
        {"$set": {"status": "Removed", "removed_at": now, "updated_at": now}},
    )
    return result.modified_count > 0


def count_vendor_email_attempts(jd_id: int, vendor_id: int) -> int:
    return _database().vendor_email_logs.count_documents({"jd_id": int(jd_id), "vendor_id": int(vendor_id)})


def create_vendor_email_log(data: dict) -> int:
    log_id = _next_id("vendor_email_logs")
    now = data.get("sent_at") or _now()
    doc = {
        "id": log_id,
        "assignment_id": int(data.get("assignment_id") or 0),
        "vendor_id": int(data.get("vendor_id") or 0),
        "jd_id": int(data.get("jd_id") or 0),
        "subject": data.get("subject") or "",
        "body": data.get("body") or "",
        "status": data.get("status") or "failed",
        "sent_by": int(data.get("sent_by") or 0) if data.get("sent_by") is not None else None,
        "sent_by_username": data.get("sent_by_username") or "",
        "sent_at": now,
        "retry_count": int(data.get("retry_count") or 0),
        "error_message": data.get("error_message") or "",
        "created_at": now,
    }
    _database().vendor_email_logs.insert_one(doc)
    return log_id


def update_vendor_assignment_email_status(assignment_id: int, status: str, log_id: int, sent_at: Any = None) -> bool:
    patch: dict[str, Any] = {
        "email_status": status,
        "delivery_status": status,
        "last_email_log_id": int(log_id),
        "updated_at": _now(),
    }
    if status == "sent":
        patch["last_email_sent_at"] = sent_at or _now()
    result = _database().jd_vendor_assignments.update_one({"id": int(assignment_id)}, {"$set": patch})
    return result.modified_count > 0


def get_vendor_email_history(jd_id: int, vendor_id: int) -> list[dict]:
    rows = list(
        _database()
        .vendor_email_logs.find({"jd_id": int(jd_id), "vendor_id": int(vendor_id)})
        .sort("sent_at", DESCENDING)
    )
    return _serialize_docs(rows)


def get_vendor_candidates_for_jd(jd_id: int, vendor_id: int) -> list[dict]:
    rows = list(
        _database()
        .candidates.find({"jd_id": int(jd_id), "source_vendor_id": int(vendor_id)})
        .sort("uploaded_at", DESCENDING)
    )
    return _serialize_docs(rows)


# Purpose: Fetches jds summary list from storage or service context.
def get_jds_summary_list() -> list[dict]:
    out = []
    for row in get_all_jds():
        counts = jd_candidate_counts(int(row["id"]))
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
                "created": created,
                "created_date": created[:10],
                "file": row.get("file_name", ""),
                **counts,
            }
        )
    return out


# Candidates


# Purpose: Fetches all candidates from storage or service context.
def get_all_candidates(filters: Optional[dict] = None) -> list[dict]:
    filters = filters or {}
    query: dict[str, Any] = {}
    if filters.get("status"):
        query["status"] = filters["status"]
    if filters.get("jd_id") is not None:
        query["jd_id"] = int(filters["jd_id"])
    if filters.get("client_id") is not None:
        query["client_id"] = int(filters["client_id"])
    if filters.get("project_id") is not None:
        query["project_id"] = int(filters["project_id"])
    if filters.get("client_account_id"):
        query["client_account_id"] = str(filters["client_account_id"]).strip().upper()
    if filters.get("search"):
        query.update(_regex_filter(["name", "email", "client_name", "primary_category"], str(filters["search"])))
    if filters.get("category"):
        category = str(filters["category"]).strip()
        if category:
            query["$or"] = [{"primary_category": category}, {"secondary_categories": category}]
    rows = list(_database().candidates.find(query).sort("uploaded_at", DESCENDING))
    out = _serialize_docs(rows)
    filter_jd_id = filters.get("jd_id")
    for row in out:
        candidate_jd_id = filter_jd_id if filter_jd_id is not None else row.get("jd_id")
        if candidate_jd_id:
            comparison = _database().comparisons.find_one({"jd_id": int(candidate_jd_id), "candidate_id": int(row.get("id") or 0)}) or {}
            row.update({key: comparison.get(key) for key in ("selection_status", "qualification_status", "candidate_source") if key in comparison})
    return out


def get_available_bench_candidates_for_category(category: str, project_id: Optional[int] = None) -> list[dict]:
    query: dict[str, Any] = {
        "worker_type": "Internal",
        "bench_status": "On Bench",
        "availability_status": {"$in": ["Available", "available", "", None]},
        "primary_category": str(category or "").strip(),
    }
    if project_id is not None:
        query["project_id"] = int(project_id)
    rows = list(_database().candidates.find(query).sort("match_score", DESCENDING))
    return _serialize_docs(rows)


# Purpose: Fetches candidate by id from storage or service context.
def get_candidate_by_id(candidate_id: int) -> Optional[dict]:
    row = _database().candidates.find_one({"id": int(candidate_id)})
    return _serialize_doc(row)


# Purpose: Creates candidate records or payloads.
def create_candidate(data: dict) -> int:
    new_id = _next_id("candidates")
    client_fields = _client_for_data(data)
    project_fields = _project_for_data(data, client_fields)
    if not (data.get("client_id") or data.get("client_account_id")) and data.get("jd_id"):
        jd = get_jd_by_id(int(data["jd_id"]), include_raw_text=False) or {}
        client_fields = {
            "client_id": jd.get("client_id") or client_fields.get("client_id"),
            "client_account_id": jd.get("client_account_id") or client_fields.get("client_account_id"),
            "client_name": jd.get("client_name") or client_fields.get("client_name"),
        }
        project_fields = {
            "project_id": jd.get("project_id") or project_fields.get("project_id"),
            "project_name": jd.get("project_name") or project_fields.get("project_name"),
        }
    doc = {
        "id": new_id,
        "name": data.get("name") or "",
        "email": data.get("email") or "",
        "phone": data.get("phone") or "",
        "applied_roles": _list(data.get("applied_roles")),
        "structured_data": data.get("structured_data") if isinstance(data.get("structured_data"), dict) else {},
        "match_score": int(data.get("match_score") or 0),
        "status": data.get("status") or "Pending",
        "screening_summary": data.get("screening_summary") or "",
        "rejection_reason": data.get("rejection_reason") or "",
        "hiring_stage": data.get("hiring_stage") or "",
        "resume_file": data.get("resume_file") or "",
        "source_vendor_id": _int_or_none(data.get("source_vendor_id")),
        "source_vendor_name": data.get("source_vendor_name") or "",
        "candidate_source": data.get("candidate_source") or ("Vendor" if data.get("source_vendor_id") else "Direct"),
        "uploaded_at": _now(),
        "jd_id": _int_or_none(data.get("jd_id")),
        "worker_type": data.get("worker_type") or "Internal",
        "bench_status": data.get("bench_status") or "On Bench",
        "availability_status": data.get("availability_status") or ("Available" if (data.get("worker_type") or "Internal") == "Internal" else ""),
        "allocation_status": data.get("allocation_status") or ("Bench" if (data.get("worker_type") or "Internal") == "Internal" else ""),
        "primary_category": data.get("primary_category") or "",
        "secondary_categories": _list(data.get("secondary_categories")),
        "matched_keywords": _list(data.get("matched_keywords")),
        "categorization_source": data.get("categorization_source") or "",
        "confidence_score": int(data.get("confidence_score") or 0),
        "categorized_date": data.get("categorized_date"),
        "category_reason": data.get("category_reason") or "",
        "sub_tags": _list(data.get("sub_tags")),
        **client_fields,
        **project_fields,
    }
    _database().candidates.insert_one(doc)
    refresh_dashboard_metrics()
    return new_id


# Purpose: Updates candidate records or payloads.
def update_candidate(candidate_id: int, data: dict) -> bool:
    mapping = {
        "name": "name",
        "email": "email",
        "phone": "phone",
        "applied_roles": "applied_roles",
        "structured_data": "structured_data",
        "match_score": "match_score",
        "status": "status",
        "screening_summary": "screening_summary",
        "rejection_reason": "rejection_reason",
        "hiring_stage": "hiring_stage",
        "resume_file": "resume_file",
        "source_vendor_id": "source_vendor_id",
        "source_vendor_name": "source_vendor_name",
        "candidate_source": "candidate_source",
        "jd_id": "jd_id",
        "client_id": "client_id",
        "client_account_id": "client_account_id",
        "client_name": "client_name",
        "project_id": "project_id",
        "project_name": "project_name",
        "worker_type": "worker_type",
        "bench_status": "bench_status",
        "availability_status": "availability_status",
        "allocation_status": "allocation_status",
        "primary_category": "primary_category",
        "secondary_categories": "secondary_categories",
        "matched_keywords": "matched_keywords",
        "categorization_source": "categorization_source",
        "confidence_score": "confidence_score",
        "categorized_date": "categorized_date",
        "category_reason": "category_reason",
        "sub_tags": "sub_tags",
    }
    patch: dict[str, Any] = {}
    for key, col in mapping.items():
        if key not in data:
            continue
        value = data[key]
        if col == "applied_roles":
            value = _list(value)
        elif col in {"secondary_categories", "matched_keywords", "sub_tags"}:
            value = _list(value)
        elif col == "structured_data" and not isinstance(value, dict):
            value = {}
        elif col in {"match_score", "confidence_score", "jd_id", "client_id", "project_id", "source_vendor_id"}:
            value = _int_or_none(value) if col in {"jd_id", "client_id", "project_id", "source_vendor_id"} else int(value or 0)
        patch[col] = value
    if not patch:
        return False
    result = _database().candidates.update_one({"id": int(candidate_id)}, {"$set": patch})
    if result.modified_count:
        refresh_dashboard_metrics()
    return result.modified_count > 0


# Purpose: Deletes candidate records or payloads.
def delete_candidate(candidate_id: int) -> bool:
    db = _database()
    result = db.candidates.delete_one({"id": int(candidate_id)})
    if result.deleted_count:
        db.comparisons.delete_many({"candidate_id": int(candidate_id)})
        refresh_dashboard_metrics()
    return result.deleted_count > 0


# Purpose: Fetches candidates for jd from storage or service context.
def get_candidates_for_jd(jd_id: int, status: Optional[str] = None) -> list[dict]:
    db = _database()
    query: dict[str, Any] = {"jd_id": int(jd_id)}
    if status:
        query["status"] = status
    comparisons = list(db.comparisons.find(query).sort("comparison_date", DESCENDING))
    out: list[dict] = []
    seen: set[int] = set()

    for comp in comparisons:
        candidate_id = int(comp.get("candidate_id") or 0)
        if not candidate_id:
            continue
        seen.add(candidate_id)
        candidate = db.candidates.find_one({"id": candidate_id}) or {}
        merged = _serialize_doc(candidate) or {}
        comp_doc = _serialize_doc(comp) or {}
        comp_status = comp_doc.get("status") or merged.get("status") or "Pending"
        recommendation = comp_doc.get("recommendation") or ""
        strengths = comp_doc.get("strengths") or []
        gaps = comp_doc.get("gaps") or []
        if not recommendation:
            bits = []
            if strengths:
                bits.append(f"Strengths: {', '.join(str(x) for x in strengths)}")
            if gaps:
                bits.append(f"Gaps: {', '.join(str(x) for x in gaps)}")
            recommendation = "\n".join(bits)
        merged.update(
            {
                "match_score": int(comp_doc.get("match_score") or 0),
                "status": comp_status,
                "screening_summary": recommendation or merged.get("screening_summary", ""),
                "rejection_reason": comp_doc.get("failure_reason") or merged.get("rejection_reason", ""),
                "hiring_stage": "Screening" if comp_status == "Selected" else "Rejected",
                "jd_id": int(jd_id),
                "comparison_id": comp_doc.get("id"),
                "comparison_date": comp_doc.get("comparison_date", ""),
                "strengths": strengths,
                "gaps": gaps,
                "candidate_source": comp_doc.get("candidate_source") or merged.get("candidate_source", ""),
                "selection_status": comp_doc.get("selection_status") or "",
                "qualification_status": comp_doc.get("qualification_status") or "",
                "analysis_run_id": comp_doc.get("analysis_run_id") or "",
                "analysis_error": comp_doc.get("analysis_error") or "",
            }
        )
        out.append(merged)

    # Backward fallback for candidates created before comparison rows existed.
    fallback_query: dict[str, Any] = {"jd_id": int(jd_id)}
    if status:
        fallback_query["status"] = status
    fallback_rows = list(db.candidates.find(fallback_query).sort("uploaded_at", DESCENDING))
    for candidate in fallback_rows:
        candidate_id = int(candidate.get("id") or 0)
        if candidate_id in seen:
            continue
        out.append(_serialize_doc(candidate) or {})
    return out


# Comparisons


# Purpose: Fetches comparisons from storage or service context.
def get_comparisons(jd_id: Optional[int] = None, candidate_id: Optional[int] = None) -> list[dict]:
    db = _database()
    query: dict[str, Any] = {}
    if jd_id is not None:
        query["jd_id"] = int(jd_id)
    if candidate_id is not None:
        query["candidate_id"] = int(candidate_id)
    rows = list(db.comparisons.find(query).sort("comparison_date", DESCENDING))
    out = []
    for row in rows:
        item = _serialize_doc(row) or {}
        jd = db.job_descriptions.find_one({"id": int(item.get("jd_id") or 0)}, {"title": 1})
        cand = db.candidates.find_one({"id": int(item.get("candidate_id") or 0)}, {"name": 1})
        item["jd_title"] = (jd or {}).get("title", "")
        item["candidate_name"] = (cand or {}).get("name", "")
        item["client_id"] = (jd or {}).get("client_id") or (cand or {}).get("client_id")
        item["client_name"] = (jd or {}).get("client_name") or (cand or {}).get("client_name", "")
        out.append(item)
    return out


# Purpose: Implements the upsert comparison backend behavior.
def upsert_comparison(data: dict) -> int:
    db = _database()
    jd_id = int(data["jd_id"])
    candidate_id = int(data["candidate_id"])
    existing = db.comparisons.find_one({"jd_id": jd_id, "candidate_id": candidate_id})
    comparison_id = int(existing["id"]) if existing else _next_id("comparisons")
    raw_date = data.get("comparison_date")
    if isinstance(raw_date, datetime):
        comparison_date = raw_date
    elif raw_date:
        comparison_date = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
    else:
        comparison_date = _now()
    doc = {
        "id": comparison_id,
        "jd_id": jd_id,
        "candidate_id": candidate_id,
        "match_score": int(data.get("match_score") or 0),
        "status": data.get("status") or "Pending",
        "strengths": _list(data.get("strengths")),
        "gaps": _list(data.get("gaps")),
        "recommendation": data.get("recommendation") or "",
        "failure_reason": data.get("failure_reason") or "",
        "candidate_source": data.get("candidate_source") or "",
        "selection_status": data.get("selection_status") or "",
        "qualification_status": data.get("qualification_status") or "",
        "analysis_run_id": data.get("analysis_run_id") or "",
        "analysis_error": data.get("analysis_error") or "",
        "scoring_version": data.get("scoring_version") or "",
        "comparison_date": comparison_date,
    }
    db.comparisons.update_one(
        {"jd_id": jd_id, "candidate_id": candidate_id},
        {"$set": doc},
        upsert=True,
    )
    refresh_dashboard_metrics()
    return comparison_id


# Purpose: Creates comparison records or payloads.
def create_comparison(data: dict) -> int:
    return upsert_comparison(data)


def update_comparison_metadata(jd_id: int, candidate_id: int, data: dict) -> bool:
    allowed = {
        "candidate_source",
        "selection_status",
        "qualification_status",
        "analysis_run_id",
        "analysis_error",
        "scoring_version",
    }
    patch = {key: data[key] for key in allowed if key in data}
    if not patch:
        return False
    result = _database().comparisons.update_one(
        {"jd_id": int(jd_id), "candidate_id": int(candidate_id)},
        {"$set": patch},
    )
    if result.modified_count:
        refresh_dashboard_metrics()
    return result.modified_count > 0


def get_comparison_by_candidate(jd_id: int, candidate_id: int) -> Optional[dict]:
    row = _database().comparisons.find_one({"jd_id": int(jd_id), "candidate_id": int(candidate_id)})
    return _serialize_doc(row)


def count_selected_bench_candidates(jd_id: int) -> int:
    return _database().comparisons.count_documents(
        {
            "jd_id": int(jd_id),
            "candidate_source": "bench",
            "selection_status": "selected_bench",
            "qualification_status": "qualified",
        }
    )


def count_accepted_vendor_candidates(jd_id: int) -> int:
    return _database().comparisons.count_documents(
        {
            "jd_id": int(jd_id),
            "candidate_source": "vendor",
            "selection_status": "accepted_vendor",
        }
    )


def get_jd_audit_events(jd_id: int, limit: int = 50) -> list[dict]:
    rows = list(
        _database()
        .audit_logs.find({"jd_id": int(jd_id)})
        .sort("timestamp", DESCENDING)
        .limit(int(limit or 50))
    )
    return _serialize_docs(rows)


# Interviews


# Purpose: Fetches interviews for recruiter on day from storage or service context.
def get_interviews_for_recruiter_on_day(recruiter_id: int, day_start: datetime, day_end: datetime) -> list[dict]:
    query = {
        "recruiter_id": int(recruiter_id),
        "status": {"$in": ["Scheduled", "Rescheduled", "Email Sent"]},
        "interview_start": {"$lt": day_end},
        "interview_end": {"$gt": day_start},
    }
    rows = list(_database().interviews.find(query).sort("interview_start", ASCENDING))
    return [_normalize_interview_doc(row) for row in rows]


def _normalize_interview_doc(row: dict) -> dict:
    item = _serialize_doc(row) or {}
    if item.get("email_status") in {None, "", "pending"} and (item.get("email_subject") or item.get("email_body") or item.get("to_email")):
        item["email_status"] = "sent"
    if item.get("text_status") in {None, "", "not_configured", "pending"} and item.get("status") in {"Scheduled", "Rescheduled", "Email Sent"}:
        item["text_status"] = "sent"
    if not item.get("followup_status"):
        item["followup_status"] = "not_sent"
    if not item.get("cancellation_status"):
        item["cancellation_status"] = "not_sent"
    return item


def get_interviews(filters: Optional[dict] = None) -> list[dict]:
    filters = filters or {}
    query: dict[str, Any] = {}
    if filters.get("recruiter_id"):
        query["recruiter_id"] = int(filters["recruiter_id"])
    if filters.get("candidate_id"):
        query["candidate_id"] = int(filters["candidate_id"])
    if filters.get("jd_id"):
        query["jd_id"] = int(filters["jd_id"])
    rows = list(_database().interviews.find(query).sort("interview_start", ASCENDING))
    return [_normalize_interview_doc(row) for row in rows]


def get_interviews_for_client(client_id: int) -> list[dict]:
    jd_ids = [
        int(row.get("id"))
        for row in _database().job_descriptions.find({"client_id": int(client_id)}, {"id": 1})
        if row.get("id")
    ]
    if not jd_ids:
        return []
    rows = list(_database().interviews.find({"jd_id": {"$in": jd_ids}}).sort("interview_start", ASCENDING))
    return [_normalize_interview_doc(row) for row in rows]


def get_interview_by_id(interview_id: int) -> Optional[dict]:
    row = _database().interviews.find_one({"id": int(interview_id)})
    return _normalize_interview_doc(row) if row else None


def update_interview(interview_id: int, data: dict) -> bool:
    allowed = {
        "status",
        "interview_start",
        "interview_end",
        "interviewer",
        "interview_mode",
        "meeting_link",
        "notes",
        "email_subject",
        "email_body",
        "text_body",
        "email_status",
        "email_error",
        "email_sent_at",
        "text_status",
        "text_error",
        "text_sent_at",
        "followup_subject",
        "followup_body",
        "followup_status",
        "followup_sent_at",
        "cancellation_type",
        "cancellation_subject",
        "cancellation_body",
        "cancellation_status",
        "cancellation_sent_at",
    }
    patch = {key: value for key, value in (data or {}).items() if key in allowed}
    if not patch:
        return False
    patch["updated_at"] = _now()
    result = _database().interviews.update_one({"id": int(interview_id)}, {"$set": patch})
    if result.modified_count:
        refresh_dashboard_metrics()
    return result.modified_count > 0


# Purpose: Implements the recruiter slot is available backend behavior.
def recruiter_slot_is_available(
    recruiter_id: int,
    interview_start: datetime,
    interview_end: datetime,
    exclude_interview_id: Optional[int] = None,
) -> bool:
    query = {
        "recruiter_id": int(recruiter_id),
        "status": {"$in": ["Scheduled", "Rescheduled", "Email Sent"]},
        "interview_start": {"$lt": interview_end},
        "interview_end": {"$gt": interview_start},
    }
    if exclude_interview_id:
        query["id"] = {"$ne": int(exclude_interview_id)}
    return _database().interviews.count_documents(query) == 0


# Purpose: Creates interview records or payloads.
def create_interview(data: dict) -> int:
    interview_id = _next_id("interviews")
    doc = {
        "id": interview_id,
        "candidate_id": int(data["candidate_id"]),
        "candidate_email": data.get("candidate_email") or "",
        "candidate_name": data.get("candidate_name") or "",
        "jd_id": int(data["jd_id"]),
        "job_role": data.get("job_role") or "",
        "recruiter_id": int(data["recruiter_id"]),
        "recruiter_email": data.get("recruiter_email") or "",
        "interview_start": data["interview_start"],
        "interview_end": data["interview_end"],
        "interviewer": data.get("interviewer") or "",
        "interview_mode": data.get("interview_mode") or "Online",
        "meeting_link": data.get("meeting_link") or "",
        "notes": data.get("notes") or "",
        "text_body": data.get("text_body") or "",
        "from_email": data.get("from_email") or "",
        "to_email": data.get("to_email") or "",
        "email_subject": data.get("email_subject") or "",
        "email_body": data.get("email_body") or "",
        "email_status": data.get("email_status") or "pending",
        "email_error": data.get("email_error") or "",
        "email_sent_at": data.get("email_sent_at"),
        "text_status": data.get("text_status") or "not_configured",
        "text_error": data.get("text_error") or "",
        "text_sent_at": data.get("text_sent_at"),
        "followup_subject": data.get("followup_subject") or "",
        "followup_body": data.get("followup_body") or "",
        "followup_status": data.get("followup_status") or "not_sent",
        "followup_sent_at": data.get("followup_sent_at"),
        "cancellation_type": data.get("cancellation_type") or "",
        "cancellation_subject": data.get("cancellation_subject") or "",
        "cancellation_body": data.get("cancellation_body") or "",
        "cancellation_status": data.get("cancellation_status") or "not_sent",
        "cancellation_sent_at": data.get("cancellation_sent_at"),
        "status": data.get("status") or "Scheduled",
        "created_at": _now(),
        "updated_at": _now(),
    }
    _database().interviews.insert_one(doc)
    refresh_dashboard_metrics()
    return interview_id


# Assessments


def get_assessment_by_id(assessment_id: int) -> Optional[dict]:
    from assessment import repository as assessment_repo

    return assessment_repo.get_assessment_by_id(assessment_id)


def get_assessment_for_candidate_jd(candidate_id: int, jd_id: int) -> Optional[dict]:
    from assessment import repository as assessment_repo

    return assessment_repo.get_latest_assessment_for_candidate_jd(candidate_id, jd_id)


def get_assessments(filters: Optional[dict] = None) -> list[dict]:
    filters = filters or {}
    query: dict[str, Any] = {}
    if filters.get("candidate_id"):
        query["candidate_id"] = int(filters["candidate_id"])
    if filters.get("jd_id"):
        query["jd_id"] = int(filters["jd_id"])
    if filters.get("recruiter_id"):
        query["recruiter_id"] = int(filters["recruiter_id"])
    if filters.get("status"):
        query["status"] = filters["status"]
    rows = list(_database().assessments.find(query).sort("updated_at", DESCENDING))
    return _serialize_docs(rows)


def assessment_allows_scheduling(candidate_id: int, jd_id: int) -> bool:
    from services.assessment_service import is_assessment_passed_for_candidate_jd

    return is_assessment_passed_for_candidate_jd(candidate_id, jd_id)


# Agentic orchestration runs


# Purpose: Creates agent run records or payloads.
def create_agent_run(data: dict) -> int:
    run_id = data.get("run_id") or f"agent_run_{_next_id('agent_runs')}"
    existing = _database().agent_runs.find_one({"run_id": run_id})
    if existing:
        return int(existing.get("id") or 0)
    agent_run_id = _next_id("agent_runs")
    now = _now()
    _database().agent_runs.insert_one(
        {
            "id": agent_run_id,
            "run_id": run_id,
            "task_type": data.get("task_type") or "unknown",
            "status": data.get("status") or "running",
            "username": data.get("username") or "",
            "input": data.get("input") if isinstance(data.get("input"), dict) else {},
            "output": data.get("output") if isinstance(data.get("output"), dict) else {},
            "error": data.get("error") or "",
            "created_at": now,
            "updated_at": now,
        }
    )
    return agent_run_id


# Purpose: Updates agent run records or payloads.
def update_agent_run(run_id: str, data: dict) -> bool:
    patch: dict[str, Any] = {"updated_at": _now()}
    for key in ("task_type", "status", "username", "input", "output", "error"):
        if key in data:
            value = data[key]
            if key in {"input", "output"} and not isinstance(value, dict):
                value = {}
            patch[key] = value
    result = _database().agent_runs.update_one({"run_id": run_id}, {"$set": patch})
    return result.modified_count > 0


# Purpose: Fetches agent run from storage or service context.
def get_agent_run(run_id: str) -> Optional[dict]:
    return _serialize_doc(_database().agent_runs.find_one({"run_id": run_id}))


# Purpose: Fetches agent runs from storage or service context.
def get_agent_runs(filters: Optional[dict] = None) -> list[dict]:
    filters = filters or {}
    query: dict[str, Any] = {}
    if filters.get("task_type"):
        query["task_type"] = str(filters["task_type"])
    if filters.get("username"):
        query["username"] = str(filters["username"])
    rows = list(_database().agent_runs.find(query).sort("created_at", DESCENDING).limit(int(filters.get("limit") or 50)))
    return _serialize_docs(rows)


# Dashboard and reports


def _status_regex(keyword: str) -> dict[str, Any]:
    return {"$regex": keyword, "$options": "i"}


def _dashboard_metrics_from_current_data() -> dict[str, Any]:
    db = _database()
    selected_query = {
        "$or": [
            {"status": _status_regex("selected")},
            {"selection_status": {"$in": ["selected_bench", "accepted_vendor"]}},
        ]
    }
    rejected_query = {
        "$or": [
            {"status": _status_regex("rejected")},
            {"selection_status": "rejected"},
        ]
    }
    selected_count = db.comparisons.count_documents(selected_query)
    rejected_count = db.comparisons.count_documents(rejected_query)
    vendor_submitted = db.comparisons.count_documents({"selection_status": "vendor_submitted"})
    waitlisted = db.comparisons.count_documents({"selection_status": "waitlisted_bench"})
    accepted_vendor = db.comparisons.count_documents({"selection_status": "accepted_vendor"})
    selected_bench = db.comparisons.count_documents({"selection_status": "selected_bench"})
    total_candidates = db.candidates.count_documents({})
    decision_total = selected_count + rejected_count
    return {
        "total_jds": db.job_descriptions.count_documents({}),
        "total_candidates": total_candidates,
        "screened_candidates": decision_total,
        "active_jobs": db.job_descriptions.count_documents({"status": "Active"}),
        "selected_candidates": selected_count,
        "rejected_candidates": rejected_count,
        "submissions": db.comparisons.count_documents({}),
        "client_submissions": selected_count,
        "client_rejections": 0,
        "selected_bench_candidates": selected_bench,
        "waitlisted_bench_candidates": waitlisted,
        "vendor_submitted_candidates": vendor_submitted,
        "accepted_vendor_candidates": accepted_vendor,
        "remaining_vendor_requirement": sum(int(row.get("remaining_vendor_requirement") or 0) for row in db.job_descriptions.find({})),
        "internal_interviews": db.interviews.count_documents({}),
        "external_interviews": 0,
        "selection_rate": int((selected_count / decision_total) * 100) if decision_total else 0,
        "rejection_rate": int((rejected_count / decision_total) * 100) if decision_total else 0,
    }


def refresh_dashboard_metrics() -> dict[str, Any]:
    metrics = _dashboard_metrics_from_current_data()
    doc = {**metrics, "_id": "current", "updated_at": _now()}
    _database().dashboard_metrics.update_one({"_id": "current"}, {"$set": doc}, upsert=True)
    return metrics


# Purpose: Fetches dashboard metrics from storage or service context.
def get_dashboard_metrics() -> dict[str, Any]:
    row = _serialize_doc(_database().dashboard_metrics.find_one({"_id": "current"})) or {}
    if not row:
        return _dashboard_metrics_from_current_data()
    return {k: v for k, v in row.items() if k not in {"updated_at"}}


# Purpose: Fetches jd performance from storage or service context.
def get_jd_performance() -> list[dict]:
    out = []
    for jd in get_all_jds():
        candidates = get_candidates_for_jd(int(jd["id"]))
        applications = len(candidates)
        avg_match = int(sum(int(c.get("match_score") or 0) for c in candidates) / applications) if applications else 0
        out.append(
            {
                "id": jd["id"],
                "title": jd.get("title", ""),
                "applications": applications,
                "avg_match": avg_match,
                "selected": sum(1 for c in candidates if c.get("status") == "Selected" or c.get("selection_status") in {"selected_bench", "accepted_vendor"}),
                "rejected": sum(1 for c in candidates if c.get("status") == "Rejected" or c.get("selection_status") == "rejected"),
                "waitlisted": sum(1 for c in candidates if c.get("selection_status") == "waitlisted_bench"),
                "vendor_submitted": sum(1 for c in candidates if c.get("selection_status") == "vendor_submitted"),
                "remaining_vendor_requirement": int(jd.get("remaining_vendor_requirement") or 0),
            }
        )
    return out


# Purpose: Fetches reports data from storage or service context.
def get_reports_data() -> dict[str, Any]:
    metrics_row = get_dashboard_metrics()
    selected = metrics_row["selected_candidates"]
    rejected = metrics_row["rejected_candidates"]
    total_screened = selected + rejected
    selection_rate = int((selected / total_screened * 100)) if total_screened > 0 else 0

    jd_reports = []
    skill_counts: dict[str, int] = {}
    for jd in get_all_jds():
        candidates = get_candidates_for_jd(int(jd["id"]))
        selected_count = sum(1 for c in candidates if c.get("status") == "Selected" or c.get("selection_status") in {"selected_bench", "accepted_vendor"})
        rejected_count = sum(1 for c in candidates if c.get("status") == "Rejected" or c.get("selection_status") == "rejected")
        avg_match = int(sum(int(c.get("match_score") or 0) for c in candidates) / len(candidates)) if candidates else 0
        jd_reports.append(
            {
                "title": jd.get("title", ""),
                "total_screened": len(candidates),
                "selected": selected_count,
                "rejected": rejected_count,
                "waitlisted": sum(1 for c in candidates if c.get("selection_status") == "waitlisted_bench"),
                "vendor_submitted": sum(1 for c in candidates if c.get("selection_status") == "vendor_submitted"),
                "remaining_vendor_requirement": int(jd.get("remaining_vendor_requirement") or 0),
                "avg_match": avg_match,
            }
        )
        for skill in jd.get("skills") or []:
            skill_counts[str(skill)] = skill_counts.get(str(skill), 0) + 1

    all_candidates = get_all_candidates()
    skill_rows = []
    for skill, jd_count in sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:12]:
        candidate_count = 0
        needle = skill.lower()
        for cand in all_candidates:
            roles = " ".join(str(x) for x in cand.get("applied_roles") or [])
            structured = str(cand.get("structured_data") or {})
            if needle in roles.lower() or needle in structured.lower():
                candidate_count += 1
        skill_rows.append({"name": skill, "jd_count": jd_count, "candidate_count": candidate_count})

    if not skill_rows:
        skill_rows = [
            {"name": "Python", "jd_count": 0, "candidate_count": 0},
            {"name": "SQL", "jd_count": 0, "candidate_count": 0},
        ]

    return {
        "metrics": {
            "total_jobs": metrics_row["total_jds"],
            "total_candidates": metrics_row["total_candidates"],
            "active_jobs": metrics_row["active_jobs"],
            "selection_rate": selection_rate,
            "selected_bench": metrics_row.get("selected_bench_candidates", 0),
            "waitlisted_bench": metrics_row.get("waitlisted_bench_candidates", 0),
            "vendor_submitted": metrics_row.get("vendor_submitted_candidates", 0),
            "accepted_vendor": metrics_row.get("accepted_vendor_candidates", 0),
            "remaining_vendor_requirement": metrics_row.get("remaining_vendor_requirement", 0),
        },
        "jd_reports": jd_reports,
        "funnel": [
            {"name": "Screening Passed", "count": selected},
            {"name": "Recruiter Review", "count": max(0, int(selected * 0.8))},
            {"name": "Technical Interview", "count": max(0, int(selected * 0.5))},
            {"name": "HR Round", "count": max(0, int(selected * 0.3))},
            {"name": "Offer", "count": max(0, int(selected * 0.2))},
            {"name": "Hired", "count": max(0, int(selected * 0.1))},
        ],
        "skill_gaps": skill_rows,
    }


# Audit and users


def _audit_body_hash(previous_hash: str, body: dict[str, Any]) -> str:
    canonical = json.dumps(_serialize_value(body), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{previous_hash}{canonical}".encode("utf-8")).hexdigest()


def _latest_audit_hash() -> str:
    row = _database().audit_logs.find_one({"current_hash": {"$exists": True}}, sort=[("id", DESCENDING)])
    return str((row or {}).get("current_hash") or "")


# Purpose: Implements the log audit backend behavior.
def log_audit(
    action: str,
    username: str,
    details: str = "",
    jd_id: Optional[int] = None,
    *,
    run_id: str = "",
    tool: str = "",
    outcome: str = "",
    params: Optional[dict[str, Any]] = None,
) -> None:
    previous_hash = _latest_audit_hash()
    doc = {
        "id": _next_id("audit_logs"),
        "action": action,
        "username": username or "",
        "details": details or "",
        "jd_id": int(jd_id) if jd_id is not None else None,
        "run_id": run_id or "",
        "tool": tool or "",
        "outcome": outcome or "",
        "params": _redact_audit_params(params or {}),
        "timestamp": _now(),
        "previous_hash": previous_hash,
    }
    doc["current_hash"] = _audit_body_hash(previous_hash, doc)
    _database().audit_logs.insert_one(doc)


def _redact_audit_params(params: dict[str, Any]) -> dict[str, Any]:
    redacted = {}
    secret_markers = ("password", "token", "secret", "key", "smtp", "uri")
    for key, value in (params or {}).items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in secret_markers):
            redacted[key] = "[redacted]"
        elif key in {"file"}:
            redacted[key] = getattr(value, "filename", "[file]")
        else:
            redacted[key] = _serialize_value(value)
    return redacted


def verify_audit_chain() -> dict[str, Any]:
    previous_hash = ""
    checked = 0
    for row in _database().audit_logs.find({"current_hash": {"$exists": True}}).sort("id", ASCENDING):
        current_hash = row.get("current_hash") or ""
        expected_previous = row.get("previous_hash") or ""
        body = {k: v for k, v in row.items() if k not in {"_id", "current_hash"}}
        if expected_previous != previous_hash:
            return {"valid": False, "checked": checked, "broken_id": row.get("id"), "reason": "previous_hash mismatch"}
        expected_hash = _audit_body_hash(previous_hash, body)
        if current_hash != expected_hash:
            return {"valid": False, "checked": checked, "broken_id": row.get("id"), "reason": "current_hash mismatch"}
        previous_hash = current_hash
        checked += 1
    return {"valid": True, "checked": checked, "broken_id": None, "reason": ""}


# Purpose: Implements the replace user session token backend behavior.
def replace_user_session_token(user_id: int, token: str) -> None:
    db = _database()
    db.user_session_tokens.delete_many({"user_id": int(user_id)})
    db.user_session_tokens.insert_one({"token": token, "user_id": int(user_id), "created_at": _now()})


# Purpose: Deletes session token records or payloads.
def delete_session_token(token: str) -> None:
    if token:
        _database().user_session_tokens.delete_one({"token": token})


# Purpose: Implements the user id for session token backend behavior.
def user_id_for_session_token(token: str) -> Optional[int]:
    if not token:
        return None
    row = _database().user_session_tokens.find_one({"token": token})
    if not row:
        return None
    created_at = _coerce_datetime(row.get("created_at"))
    if not created_at or created_at < (_now() - timedelta(seconds=_session_token_ttl_seconds())):
        delete_session_token(token)
        return None
    return int(row["user_id"])


# Purpose: Implements the authenticate user backend behavior.
def authenticate_user(username: str, password: str) -> Optional[dict]:
    row = _database().users.find_one({"username": username})
    if not row or not check_password_hash(row.get("password", ""), password):
        return None
    user = _serialize_doc(row) or {}
    user.pop("password", None)
    return user


# Purpose: Fetches user by id from storage or service context.
def get_user_by_id(user_id: int) -> Optional[dict]:
    row = _database().users.find_one({"id": int(user_id)})
    user = _serialize_doc(row)
    if user:
        user.pop("password", None)
    return user


# Purpose: Updates user profile records or payloads.
def update_user_profile(user_id: int, email: str) -> bool:
    result = _database().users.update_one({"id": int(user_id)}, {"$set": {"email": email}})
    return result.modified_count > 0


# Purpose: Updates user password records or payloads.
def update_user_password(user_id: int, current_password: str, new_password: str) -> bool:
    row = _database().users.find_one({"id": int(user_id)})
    if not row or not check_password_hash(row.get("password", ""), current_password):
        return False
    result = _database().users.update_one(
        {"id": int(user_id)},
        {"$set": {"password": generate_password_hash(new_password)}},
    )
    return result.modified_count > 0


# Purpose: Implements the recent activity backend behavior.
def recent_activity(limit: int = 5) -> dict[str, list]:
    db = _database()
    recent_jds = _serialize_docs(list(db.job_descriptions.find({}).sort("created_at", DESCENDING).limit(limit)))
    for jd in recent_jds:
        created = jd.get("created_at") or jd.get("created") or ""
        jd["created"] = created
        jd["created_date"] = str(created)[:10] if created else ""
    recent_candidates = _serialize_docs(list(db.candidates.find({}).sort("uploaded_at", DESCENDING).limit(limit)))
    recent_comparisons = get_comparisons()[:limit]
    for comp in recent_comparisons:
        comp["date"] = comp.get("comparison_date", "")
    return {
        "recent_jds": recent_jds,
        "recent_candidates": recent_candidates,
        "recent_comparisons": recent_comparisons,
    }


# Purpose: Implements the reset user password backend behavior.
def reset_user_password(username: str, password: str) -> bool:
    result = _database().users.update_one(
        {"username": username},
        {"$set": {"password": generate_password_hash(password)}},
    )
    return result.modified_count > 0
