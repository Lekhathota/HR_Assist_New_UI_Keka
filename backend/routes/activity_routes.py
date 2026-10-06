# Backend file purpose: Flask route handlers for report IDs, per-user activity stats,
# notification preferences and shared reference data (role categories).
from __future__ import annotations

from flask import Blueprint, jsonify, request

import activity_feed
import database as db
from services.auth_service import api_login_required, current_user
from services.role_category_service import role_category_options

activity_bp = Blueprint("activity_routes", __name__)

REPORT_SCOPES = {"jobs", "job_details", "talent", "candidate_profile", "analytics"}
REPORT_FORMATS = {"pdf", "docx", "csv", "excel", "email"}


# Purpose: Issues a real, sequential report ID for an export and records who generated it.
@activity_bp.route("/api/reports/issue", methods=["POST"], endpoint="api_reports_issue")
@api_login_required
def api_reports_issue():
    user = current_user()
    data = request.get_json(silent=True) or {}
    scope = str(data.get("scope") or "").strip().lower()
    report_format = str(data.get("format") or "").strip().lower()
    if scope not in REPORT_SCOPES:
        return jsonify({"error": "Unknown report scope."}), 400
    if report_format not in REPORT_FORMATS:
        return jsonify({"error": "Unknown report format."}), 400
    report_id = db.issue_report(user, scope, report_format)
    jd_id = data.get("jd_id")
    activity_feed.emit("report_generated", report_id=report_id, scope=scope, format=report_format,
                       jd_id=int(jd_id) if str(jd_id or "").isdigit() else None)
    return jsonify({"report_id": report_id})


# Purpose: Returns the signed-in user's own activity counts for the Profile page.
@activity_bp.route("/api/profile/activity", methods=["GET"], endpoint="api_profile_activity")
@api_login_required
def api_profile_activity():
    user = current_user()
    if not user:
        return jsonify({"error": "Not found"}), 404
    return jsonify(db.user_activity_stats(user["id"]))


# Purpose: Reads or saves the signed-in user's notification preferences.
@activity_bp.route("/api/profile/preferences", methods=["GET", "PUT"], endpoint="api_profile_preferences")
@api_login_required
def api_profile_preferences():
    user = current_user()
    if not user:
        return jsonify({"error": "Not found"}), 404
    if request.method == "PUT":
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict) or not data:
            return jsonify({"error": "Send at least one preference."}), 400
        return jsonify({"success": True, "preferences": db.save_user_preferences(user["id"], data)})
    return jsonify({"preferences": db.get_user_preferences(user["id"])})


# Purpose: Shared role-category taxonomy used by the Jobs and Talent filters.
@activity_bp.route("/api/meta/role-categories", methods=["GET"], endpoint="api_role_categories")
@api_login_required
def api_role_categories():
    return jsonify({"categories": role_category_options()})
