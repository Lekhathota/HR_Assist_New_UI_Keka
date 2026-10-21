"""
MongoDB persistence layer for the Assessment module.

Uses the shared Recruitment Assist database connection and counter sequences.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure

import activity_feed
import database as db
from assessment.models import CUSTOM_CODING_FIELDS, AssessmentStatus
from assessment.utilities import utc_now


def _database():
    db.init_pool()
    return db.get_database()


def _now() -> datetime:
    return utc_now()


def _next_id(name: str) -> int:
    row = _database().counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(row["seq"])


def _serialize_doc(doc: Optional[dict]) -> Optional[dict]:
    from database import _serialize_doc as serialize

    return serialize(doc)


def _serialize_docs(rows: list[dict]) -> list[dict]:
    from database import _serialize_docs as serialize_many

    return serialize_many(rows)


def ensure_assessment_indexes() -> None:
    """Create indexes for assessment collections. Called from database._ensure_indexes()."""
    mongo = db.get_database()
    mongo.assessments.create_index([("id", ASCENDING)], unique=True)
    try:
        mongo.assessments.create_index([("candidate_id", ASCENDING), ("jd_id", ASCENDING)])
    except OperationFailure:
        mongo.assessments.drop_index("candidate_id_1_jd_id_1")
        mongo.assessments.create_index([("candidate_id", ASCENDING), ("jd_id", ASCENDING)])
    mongo.assessments.create_index([("access_token", ASCENDING)], unique=True, sparse=True)
    mongo.assessments.create_index([("status", ASCENDING), ("updated_at", DESCENDING)])
    # Empty strings violate the sparse unique index; drafts should omit the field until send.
    mongo.assessments.update_many({"access_token": ""}, {"$unset": {"access_token": ""}})

    mongo.questions.create_index([("id", ASCENDING)], unique=True)
    mongo.questions.create_index([("assessment_id", ASCENDING), ("sort_order", ASCENDING)])
    # A generated question saved twice (double click, network retry) is stored once.
    mongo.questions.create_index([("assessment_id", ASCENDING), ("client_request_id", ASCENDING)], unique=True,
                                 partialFilterExpression={"client_request_id": {"$type": "string"}})

    mongo.candidate_answers.create_index([("id", ASCENDING)], unique=True)
    mongo.candidate_answers.create_index(
        [("assessment_id", ASCENDING), ("question_id", ASCENDING)],
        unique=True,
    )

    mongo.assessment_results.create_index([("id", ASCENDING)], unique=True)
    mongo.assessment_results.create_index([("assessment_id", ASCENDING)], unique=True)
    mongo.assessment_versions.create_index([("assessment_id", ASCENDING), ("version", ASCENDING)], unique=True)
    mongo.assessment_code_attempts.create_index([("assessment_id", ASCENDING), ("question_id", ASCENDING), ("created_at", ASCENDING)])
    # One in-flight "generate & send" per candidate and JD (see claim_send_request).
    mongo.assessment_send_requests.create_index([("candidate_id", ASCENDING), ("jd_id", ASCENDING)], unique=True)

    from assessment.proctoring_media import ensure_proctoring_indexes
    ensure_proctoring_indexes()


def sync_assessment_counters() -> None:
    mongo = _database()
    for name in ("assessments", "questions", "candidate_answers", "assessment_results"):
        row = mongo[name].find_one({}, sort=[("id", DESCENDING)])
        if row and row.get("id") is not None:
            db._ensure_counter_at_least(name, int(row["id"]))


# Assessments


def create_assessment(data: dict[str, Any]) -> int:
    assessment_id = _next_id("assessments")
    doc = {
        "id": assessment_id,
        "candidate_id": int(data["candidate_id"]),
        "jd_id": int(data["jd_id"]),
        "recruiter_id": int(data["recruiter_id"]),
        "status": data.get("status") or AssessmentStatus.DRAFT,
        "title": data.get("title") or "",
        "candidate_name": data.get("candidate_name") or "",
        "candidate_email": data.get("candidate_email") or "",
        "job_role": data.get("job_role") or "",
        "experience_required": data.get("experience_required") or "Not specified",
        "passing_score": int(data.get("passing_score") or 70),
        "time_limit_minutes": int(data.get("time_limit_minutes") or 60),
        "sent_at": data.get("sent_at"),
        "started_at": data.get("started_at"),
        "completed_at": data.get("completed_at"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    # Optional provenance for assessments sent outside the normal screening flow.
    for key in ("source", "screening_override", "initiated_by"):
        if data.get(key) is not None:
            doc[key] = data[key]
    token = str(data.get("access_token") or "").strip()
    if token:
        doc["access_token"] = token
    if data.get("token_expires_at") is not None:
        doc["token_expires_at"] = data.get("token_expires_at")
    _database().assessments.insert_one(doc)
    activity_feed.emit("assessment", assessment_id=assessment_id, jd_id=doc["jd_id"], name=doc["candidate_name"],
                       status="CREATED" if doc["status"] in (AssessmentStatus.DRAFT, AssessmentStatus.DRAFT.value) else str(getattr(doc["status"], "value", doc["status"])))
    return assessment_id


def get_assessment_by_id(assessment_id: int) -> Optional[dict]:
    return _serialize_doc(_database().assessments.find_one({"id": int(assessment_id)}))


def get_assessment_by_token(token: str) -> Optional[dict]:
    return _serialize_doc(_database().assessments.find_one({"access_token": str(token).strip()}))


def get_active_assessment_for_candidate_jd(candidate_id: int, jd_id: int) -> Optional[dict]:
    terminal = list(AssessmentStatus.terminal_states())
    doc = _database().assessments.find_one(
        {
            "candidate_id": int(candidate_id),
            "jd_id": int(jd_id),
            "status": {"$nin": terminal},
        },
        sort=[("created_at", DESCENDING)],
    )
    return _serialize_doc(doc)


def get_latest_assessment_for_candidate_jd(candidate_id: int, jd_id: int) -> Optional[dict]:
    """Most recent assessment for a candidate/JD pair, including terminal states."""
    doc = _database().assessments.find_one(
        {"candidate_id": int(candidate_id), "jd_id": int(jd_id)},
        sort=[("created_at", DESCENDING)],
    )
    return _serialize_doc(doc)


def get_latest_assessments_for_jd(jd_id: int) -> list[dict]:
    """Latest assessment per candidate for a job description."""
    mongo = _database()
    rows = list(
        mongo.assessments.find({"jd_id": int(jd_id)}).sort([("candidate_id", 1), ("created_at", DESCENDING)])
    )
    latest_by_candidate: dict[int, dict] = {}
    for row in rows:
        candidate_id = int(row.get("candidate_id") or 0)
        if candidate_id and candidate_id not in latest_by_candidate:
            latest_by_candidate[candidate_id] = _serialize_doc(row) or {}
    return list(latest_by_candidate.values())


def get_recent_questions_for_jd(jd_id: int, limit: int = 50) -> list[dict]:
    """Recent questions generated for any assessment tied to this JD."""
    mongo = _database()
    assessment_ids = [
        int(row["id"])
        for row in mongo.assessments.find({"jd_id": int(jd_id)}, {"id": 1}).sort("created_at", DESCENDING)
        if row.get("id") is not None
    ]
    if not assessment_ids:
        return []
    rows = list(
        mongo.questions.find({"assessment_id": {"$in": assessment_ids}})
        .sort([("created_at", DESCENDING), ("id", DESCENDING)])
        .limit(int(limit))
    )
    return _serialize_docs(rows)


def update_assessment(assessment_id: int, patch: dict[str, Any]) -> bool:
    allowed = {
        "status",
        "title",
        "access_token",
        "token_expires_at",
        "passing_score",
        "time_limit_minutes",
        "sent_at",
        "started_at",
        "completed_at",
        "candidate_email",
        "terms_accepted_at",
        "terms_version",
        "email_delivery_status",
        "email_delivery_error",
        "email_sent_at",
        "send_request_id",
        "coding_specs",
        "client_coding_prompt",
    }
    update_doc: dict[str, Any] = {}
    unset_doc: dict[str, int] = {}
    for key, value in patch.items():
        if key not in allowed:
            continue
        if key == "access_token" and not str(value or "").strip():
            unset_doc["access_token"] = 1
            continue
        update_doc[key] = value
    if not update_doc and not unset_doc:
        return False
    update_doc["updated_at"] = _now()
    mongo = _database()
    before = mongo.assessments.find_one(
        {"id": int(assessment_id)}, {"status": 1, "jd_id": 1, "candidate_name": 1}
    ) if "status" in update_doc else None
    if update_doc and unset_doc:
        result = mongo.assessments.update_one(
            {"id": int(assessment_id)},
            {"$set": update_doc, "$unset": unset_doc},
        )
    elif unset_doc:
        result = mongo.assessments.update_one({"id": int(assessment_id)}, {"$unset": unset_doc, "$set": update_doc})
    else:
        result = mongo.assessments.update_one({"id": int(assessment_id)}, {"$set": update_doc})
    if result.modified_count and before is not None:
        new_status = str(getattr(update_doc["status"], "value", update_doc["status"]))
        if str(getattr(before.get("status"), "value", before.get("status"))) != new_status:
            activity_feed.emit("assessment", assessment_id=int(assessment_id), jd_id=before.get("jd_id"),
                               name=before.get("candidate_name") or "", status=new_status)
    return result.modified_count > 0


def push_delivery_event(assessment_id: int, event: dict[str, Any]) -> None:
    """Append-only email delivery history shown to recruiters."""
    _database().assessments.update_one(
        {"id": int(assessment_id)},
        {"$push": {"delivery_history": {**event, "at": _now()}}, "$set": {"updated_at": _now()}},
    )


def get_assessments_for_candidate(candidate_id: int) -> list[dict]:
    rows = _database().assessments.find({"candidate_id": int(candidate_id)}).sort("created_at", DESCENDING)
    return _serialize_docs(list(rows))


def claim_send_request(candidate_id: int, jd_id: int, request_id: str, lease_seconds: int) -> Optional[dict]:
    """Atomically take the candidate/JD send lease; None while another request holds it."""
    now = _now()
    try:
        row = _database().assessment_send_requests.find_one_and_update(
            {"candidate_id": int(candidate_id), "jd_id": int(jd_id),
             "$or": [{"lease_until": {"$lte": now}}, {"lease_until": None}]},
            {"$set": {"request_id": request_id, "state": "processing", "lease_until": now + timedelta(seconds=lease_seconds),
                      "updated_at": now},
             "$setOnInsert": {"created_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        return None
    return _serialize_doc(row)


def finish_send_request(candidate_id: int, jd_id: int, request_id: str, *, state: str, error: str = "",
                        assessment_id: int | None = None) -> None:
    """Release the lease and remember the outcome (generation failures have no assessment row)."""
    _database().assessment_send_requests.update_one(
        {"candidate_id": int(candidate_id), "jd_id": int(jd_id), "request_id": request_id},
        {"$set": {"state": state, "last_error": error, "assessment_id": assessment_id,
                  "lease_until": _now(), "updated_at": _now()}},
    )


def get_send_requests_for_candidate(candidate_id: int) -> list[dict]:
    return _serialize_docs(list(_database().assessment_send_requests.find({"candidate_id": int(candidate_id)})))


def activate_assessment(assessment_id: int, expected_status: str, patch_doc: dict[str, Any]) -> bool:
    """Apply patch_doc only if the assessment is still in expected_status (prevents duplicate sends)."""
    status = getattr(expected_status, "value", expected_status)
    doc = {k: getattr(v, "value", v) for k, v in patch_doc.items()}
    row = _database().assessments.find_one_and_update(
        {"id": int(assessment_id), "status": status}, {"$set": {**doc, "updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    return bool(row)


def return_assessment_to_draft(assessment_id: int) -> bool:
    """SENT -> DRAFT only while the candidate has not started (atomic against begin_candidate_attempt)."""
    row = _database().assessments.find_one_and_update(
        {"id": int(assessment_id), "status": AssessmentStatus.SENT, "started_at": {"$in": [None]}},
        {"$set": {"status": AssessmentStatus.DRAFT, "approval": None, "updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    return bool(row)


def begin_candidate_attempt(assessment_id: int) -> Optional[dict]:
    """Only the first start sets the clock; concurrent starts cannot reset it."""
    row = _database().assessments.find_one_and_update(
        {"id": int(assessment_id), "status": AssessmentStatus.SENT},
        {"$set": {"status": AssessmentStatus.IN_PROGRESS, "started_at": _now(), "updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    if row:
        activity_feed.emit("assessment", assessment_id=int(assessment_id), jd_id=row.get("jd_id"),
                           name=row.get("candidate_name") or "", status="IN_PROGRESS")
    return _serialize_doc(row or _database().assessments.find_one({"id": int(assessment_id)}))


def record_proctoring_violation(assessment_id: int, event_id: str, reason: str) -> Optional[dict]:
    """Count each incident once and close the attempt atomically on incident two."""
    now = _now()
    row = _database().assessments.find_one_and_update(
        {"id": int(assessment_id), "status": AssessmentStatus.IN_PROGRESS,
         "proctoring_events.event_id": {"$ne": event_id}},
        [
            {"$set": {
                "proctoring_violation_count": {"$add": [{"$ifNull": ["$proctoring_violation_count", 0]}, 1]},
                "proctoring_events": {"$concatArrays": [{"$ifNull": ["$proctoring_events", []]},
                    {"$literal": [{"event_id": event_id, "reason": reason, "recorded_at": now}]}]},
                "updated_at": now,
            }},
            {"$set": {
                "status": {"$cond": [{"$gte": ["$proctoring_violation_count", 2]},
                    AssessmentStatus.TERMINATED, "$status"]},
                "completed_at": {"$cond": [{"$gte": ["$proctoring_violation_count", 2]}, now, "$completed_at"]},
                "termination_reason": {"$cond": [{"$gte": ["$proctoring_violation_count", 2]},
                    "Two exam navigation or focus violations", "$termination_reason"]},
            }},
        ],
        return_document=ReturnDocument.AFTER,
    )
    if row and row.get("status") == AssessmentStatus.TERMINATED:
        activity_feed.emit("assessment", assessment_id=int(assessment_id), jd_id=row.get("jd_id"),
                           name=row.get("candidate_name") or "", status="TERMINATED")
    return _serialize_doc(row or _database().assessments.find_one({"id": int(assessment_id)}))


def complete_candidate_attempt(assessment_id: int) -> bool:
    """Submission cannot overwrite an attempt terminated by a concurrent violation."""
    result = _database().assessments.update_one(
        {"id": int(assessment_id), "status": AssessmentStatus.IN_PROGRESS,
         "$and": [
             {"$or": [{"proctoring_violation_count": {"$lt": 2}}, {"proctoring_violation_count": {"$exists": False}}]},
             {"$or": [{"face_violation_count": {"$lt": 2}}, {"face_violation_count": {"$exists": False}}]},
         ]},
        {"$set": {"status": AssessmentStatus.COMPLETED, "completed_at": _now(), "updated_at": _now()}},
    )
    return result.modified_count > 0


def delete_assessment_cascade(assessment_id: int) -> None:
    mongo = _database()
    aid = int(assessment_id)
    mongo.questions.delete_many({"assessment_id": aid})
    mongo.candidate_answers.delete_many({"assessment_id": aid})
    mongo.assessment_results.delete_many({"assessment_id": aid})
    mongo.assessment_versions.delete_many({"assessment_id": aid})
    mongo.assessment_code_attempts.delete_many({"assessment_id": aid})
    mongo.assessments.delete_one({"id": aid})
    from assessment.proctoring_media import delete_assessment_media
    delete_assessment_media(aid)


# Questions

# Test-case data for automatically graded coding / SQL questions.
EXECUTABLE_QUESTION_FIELDS = (
    "test_cases", "sql_schema", "order_matters", "input_format", "output_format",
    "allowed_languages", "default_language", "tests_verified",
    "reference_language", "verification", "config_fingerprint",
    # Coding configuration (assessment/code_execution/coding_config.py)
    "title", "edge_cases", "time_limit_seconds", "memory_limit_mb", "comparison", "scoring", "reference_solutions",
)


def create_question(data: dict[str, Any]) -> int:
    question_id = _next_id("questions")
    doc = {
        "id": question_id,
        "assessment_id": int(data["assessment_id"]),
        "question_text": data.get("question_text") or "",
        "question_type": data.get("question_type") or "mcq",
        "options": list(data.get("options") or []),
        "correct_answer": data.get("correct_answer") or "",
        "starter_code": data.get("starter_code") or "",
        "points": int(data.get("points") or 10),
        "skill_tag": data.get("skill_tag") or "",
        **{key: data.get(key) for key in ("question_id", "difficulty", "scenario_type", "explanation", "evaluation_focus", "jd_requirement") if data.get(key) is not None},
        **{key: data.get(key) for key in EXECUTABLE_QUESTION_FIELDS if data.get(key) is not None},
        **{key: data.get(key) for key in CUSTOM_CODING_FIELDS if data.get(key) is not None},
        "sort_order": int(data.get("sort_order") or 0),
        "created_at": _now(),
        "updated_at": _now(),
    }
    _database().questions.insert_one(doc)
    return question_id


def create_questions_bulk(rows: list[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    for row in rows:
        ids.append(create_question(row))
    return ids


def get_question_by_id(question_id: int) -> Optional[dict]:
    return _serialize_doc(_database().questions.find_one({"id": int(question_id)}))


def get_questions_for_assessment(assessment_id: int) -> list[dict]:
    rows = list(
        _database()
        .questions.find({"assessment_id": int(assessment_id)})
        .sort([("sort_order", ASCENDING), ("id", ASCENDING)])
    )
    return _serialize_docs(rows)


def update_question(question_id: int, patch: dict[str, Any]) -> bool:
    allowed = {
        "question_text",
        "question_type",
        "options",
        "correct_answer",
        "starter_code",
        "points",
        "skill_tag",
        "sort_order",
        *EXECUTABLE_QUESTION_FIELDS,
        *CUSTOM_CODING_FIELDS,
        "difficulty", "scenario_type", "explanation", "evaluation_focus", "jd_requirement",
    }
    update_doc: dict[str, Any] = {}
    for key, value in patch.items():
        if key in allowed:
            update_doc[key] = value
    if not update_doc:
        return False
    update_doc["updated_at"] = _now()
    result = _database().questions.update_one({"id": int(question_id)}, {"$set": update_doc})
    return result.modified_count > 0


def update_question_if_unchanged(question_id: int, expected_fingerprint: str, patch: dict[str, Any]) -> bool:
    """Write verification results only if the solution/tests were not edited meanwhile."""
    result = _database().questions.update_one(
        {"id": int(question_id), "$or": [{"config_fingerprint": expected_fingerprint},
                                         {"config_fingerprint": {"$exists": False}},
                                         {"config_fingerprint": None}]},
        {"$set": {**patch, "updated_at": _now()}},
    )
    return result.matched_count > 0


def delete_question(question_id: int) -> bool:
    mongo = _database()
    qid = int(question_id)
    question = mongo.questions.find_one({"id": qid})
    if not question:
        return False
    mongo.candidate_answers.delete_many({"question_id": qid})
    result = mongo.questions.delete_one({"id": qid})
    return result.deleted_count > 0


def count_questions_for_assessment(assessment_id: int) -> int:
    return int(_database().questions.count_documents({"assessment_id": int(assessment_id)}))


# Candidate answers


def upsert_candidate_answer(
    assessment_id: int,
    question_id: int,
    answer: str,
    *,
    is_final: bool = False,
    language: Optional[str] = None,
) -> int:
    mongo = _database()
    existing = mongo.candidate_answers.find_one(
        {"assessment_id": int(assessment_id), "question_id": int(question_id)}
    )
    now = _now()
    if existing:
        mongo.candidate_answers.update_one(
            {"id": int(existing["id"])},
            {"$set": {"answer": answer, "is_final": is_final, "updated_at": now,
                      **({"language": language} if language else {})}},
        )
        return int(existing["id"])

    answer_id = _next_id("candidate_answers")
    mongo.candidate_answers.insert_one(
        {
            "id": answer_id,
            "assessment_id": int(assessment_id),
            "question_id": int(question_id),
            "answer": answer,
            "is_final": is_final,
            **({"language": language} if language else {}),
            "created_at": now,
            "updated_at": now,
        }
    )
    return answer_id


def consume_code_run(assessment_id: int, question_id: int, limit: int) -> bool:
    """Count one candidate "Run" for a question; False once the limit is reached."""
    from pymongo.errors import DuplicateKeyError

    try:
        row = _database().assessment_code_runs.find_one_and_update(
            {"_id": f"{int(assessment_id)}:{int(question_id)}", "count": {"$lt": int(limit)}},
            {"$inc": {"count": 1}, "$set": {"updated_at": _now()}},
            upsert=True, return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        return False
    return bool(row)


def record_code_attempt(data: dict[str, Any]) -> None:
    """Append a candidate code run or final submission to the attempt history (recruiter view only)."""
    _database().assessment_code_attempts.insert_one({**data, "assessment_id": int(data["assessment_id"]),
                                                     "question_id": int(data["question_id"]), "created_at": _now()})


def get_code_attempts(assessment_id: int) -> list[dict]:
    rows = _database().assessment_code_attempts.find({"assessment_id": int(assessment_id)}).sort([("created_at", ASCENDING)])
    return _serialize_docs(list(rows))


# Published versions: an immutable snapshot of the questions and scoring rules each time an assessment is sent.


def create_assessment_version(data: dict[str, Any]) -> int:
    version = int(data["version"])
    _database().assessment_versions.insert_one({**data, "assessment_id": int(data["assessment_id"]), "version": version,
                                                "created_at": _now()})
    return version


def get_assessment_versions(assessment_id: int) -> list[dict]:
    rows = _database().assessment_versions.find({"assessment_id": int(assessment_id)}).sort([("version", ASCENDING)])
    return _serialize_docs(list(rows))


def get_answers_for_assessment(assessment_id: int) -> list[dict]:
    rows = list(_database().candidate_answers.find({"assessment_id": int(assessment_id)}))
    return _serialize_docs(rows)


def mark_answers_final(assessment_id: int) -> None:
    _database().candidate_answers.update_many(
        {"assessment_id": int(assessment_id)},
        {"$set": {"is_final": True, "updated_at": _now()}},
    )


# Assessment results


def _result_document(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "assessment_id": int(data["assessment_id"]),
        "candidate_id": int(data["candidate_id"]),
        "jd_id": int(data["jd_id"]),
        # Coding marks can be fractional (weighted test cases), so points are stored as floats.
        "total_points": float(data.get("total_points") or 0),
        "earned_points": float(data.get("earned_points") or 0),
        "score": float(data.get("score") if data.get("score") is not None else data.get("earned_points") or 0),
        "score_percentage": float(data.get("score_percentage") or data.get("percentage") or 0.0),
        "percentage": float(data.get("percentage") if data.get("percentage") is not None else data.get("score_percentage") or 0.0),
        "mcq_percentage": float(data.get("mcq_percentage") or 0.0),
        "passed": bool(data.get("passed")),
        "status": data.get("status") or AssessmentStatus.FAILED,
        "question_results": list(data.get("question_results") or []),
        "evaluation_breakdown": data.get("evaluation_breakdown") or {},
        "pending_review_count": int(data.get("pending_review_count") or 0),
        "pass_basis": data.get("pass_basis") or "overall",
        "summary": data.get("summary") or "",
        "scored_at": data.get("scored_at") or _now(),
        "coding_percentage": data.get("coding_percentage"),
        "execution_error_count": int(data.get("execution_error_count") or 0),
        "needs_retry": bool(data.get("needs_retry")),
        "qualification_checks": list(data.get("qualification_checks") or []),
        "scoring_policy": data.get("scoring_policy") or {},
        "applied_section_weights": data.get("applied_section_weights"),
        "assessment_version": data.get("assessment_version"),
    }


def create_assessment_result(data: dict[str, Any]) -> int:
    result_id = _next_id("assessment_results")
    doc = {"id": result_id, **_result_document(data), "created_at": _now()}
    _database().assessment_results.insert_one(doc)
    return result_id


def get_result_by_assessment_id(assessment_id: int) -> Optional[dict]:
    return _serialize_doc(_database().assessment_results.find_one({"assessment_id": int(assessment_id)}))


def upsert_assessment_result(data: dict[str, Any]) -> int:
    existing = _database().assessment_results.find_one({"assessment_id": int(data["assessment_id"])})
    if existing:
        patch = _result_document(data)
        _database().assessment_results.update_one({"id": int(existing["id"])}, {"$set": patch})
        return int(existing["id"])
    return create_assessment_result(data)
