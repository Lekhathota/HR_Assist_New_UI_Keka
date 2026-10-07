# Backend file purpose: Flask route handlers for in-app notifications (top-bar bell).
from __future__ import annotations

from flask import Blueprint, jsonify, request

import database as db
from services.auth_service import api_login_required, current_user

notification_bp = Blueprint("notification_routes", __name__)


# Purpose: API endpoint handler listing the signed-in user's notifications.
@notification_bp.route("/api/notifications", methods=["GET"], endpoint="api_notifications")
@api_login_required
def api_notifications():
    user = current_user()
    if not user:
        return jsonify({"error": "Not found"}), 404
    try:
        limit = int(request.args.get("limit") or 20)
    except ValueError:
        limit = 20
    return jsonify(db.list_notifications(user["id"], limit))


# Purpose: API endpoint handler marking notifications as read ({"ids": [...]} or all when omitted).
@notification_bp.route("/api/notifications/read", methods=["POST"], endpoint="api_notifications_read")
@api_login_required
def api_notifications_read():
    user = current_user()
    if not user:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(silent=True) or {}
    ids = data.get("ids")
    if ids is not None:
        if not isinstance(ids, list):
            return jsonify({"error": "ids must be a list."}), 400
        try:
            ids = [int(value) for value in ids]
        except (TypeError, ValueError):
            return jsonify({"error": "ids must be numbers."}), 400
    updated = db.mark_notifications_read(user["id"], ids)
    return jsonify({"success": True, "updated": updated})


# Purpose: API endpoint handler clearing all of the signed-in user's notifications (only for them).
@notification_bp.route("/api/notifications/clear", methods=["POST"], endpoint="api_notifications_clear")
@api_login_required
def api_notifications_clear():
    user = current_user()
    if not user:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True, "cleared": db.clear_notifications(user["id"])})
