# Backend file purpose: Flask route handlers for auth features.
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, redirect, request, session

try:
    from itsdangerous import BadSignature
except ImportError:
    BadSignature = Exception  # type: ignore[misc, assignment]

from spa_urls import redirect_to_spa, safe_next_path

from services.auth_service import authenticate, login_user, logout_user

auth_bp = Blueprint("auth_routes", __name__)


# Purpose: Implements the index backend behavior.
@auth_bp.route("/", endpoint="index")
def index():
    if session.get("user_id"):
        return redirect_to_spa("/dashboard")
    return redirect_to_spa("/login")


# Purpose: Implements the login backend behavior.
@auth_bp.route("/login", methods=["GET", "POST"], endpoint="login")
def login():
    try:
        if session.get("user_id"):
            return redirect_to_spa("/dashboard")
    except BadSignature:
        session.clear()
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        try:
            user = authenticate(username, password)
        except Exception:
            current_app.logger.exception("login: database or auth error")
            return redirect_to_spa("/login")
        if user:
            login_user(user)
            nxt = safe_next_path(request.args.get("next"))
            return redirect_to_spa(nxt)
        return redirect_to_spa("/login")
    return redirect_to_spa("/login")


# Purpose: Implements the logout backend behavior.
@auth_bp.route("/logout", endpoint="logout")
def logout():
    logout_user()
    return redirect_to_spa("/login")


# Purpose: API endpoint handler for login.
@auth_bp.route("/api/login", methods=["POST"], endpoint="api_login")
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    try:
        user = authenticate(username, password)
    except Exception:
        current_app.logger.exception("api_login: database or auth error")
        return jsonify({"success": False, "message": "Service unavailable. Check database configuration."}), 503
    if not user:
        return jsonify({"success": False, "message": "Invalid username or password."}), 401
    token = login_user(user)
    return jsonify({"success": True, "token": token, "user": user})


# Purpose: API endpoint handler for logout.
@auth_bp.route("/api/logout", methods=["POST"], endpoint="api_logout")
def api_logout():
    logout_user(request.headers.get("X-Session-Token"))
    return jsonify({"success": True})
