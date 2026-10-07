# Backend file purpose: Flask route handlers for the recruiter list used when creating a JD.
from __future__ import annotations

from flask import Blueprint, jsonify, request

import database as db
from services.auth_service import api_login_required, current_user

recruiter_bp = Blueprint("recruiter_routes", __name__)


# Purpose: API endpoint handler listing recruiters.
@recruiter_bp.route("/api/recruiters", methods=["GET"], endpoint="api_recruiters")
@api_login_required
def api_recruiters():
    return jsonify({"recruiters": db.list_recruiters()})


# Purpose: API endpoint handler adding a new recruiter.
@recruiter_bp.route("/api/recruiters", methods=["POST"], endpoint="api_recruiter_add")
@api_login_required
def api_recruiter_add():
    user = current_user() or {}
    name = (request.get_json(silent=True) or {}).get("name") or ""
    try:
        added, created = db.add_recruiter(name, user.get("username") or "")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if created:
        db.log_audit("Recruiter Added", user.get("username") or "", f"Added recruiter '{added}'.", None)
    return jsonify({"success": True, "name": added, "created": created, "recruiters": db.list_recruiters()}), 201 if created else 200
