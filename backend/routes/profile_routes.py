# Backend file purpose: Flask route handlers for profile features.
from __future__ import annotations

from flask import Blueprint, jsonify, redirect, request

import database as db
from spa_urls import redirect_to_spa

from services.auth_service import api_login_required, current_user, login_required

profile_bp = Blueprint("profile_routes", __name__)


# Purpose: Implements the profile backend behavior.
@profile_bp.route("/profile", methods=["GET", "POST"], endpoint="profile")
@login_required
def profile():
    user = current_user()
    if request.method == "POST" and user:
        email = (request.form.get("email") or "").strip()
        db.update_user_profile(user["id"], email)
        return redirect_to_spa("/profile")
    return redirect_to_spa("/profile")


# Purpose: API endpoint handler for profile.
@profile_bp.route("/api/profile", methods=["GET", "POST"], endpoint="api_profile")
@api_login_required
def api_profile():
    user = current_user()
    if not user:
        return jsonify({"error": "Not found"}), 404
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip()
        current_password = str(data.get("current_password") or "")
        new_password = str(data.get("new_password") or "")
        confirm_password = str(data.get("confirm_password") or "")
        if new_password or current_password or confirm_password:
            if not current_password or not new_password:
                return jsonify({"success": False, "error": "Current password and new password are required."}), 400
            if new_password != confirm_password:
                return jsonify({"success": False, "error": "New passwords do not match."}), 400
            if not db.update_user_password(user["id"], current_password, new_password):
                return jsonify({"success": False, "error": "Current password is incorrect."}), 400
        db.update_user_profile(user["id"], email)
        updated = db.get_user_by_id(user["id"])
        return jsonify({"success": True, "message": "Profile updated successfully", "user": updated})
    return jsonify({"user": user})
