"""
MongoDB persistence layer for the Assessment module.

Uses the shared Recruitment Assist database connection and counter sequences.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import OperationFailure

import database as db
from assessment.models import AssessmentStatus
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

    mongo.candidate_answers.create_index([("id", ASCENDING)], unique=True)
    mongo.candidate_answers.create_index(
        [("assessment_id", ASCENDING), ("question_id", ASCENDING)],
        unique=True,
    )

    mongo.assessment_results.create_index([("id", ASCENDING)], unique=True)
    mongo.assessment_results.create_index([("assessment_id", ASCENDING)], unique=True)


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
        "passing_score": int(data.get("passing_score") or 70),
        "time_limit_minutes": int(data.get("time_limit_minutes") or 60),
        "sent_at": data.get("sent_at"),
        "started_at": data.get("started_at"),
        "completed_at": data.get("completed_at"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    token = str(data.get("access_token") or "").strip()
    if token:
        doc["access_token"] = token
    if data.get("token_expires_at") is not None:
        doc["token_expires_at"] = data.get("token_expires_at")
    _database().assessments.insert_one(doc)
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
    if update_doc and unset_doc:
        result = mongo.assessments.update_one(
            {"id": int(assessment_id)},
            {"$set": update_doc, "$unset": unset_doc},
        )
    elif unset_doc:
        result = mongo.assessments.update_one({"id": int(assessment_id)}, {"$unset": unset_doc, "$set": update_doc})
    else:
        result = mongo.assessments.update_one({"id": int(assessment_id)}, {"$set": update_doc})
    return result.modified_count > 0


def delete_assessment_cascade(assessment_id: int) -> None:
    mongo = _database()
    aid = int(assessment_id)
    mongo.questions.delete_many({"assessment_id": aid})
    mongo.candidate_answers.delete_many({"assessment_id": aid})
    mongo.assessment_results.delete_many({"assessment_id": aid})
    mongo.assessments.delete_one({"id": aid})


# Questions


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
) -> int:
    mongo = _database()
    existing = mongo.candidate_answers.find_one(
        {"assessment_id": int(assessment_id), "question_id": int(question_id)}
    )
    now = _now()
    if existing:
        mongo.candidate_answers.update_one(
            {"id": int(existing["id"])},
            {"$set": {"answer": answer, "is_final": is_final, "updated_at": now}},
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
            "created_at": now,
            "updated_at": now,
        }
    )
    return answer_id


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
        "total_points": int(data.get("total_points") or 0),
        "earned_points": int(data.get("earned_points") or 0),
        "score": int(data.get("score") if data.get("score") is not None else data.get("earned_points") or 0),
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
