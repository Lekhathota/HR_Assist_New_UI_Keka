# Backend file purpose: Service-layer business logic for auth features.
from __future__ import annotations

import secrets
from functools import wraps
from typing import Optional

from flask import jsonify, redirect, request, session, url_for

import database as db


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
    return db.get_user_by_id(uid)


# Purpose: Implements the authenticate backend behavior.
def authenticate(username: str, password: str) -> Optional[dict]:
    return db.authenticate_user(username, password)


# Purpose: Implements the login user backend behavior.
def login_user(user: dict) -> str:
    token = secrets.token_urlsafe(32)
    db.replace_user_session_token(int(user["id"]), token)
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
