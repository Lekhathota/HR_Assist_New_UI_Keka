# Backend file purpose: Flask route handlers for candidate features.
from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, redirect, request, send_from_directory

import database as db
from spa_urls import redirect_to_spa

from services.auth_service import api_login_required, current_user, login_required, role_required
from services.candidate_service import (
    candidate_ids_with_interview_in_range,
    candidate_profile_payload,
    candidates_payload,
    parse_calendar_bound,
    repair_all_candidates,
)
from services.hiring_process_service import compute_effective_stage, get_stage_options, normalize_process

candidate_bp = Blueprint("candidate_routes", __name__)


# Purpose: Implements the candidates backend behavior.
@candidate_bp.route("/candidates", endpoint="candidates")
@login_required
def candidates():
    return redirect_to_spa("/talent")


# Purpose: Implements the candidate profile backend behavior.
@candidate_bp.route("/candidates/<int:candidate_id>", endpoint="candidate_profile")
@login_required
def candidate_profile(candidate_id: int):
    payload = candidate_profile_payload(candidate_id)
    if not payload:
        return redirect_to_spa("/talent")
    return redirect_to_spa(f"/talent/{candidate_id}")


# Purpose: API endpoint handler for candidates.
@candidate_bp.route("/api/candidates", endpoint="api_candidates")
@api_login_required
def api_candidates():
    args = request.args
    filters: dict[str, Any] = {}
    if args.get("status"):
        filters["status"] = args["status"]
    if args.get("search"):
        filters["search"] = args["search"]
    if args.get("category"):
        filters["category"] = args["category"]
    if args.get("client_id"):
        filters["client_id"] = args["client_id"]
    if args.get("project_id"):
        filters["project_id"] = args["project_id"]
    if args.get("stage"):
        filters["stage_id"] = args["stage"]

    tz_name = args.get("tz") or ""
    upload_from = parse_calendar_bound(args.get("upload_from"), tz_name, end_of_day=False)
    upload_to = parse_calendar_bound(args.get("upload_to"), tz_name, end_of_day=True)
    if upload_from and upload_to and upload_from > upload_to:
        return jsonify({"error": "Upload date range is reversed."}), 400
    if upload_from:
        filters["uploaded_from"] = upload_from
    if upload_to:
        filters["uploaded_to"] = upload_to

    interview_from = parse_calendar_bound(args.get("interview_from"), tz_name, end_of_day=False)
    interview_to = parse_calendar_bound(args.get("interview_to"), tz_name, end_of_day=True)
    if interview_from and interview_to and interview_from > interview_to:
        return jsonify({"error": "Interview date range is reversed."}), 400
    if interview_from or interview_to:
        matching_ids = candidate_ids_with_interview_in_range(interview_from, interview_to)
        if matching_ids is not None:
            filters["id_in"] = matching_ids

    return jsonify(candidates_payload(filters if filters else None))


# Purpose: API endpoint handler for stage filter options grouped by requirement.
@candidate_bp.route("/api/candidates/stage-options", endpoint="api_candidates_stage_options")
@api_login_required
def api_candidates_stage_options():
    project_id = request.args.get("project_id")
    return jsonify({"groups": get_stage_options(int(project_id) if project_id else None)})


# Purpose: API endpoint handler for updating a candidate's manual hiring state.
@candidate_bp.route("/api/candidates/<int:candidate_id>/hiring-state", methods=["POST"], endpoint="api_candidate_hiring_state")
@api_login_required
@role_required("recruiter")
def api_candidate_hiring_state(candidate_id: int):
    candidate = db.get_candidate_by_id(candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found"}), 404
    jd = db.get_jd_by_id(int(candidate["jd_id"])) if candidate.get("jd_id") else None
    process = normalize_process((jd or {}).get("hiring_process"))
    data = request.get_json(silent=True) or {}
    updates: dict[str, Any] = {}
    notes: list[str] = []

    if "stage_id" in data:
        stage_id = data.get("stage_id")
        valid_ids = {step["id"] for step in process["steps"]}
        if stage_id is not None and stage_id not in valid_ids:
            return jsonify({"error": "stage_id does not belong to this candidate's linked job."}), 400
        updates["stage_id"] = stage_id
        updates["automation_paused"] = True
        stage_name = next((s["name"] for s in process["steps"] if s["id"] == stage_id), "Not Started")
        notes.append(f"stage set to '{stage_name}' (automation paused)")

    if "on_hold" in data:
        updates["on_hold"] = bool(data.get("on_hold"))
        notes.append("placed on hold" if updates["on_hold"] else "hold cleared")

    if data.get("resume_automation"):
        updates["automation_paused"] = False
        notes.append("automation resumed")

    if not updates:
        return jsonify({"error": "No supported fields supplied."}), 400

    db.update_candidate(candidate_id, updates)
    user = current_user()
    db.log_audit(
        "Candidate Hiring State Updated",
        user["username"] if user else "",
        f"Updated hiring state for '{candidate.get('name') or candidate_id}': {', '.join(notes)}.",
        candidate.get("jd_id"),
    )
    updated_candidate = {**candidate, **updates}
    return jsonify({"success": True, **compute_effective_stage(updated_candidate, jd)})


# Purpose: API endpoint handler for candidates repair.
@candidate_bp.route("/api/candidates/repair", methods=["POST"], endpoint="api_candidates_repair")
@api_login_required
def api_candidates_repair():
    return jsonify({"success": True, **repair_all_candidates(force_reextract=True)})


# Purpose: API endpoint handler for candidate profile.
@candidate_bp.route("/api/candidates/<int:candidate_id>", endpoint="api_candidate_profile")
@api_login_required
def api_candidate_profile(candidate_id: int):
    payload = candidate_profile_payload(candidate_id)
    if not payload:
        return jsonify({"error": "Candidate not found"}), 404
    return jsonify({"candidate": payload["candidate"], "timeline": payload.get("timeline") or []})


# Purpose: Implements the candidate delete backend behavior.
@candidate_bp.route("/candidates/<int:candidate_id>/delete", methods=["POST"], endpoint="candidate_delete")
@login_required
def candidate_delete(candidate_id: int):
    user = current_user()
    row = db.get_candidate_by_id(candidate_id)
    if db.delete_candidate(candidate_id):
        db.log_audit(
            "Candidate Deleted",
            user["username"] if user else "",
            f"User '{user['username'] if user else 'unknown'}' deleted candidate "
            f"'{(row or {}).get('name', 'Unknown')}' (id={candidate_id}).",
            (row or {}).get("jd_id"),
        )
    return redirect_to_spa("/talent")


# Purpose: API endpoint handler for candidate delete.
@candidate_bp.route("/api/candidates/<int:candidate_id>/delete", methods=["POST"], endpoint="api_candidate_delete")
@api_login_required
def api_candidate_delete(candidate_id: int):
    user = current_user()
    row = db.get_candidate_by_id(candidate_id)
    if db.delete_candidate(candidate_id):
        db.log_audit(
            "Candidate Deleted",
            user["username"] if user else "",
            f"API user '{user['username'] if user else 'unknown'}' deleted candidate "
            f"'{(row or {}).get('name', 'Unknown')}' (id={candidate_id}).",
            (row or {}).get("jd_id"),
        )
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Candidate not found"}), 404


# Purpose: Implements the uploaded file backend behavior.
@candidate_bp.route("/static/uploads/<path:name>", endpoint="uploaded_file")
@api_login_required
def uploaded_file(name: str):
    from flask import current_app

    return send_from_directory(current_app.config["UPLOAD_FOLDER"], name, as_attachment=False)
