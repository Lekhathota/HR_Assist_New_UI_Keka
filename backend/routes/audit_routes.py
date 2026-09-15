# Backend file purpose: Flask route handlers for audit features.
from __future__ import annotations

from flask import Blueprint, jsonify

from services.auth_service import api_login_required
import database as db

audit_bp = Blueprint("audit_routes", __name__)


# Purpose: API endpoint handler for audit logs.
@audit_bp.route("/api/audit/logs", endpoint="api_audit_logs")
@api_login_required
def api_audit_logs():
    activity = db.recent_activity(20)
    return jsonify({"recent_comparisons": activity.get("recent_comparisons", [])})
