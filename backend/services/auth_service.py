# Backend file purpose: Service-layer business logic for auth features.
from __future__ import annotations

import secrets
from functools import wraps
from typing import Optional

from flask import jsonify, redirect, request, session, url_for

import database as db
from security.rbac import normalize_role


# Purpose: Implements the login required backend behavior.
def login_required(view):
    # Purpose: Implements the wrapped backend behavior.
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


# Purpose: Implements the effective user id backend behavior.
def effective_user_id() -> Optional[int]:
    sid = session.get("user_id")
    if sid is not None:
        return int(sid)
    token = (request.headers.get("X-Session-Token") or "").strip()
    if token:
        uid = db.user_id_for_session_token(token)
        if uid is not None:
            return int(uid)
    return None


# Purpose: API endpoint handler for login required.
def api_login_required(view):
    # Purpose: Implements the wrapped backend behavior.
    @wraps(view)
    def wrapped(*args, **kwargs):
        if effective_user_id() is None:
            return jsonify({"error": "Unauthorized"}), 401
        return view(*args, **kwargs)

    return wrapped


# Purpose: Implements the current user backend behavior.
def current_user() -> Optional[dict]:
    uid = effective_user_id()
    if uid is None:
        return None
    user = db.get_user_by_id(uid)
    if not user:
        return None
    user["role"] = normalize_role(user.get("role"))
    return user


def role_required(*allowed_roles):
    """Protect a view by role; admin is always permitted."""
    allowed = {normalize_role(role) for role in allowed_roles}

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            role = normalize_role(user.get("role"))
            if role != "admin" and role not in allowed:
                return jsonify({"error": "Forbidden: insufficient role permissions."}), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator


# Purpose: Implements the authenticate backend behavior.
def authenticate(username: str, password: str) -> Optional[dict]:
    return db.authenticate_user(username, password)


# Purpose: Implements the login user backend behavior.
def login_user(user: dict, remember: bool = False) -> str:
    token = secrets.token_urlsafe(32)
    db.create_user_session_token(int(user["id"]), token, remember=remember)
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user.get("role", "")
    return token


# Purpose: Implements the logout user backend behavior.
def logout_user(api_token: Optional[str] = None) -> None:
    token = (api_token or "").strip()
    if token:
        db.delete_session_token(token)
    session.clear()
