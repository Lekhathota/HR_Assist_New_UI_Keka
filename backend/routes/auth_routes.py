# Backend file purpose: Flask route handlers for auth features.
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, redirect, request, session
import re

try:
    from itsdangerous import BadSignature
except ImportError:
    BadSignature = Exception  # type: ignore[misc, assignment]

from spa_urls import redirect_to_spa, safe_next_path

from services.auth_service import authenticate, login_user, logout_user, current_user, api_login_required

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
    return jsonify({"success": True, "token": token, "user": {"id": user.get("id"), "username": user.get("username"), "email": user.get("email"), "role": user.get("role")}})


# Purpose: API endpoint handler for logout.
@auth_bp.route("/api/logout", methods=["POST"], endpoint="api_logout")
def api_logout():
    logout_user(request.headers.get("X-Session-Token"))
    return jsonify({"success": True})


@auth_bp.route("/api/me", methods=["GET"], endpoint="api_me")
@api_login_required
def api_me():
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"user": {"id": user.get("id"), "username": user.get("username"), "email": user.get("email"), "role": user.get("role")}})


# User administration API. Per-role restrictions have not been configured yet,
# so any authenticated, recognized-role user may manage accounts for now.
# "admin" keeps unrestricted superuser access regardless of other role rules.
def _admin_user():
    user = current_user()
    if not user:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    if str(user.get("role", "")).strip().lower().replace(" ", "_") not in {"finance", "recruiter", "hr", "managers_consultant", "it", "admin"}:
        return None, (jsonify({"error": "Forbidden: unrecognized role."}), 403)
    return user, None


@auth_bp.route("/api/admin/users", methods=["GET"], endpoint="admin_list_users")
@api_login_required
def admin_list_users():
    _, error = _admin_user()
    if error: return error
    import database as db
    users = db.list_users()
    safe = [{k: u.get(k) for k in ("id", "username", "email", "role", "is_active", "created_at")} for u in users]
    return jsonify({"users": safe})


@auth_bp.route("/api/admin/users", methods=["POST"], endpoint="admin_create_user")
@api_login_required
def admin_create_user():
    _, error = _admin_user()
    if error: return error
    import database as db
    from pymongo.errors import DuplicateKeyError
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip().lower()
    password = str(data.get("password") or "")
    email = str(data.get("email") or "").strip().lower()
    role = str(data.get("role") or "").strip().lower().replace(" ", "_")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,39}", username):
        return jsonify({"error": "Username must be 3–40 characters (letters, numbers, dot, underscore or hyphen)."}), 400
    if len(password) < 12:
        return jsonify({"error": "Password must be at least 12 characters."}), 400
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"error": "Enter a valid email address."}), 400
    if role not in {"finance", "recruiter", "hr", "managers_consultant", "it", "admin"}:
        return jsonify({"error": "Role must be finance, recruiter, hr, managers_consultant, it, or admin."}), 400
    try:
        user = db.create_managed_user(username, password, email, role)
    except DuplicateKeyError:
        return jsonify({"error": "That username already exists."}), 409
    return jsonify({"success": True, "user": {k: user.get(k) for k in ("id", "username", "email", "role", "is_active")}}), 201


@auth_bp.route("/api/admin/users/<int:user_id>", methods=["PATCH"], endpoint="admin_update_user")
@api_login_required
def admin_update_user(user_id):
    admin, error = _admin_user()
    if error: return error
    import database as db
    data = request.get_json(silent=True) or {}
    updates = {}
    if "role" in data:
        role = str(data.get("role") or "").strip().lower().replace(" ", "_")
        if role not in {"finance", "recruiter", "hr", "managers_consultant", "it", "admin"}:
            return jsonify({"error": "Role must be finance, recruiter, hr, managers_consultant, it, or admin."}), 400
        if admin.get("role") == "admin" and int(admin["id"]) == user_id and role != "admin":
            return jsonify({"error": "You cannot remove your own administrator role."}), 400
        updates["role"] = role
    if "is_active" in data:
        active = bool(data.get("is_active"))
        target = db.get_user_by_id(user_id)
        if not target: return jsonify({"error": "User not found."}), 404
        if int(admin["id"]) == user_id and not active:
            return jsonify({"error": "You cannot deactivate your own account."}), 400
        if not active and target.get("role") in {"admin", "administrator"}:
            active_admins = [u for u in db.list_users() if u.get("role") in {"admin", "administrator"} and u.get("is_active", True)]
            if len(active_admins) <= 1:
                return jsonify({"error": "At least one active administrator must remain."}), 400
        updates["is_active"] = active
        if not active:
            db.get_database().user_session_tokens.delete_many({"user_id": user_id})
    if not updates: return jsonify({"error": "No supported fields supplied."}), 400
    if not db.update_managed_user(user_id, updates): return jsonify({"error": "User not found."}), 404
    return jsonify({"success": True})
