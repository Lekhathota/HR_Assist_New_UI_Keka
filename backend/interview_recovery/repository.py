"""MongoDB persistence for interview recovery cases and their attempt history.

Collections:
  interview_recovery_cases     one document per recovery case
  interview_recovery_attempts  append-only history of messages and actions
  interview_recovery_locks     short-lived booking locks per recruiter

Concurrency: every state change the scheduler makes starts with an atomic
find_one_and_update "claim" guarded by a lease. A worker that dies mid-case
leaves a PROCESSING case whose lease expires, so the next run resumes it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

import database as db
from interview_recovery.models import RecoveryStatus


def _database():
    db.init_pool()
    return db.get_database()


def _aware(value: Any) -> Any:
    """PyMongo returns naive UTC datetimes; make case timestamps comparable."""
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _case(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    return {key: _aware(value) for key, value in doc.items() if key != "_id"}


def ensure_indexes() -> None:
    mongo = db.get_database()
    mongo.interview_recovery_cases.create_index([("id", ASCENDING)], unique=True)
    # At most one open case per interview and recovery type: duplicate events
    # (double clicks, repeated detection runs) collapse onto the same case.
    mongo.interview_recovery_cases.create_index(
        [("interview_id", ASCENDING), ("recovery_type", ASCENDING)],
        unique=True, name="one_open_case_per_interview_type",
        partialFilterExpression={"is_open": True},
    )
    mongo.interview_recovery_cases.create_index([("status", ASCENDING), ("next_action_at", ASCENDING)])
    mongo.interview_recovery_cases.create_index([("status", ASCENDING), ("response_deadline", ASCENDING)])
    mongo.interview_recovery_cases.create_index([("recruiter_id", ASCENDING), ("status", ASCENDING)])
    mongo.interview_recovery_attempts.create_index([("id", ASCENDING)], unique=True)
    mongo.interview_recovery_attempts.create_index([("case_id", ASCENDING), ("created_at", ASCENDING)])
    mongo.interview_recovery_locks.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    mongo.interviews.create_index(
        [("candidate_access_token", ASCENDING)], unique=True, name="interview_candidate_token",
        partialFilterExpression={"candidate_access_token": {"$type": "string"}},
    )


def create_case(doc: dict) -> tuple[dict, bool]:
    """Insert an open case. Returns (case, created); an existing open case wins."""
    mongo = _database()
    row = {**doc, "id": db._next_id("interview_recovery_cases"), "is_open": True}
    try:
        mongo.interview_recovery_cases.insert_one(row)
        return _case(row), True
    except DuplicateKeyError:
        existing = get_open_case(int(doc["interview_id"]), doc["recovery_type"])
        if existing is None:
            raise
        return existing, False


def get_case(case_id: int) -> Optional[dict]:
    return _case(_database().interview_recovery_cases.find_one({"id": int(case_id)}))


def get_open_case(interview_id: int, recovery_type: Optional[str] = None) -> Optional[dict]:
    query: dict[str, Any] = {"interview_id": int(interview_id), "is_open": True}
    if recovery_type:
        query["recovery_type"] = recovery_type
    return _case(_database().interview_recovery_cases.find_one(query, sort=[("created_at", DESCENDING)]))


def case_exists_for_occurrence(interview_id: int, recovery_type: str, interview_start: datetime) -> bool:
    """True when this exact interview occurrence already produced a case (open or not)."""
    return _database().interview_recovery_cases.count_documents({
        "interview_id": int(interview_id), "recovery_type": recovery_type,
        "original_interview_start": interview_start,
    }, limit=1) > 0


def latest_cases_for_interviews(interview_ids: list[int]) -> dict[int, dict]:
    if not interview_ids:
        return {}
    rows = _database().interview_recovery_cases.find(
        {"interview_id": {"$in": [int(i) for i in interview_ids]}}
    ).sort("created_at", ASCENDING)
    latest: dict[int, dict] = {}
    for row in rows:
        latest[int(row["interview_id"])] = _case(row)
    return latest


def list_cases(*, recruiter_id: Optional[int] = None, statuses: Optional[list[str]] = None, limit: int = 100) -> list[dict]:
    query: dict[str, Any] = {}
    if recruiter_id is not None:
        query["recruiter_id"] = int(recruiter_id)
    if statuses:
        query["status"] = {"$in": list(statuses)}
    rows = _database().interview_recovery_cases.find(query).sort("updated_at", DESCENDING).limit(max(1, min(limit, 500)))
    return [_case(row) for row in rows]


def update_case(case_id: int, patch: dict, *, expected_status: Optional[str] = None) -> bool:
    query: dict[str, Any] = {"id": int(case_id)}
    if expected_status:
        query["status"] = expected_status
    values = dict(patch)
    if "status" in values:
        values["is_open"] = values["status"] in RecoveryStatus.OPEN
    values["updated_at"] = datetime.now(timezone.utc)
    return _database().interview_recovery_cases.update_one(query, {"$set": values}).modified_count > 0


def claim_case(case_id: int, from_statuses: set[str] | frozenset[str], now: datetime, lease_seconds: int) -> Optional[dict]:
    """Atomically move a case to PROCESSING if it is in one of from_statuses."""
    row = _database().interview_recovery_cases.find_one_and_update(
        {"id": int(case_id), "status": {"$in": list(from_statuses)}},
        [{"$set": {
            "resume_from": {"$cond": [{"$eq": ["$status", RecoveryStatus.PROCESSING]}, "$resume_from", "$status"]},
            "status": RecoveryStatus.PROCESSING,
            "is_open": True,
            "lease_until": now + timedelta(seconds=lease_seconds),
            "updated_at": now,
        }}],
        return_document=ReturnDocument.AFTER,
    )
    return _case(row)


def claim_next_due_case(now: datetime, lease_seconds: int) -> Optional[dict]:
    """Claim one case whose retry, response deadline or stale lease is due."""
    due = {"$or": [
        {"status": {"$in": [RecoveryStatus.PENDING, RecoveryStatus.RETRY_SCHEDULED]}, "next_action_at": {"$lte": now}},
        {"status": {"$in": [RecoveryStatus.AWAITING_RESPONSE, RecoveryStatus.SLOT_PROPOSED]}, "response_deadline": {"$lte": now}},
        {"status": RecoveryStatus.PROCESSING, "lease_until": {"$lte": now}},
    ]}
    row = _database().interview_recovery_cases.find_one_and_update(
        due,
        [{"$set": {
            "resume_from": {"$cond": [{"$eq": ["$status", RecoveryStatus.PROCESSING]}, "$resume_from", "$status"]},
            "status": RecoveryStatus.PROCESSING,
            "lease_until": now + timedelta(seconds=lease_seconds),
            "updated_at": now,
        }}],
        sort=[("next_action_at", ASCENDING)],
        return_document=ReturnDocument.AFTER,
    )
    return _case(row)


def mark_escalated(case_id: int, now: datetime, reason: str, recommended_action: str) -> bool:
    """Escalate once: only the first call for an unescalated case succeeds."""
    result = _database().interview_recovery_cases.update_one(
        {"id": int(case_id), "escalated_at": None},
        {"$set": {
            "status": RecoveryStatus.ESCALATED, "is_open": True, "escalated_at": now,
            "escalation_reason": reason, "recommended_action": recommended_action,
            "next_action_at": None, "response_deadline": None, "lease_until": None, "updated_at": now,
        }},
    )
    return result.modified_count > 0


def add_attempt(doc: dict) -> int:
    attempt_id = db._next_id("interview_recovery_attempts")
    _database().interview_recovery_attempts.insert_one({**doc, "id": attempt_id, "created_at": datetime.now(timezone.utc)})
    return attempt_id


def list_attempts(case_id: int) -> list[dict]:
    rows = _database().interview_recovery_attempts.find({"case_id": int(case_id)}).sort("created_at", ASCENDING)
    return [_case(row) for row in rows]


def set_interview_fields(interview_id: int, fields: dict) -> bool:
    """Recovery-owned interview fields (token hash, attendance) outside update_interview's allow-list."""
    fields = {**fields, "updated_at": datetime.now(timezone.utc)}
    return _database().interviews.update_one({"id": int(interview_id)}, {"$set": fields}).matched_count > 0


def find_interview_by_token(token: str) -> Optional[dict]:
    row = _database().interviews.find_one({"candidate_access_token": token})
    return {k: v for k, v in row.items() if k != "_id"} if row else None


def raw_interview(interview_id: int) -> Optional[dict]:
    """Interview with native datetimes (the normalized form serializes them)."""
    row = _database().interviews.find_one({"id": int(interview_id)})
    return {k: v for k, v in row.items() if k != "_id"} if row else None


def interviews_due_for_no_show_check(window_start: datetime, window_end: datetime, statuses: list[str]) -> list[dict]:
    rows = _database().interviews.find({
        "status": {"$in": statuses},
        "interview_start": {"$gte": window_start, "$lte": window_end},
        "attendance_status": {"$ne": "attended"},
    })
    return [{k: v for k, v in row.items() if k != "_id"} for row in rows]


def acquire_lock(key: str, owner: str, now: datetime, seconds: int) -> bool:
    mongo = _database()
    try:
        result = mongo.interview_recovery_locks.find_one_and_update(
            {"_id": key, "$or": [{"expires_at": {"$lte": now}}, {"owner": owner}]},
            {"$set": {"owner": owner, "expires_at": now + timedelta(seconds=seconds)}},
            upsert=True, return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        return False
    return bool(result and result.get("owner") == owner)


def release_lock(key: str, owner: str) -> None:
    _database().interview_recovery_locks.delete_one({"_id": key, "owner": owner})
