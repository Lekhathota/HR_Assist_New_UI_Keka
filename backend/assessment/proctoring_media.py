"""
MongoDB persistence for assessment proctoring evidence.

Face snapshots are small JPEGs stored inline in ``proctoring_snapshots``. Session
recordings arrive as MediaRecorder timeslices and are stored in the GridFS bucket
``proctoring_recordings``; concatenating one session's chunks in sequence order
yields a playable WebM file. Every document carries the candidate's name and email
so evidence remains identifiable outside the assessment record.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import gridfs
from bson import Binary
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

import activity_feed
import database as db
from assessment.models import AssessmentStatus
from assessment.utilities import utc_now

FACE_VIOLATION_LIMIT = 2
RECORDING_BUCKET = "proctoring_recordings"
SNAPSHOT_KINDS = frozenset({"reference", "periodic"})
RECORDING_STREAMS = frozenset({"camera", "screen"})


def _database():
    db.init_pool()
    return db.get_database()


def _bucket() -> gridfs.GridFSBucket:
    return gridfs.GridFSBucket(_database(), bucket_name=RECORDING_BUCKET)


def _candidate_fields(assessment: dict[str, Any]) -> dict[str, Any]:
    return {
        "assessment_id": int(assessment["id"]),
        "candidate_id": assessment.get("candidate_id"),
        "candidate_name": assessment.get("candidate_name") or "",
        "candidate_email": assessment.get("candidate_email") or "",
        "jd_id": assessment.get("jd_id"),
    }


def ensure_proctoring_indexes() -> None:
    mongo = db.get_database()
    mongo.proctoring_snapshots.create_index(
        [("assessment_id", ASCENDING), ("snapshot_id", ASCENDING)], unique=True)
    mongo.proctoring_snapshots.create_index([("assessment_id", ASCENDING), ("captured_at", ASCENDING)])
    mongo.proctoring_snapshots.create_index([("candidate_name", ASCENDING)])
    files = mongo[f"{RECORDING_BUCKET}.files"]
    files.create_index(
        [("metadata.assessment_id", ASCENDING), ("metadata.stream", ASCENDING),
         ("metadata.session_id", ASCENDING), ("metadata.sequence", ASCENDING)],
        unique=True, name="unique_recording_chunk")
    files.create_index([("metadata.candidate_name", ASCENDING)])


def has_verified_reference(assessment_id: int) -> bool:
    return _database().proctoring_snapshots.count_documents(
        {"assessment_id": int(assessment_id), "kind": "reference", "face_ok": True}, limit=1) > 0


def find_snapshot(assessment_id: int, snapshot_id: str) -> Optional[dict]:
    return _database().proctoring_snapshots.find_one(
        {"assessment_id": int(assessment_id), "snapshot_id": snapshot_id})


def insert_snapshot(assessment: dict[str, Any], *, snapshot_id: str, kind: str, image: bytes,
                    mime_type: str, face_count: int, face_ok: bool, issue: str,
                    captured_at: datetime) -> bool:
    """Store a snapshot once. Returns False when this snapshot_id was already stored."""
    try:
        _database().proctoring_snapshots.insert_one({
            **_candidate_fields(assessment),
            "snapshot_id": snapshot_id,
            "kind": kind,
            "image": Binary(image),
            "mime_type": mime_type,
            "size": len(image),
            "face_count": int(face_count),
            "face_ok": bool(face_ok),
            "issue": issue,
            "captured_at": captured_at,
            "created_at": utc_now(),
        })
    except DuplicateKeyError:
        return False
    return True


def record_face_violation(assessment_id: int, snapshot_id: str, issue: str) -> Optional[dict]:
    """Count each failed snapshot once and terminate atomically on the second."""
    now = utc_now()
    limit = FACE_VIOLATION_LIMIT
    row = _database().assessments.find_one_and_update(
        {"id": int(assessment_id), "status": AssessmentStatus.IN_PROGRESS,
         "face_violations.snapshot_id": {"$ne": snapshot_id}},
        [
            {"$set": {
                "face_violation_count": {"$add": [{"$ifNull": ["$face_violation_count", 0]}, 1]},
                "face_violations": {"$concatArrays": [{"$ifNull": ["$face_violations", []]},
                    {"$literal": [{"snapshot_id": snapshot_id, "issue": issue, "recorded_at": now}]}]},
                "updated_at": now,
            }},
            {"$set": {
                "status": {"$cond": [{"$gte": ["$face_violation_count", limit]},
                    AssessmentStatus.TERMINATED, "$status"]},
                "completed_at": {"$cond": [{"$gte": ["$face_violation_count", limit]}, now, "$completed_at"]},
                "termination_reason": {"$cond": [{"$gte": ["$face_violation_count", limit]},
                    "Face not detected on camera twice", "$termination_reason"]},
            }},
        ],
        return_document=ReturnDocument.AFTER,
    )
    if row and row.get("status") == AssessmentStatus.TERMINATED:
        activity_feed.emit("assessment", assessment_id=int(assessment_id), jd_id=row.get("jd_id"),
                           name=row.get("candidate_name") or "", status="TERMINATED")
    return db._serialize_doc(row or _database().assessments.find_one({"id": int(assessment_id)}))


def store_recording_chunk(assessment: dict[str, Any], *, stream: str, session_id: str,
                          sequence: int, data: bytes, mime_type: str) -> bool:
    """Store a recording timeslice once. Returns False for a retried duplicate."""
    metadata = {
        **_candidate_fields(assessment),
        "stream": stream,
        "session_id": session_id,
        "sequence": int(sequence),
        "mime_type": mime_type,
        "uploaded_at": utc_now(),
    }
    files = _database()[f"{RECORDING_BUCKET}.files"]
    if files.find_one({"metadata.assessment_id": metadata["assessment_id"], "metadata.stream": stream,
                       "metadata.session_id": session_id, "metadata.sequence": int(sequence)}, {"_id": 1}):
        return False
    name = f"{metadata['candidate_name'] or 'candidate'}-assessment{metadata['assessment_id']}-{stream}-{session_id}-{int(sequence):05d}.webm"
    try:
        _bucket().upload_from_stream(name, data, metadata=metadata)
    except DuplicateKeyError:
        return False
    return True


def list_snapshots(assessment_id: int) -> list[dict]:
    rows = _database().proctoring_snapshots.find(
        {"assessment_id": int(assessment_id)}, {"image": 0}).sort("captured_at", ASCENDING)
    return [{
        "snapshot_id": row.get("snapshot_id"),
        "kind": row.get("kind"),
        "face_ok": bool(row.get("face_ok")),
        "face_count": int(row.get("face_count") or 0),
        "issue": row.get("issue") or "",
        "captured_at": row.get("captured_at"),
        "candidate_name": row.get("candidate_name") or "",
        "size": int(row.get("size") or 0),
    } for row in rows]


def list_recording_sessions(assessment_id: int) -> list[dict]:
    pipeline = [
        {"$match": {"metadata.assessment_id": int(assessment_id)}},
        {"$sort": {"metadata.sequence": 1}},
        {"$group": {
            "_id": {"stream": "$metadata.stream", "session_id": "$metadata.session_id"},
            "chunks": {"$push": "$metadata.sequence"},
            "bytes": {"$sum": "$length"},
            "started_at": {"$min": "$metadata.uploaded_at"},
            "ended_at": {"$max": "$metadata.uploaded_at"},
            "mime_type": {"$first": "$metadata.mime_type"},
            "candidate_name": {"$first": "$metadata.candidate_name"},
        }},
        {"$sort": {"started_at": 1}},
    ]
    return [{
        "stream": row["_id"]["stream"],
        "session_id": row["_id"]["session_id"],
        "chunks": row["chunks"],
        "bytes": int(row.get("bytes") or 0),
        "started_at": row.get("started_at"),
        "ended_at": row.get("ended_at"),
        "mime_type": row.get("mime_type") or "video/webm",
        "candidate_name": row.get("candidate_name") or "",
    } for row in _database()[f"{RECORDING_BUCKET}.files"].aggregate(pipeline)]


def read_recording_chunk(assessment_id: int, stream: str, session_id: str, sequence: int) -> Optional[tuple[bytes, str]]:
    files = _database()[f"{RECORDING_BUCKET}.files"]
    row = files.find_one({"metadata.assessment_id": int(assessment_id), "metadata.stream": stream,
                          "metadata.session_id": session_id, "metadata.sequence": int(sequence)})
    if not row:
        return None
    with _bucket().open_download_stream(row["_id"]) as handle:
        return handle.read(), (row.get("metadata") or {}).get("mime_type") or "video/webm"


def delete_assessment_media(assessment_id: int) -> None:
    mongo = _database()
    mongo.proctoring_snapshots.delete_many({"assessment_id": int(assessment_id)})
    bucket = _bucket()
    for row in mongo[f"{RECORDING_BUCKET}.files"].find({"metadata.assessment_id": int(assessment_id)}, {"_id": 1}):
        bucket.delete(row["_id"])
