# Backend file purpose: Flask route handlers for candidate features.
from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, redirect, request, send_from_directory

import database as db
from spa_urls import redirect_to_spa

from services.auth_service import api_login_required, current_user, login_required
from services.candidate_service import candidate_profile_payload, candidates_payload, repair_all_candidates

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
    status = request.args.get("status")
    search = request.args.get("search")
    category = request.args.get("category")
    filters: dict[str, Any] = {}
    if status:
        filters["status"] = status
    if search:
        filters["search"] = search
    if category:
        filters["category"] = category
    return jsonify(candidates_payload(filters if filters else None))


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
