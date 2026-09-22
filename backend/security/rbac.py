"""Central role-based access policy for Recruitment Assist API routes.

Role checks here are defense-in-depth; sensitive business operations should
also enforce ownership/assignment constraints in their service layer.
"""
from __future__ import annotations

from flask import jsonify, request

ROLE_ALIASES = {
    "admin": "admin", "administrator": "admin",
    "finance": "finance",
    "recruiter": "recruiter", "talent acquisition": "recruiter",
    "hr": "hr", "human resources": "hr",
    "managers consultant": "managers_consultant", "managers_consultant": "managers_consultant",
    "manager": "managers_consultant", "consultant": "managers_consultant",
    "it": "it", "information technology": "it",
}

ROLES = {"finance", "recruiter", "hr", "managers_consultant", "it"}


def normalize_role(value: object) -> str:
    key = " ".join(str(value or "").strip().lower().replace("_", " ").replace("/", " ").split())
    return ROLE_ALIASES.get(key, key)


def _allowed(role: str, path: str, method: str, task_type: str = "") -> bool:
    # "admin" always has unrestricted access.
    if role == "admin":
        return True
    # Per-role page/API access has not been configured yet for the other
    # roles — every recognized role gets full access until that's defined.
    return role in ROLES


def enforce_api_role(user_getter) -> object | None:
    """Return a 403 response when authenticated role lacks route permission."""
    path = request.path or ""
    if not path.startswith("/api/") or path in {"/api/login", "/api/logout"}:
        return None
    user = user_getter() or {}
    # Let the endpoint authentication decorator return the canonical 401.
    if not user:
        return None
    role = normalize_role(user.get("role"))
    payload = request.get_json(silent=True) or {}
    task_type = str(payload.get("task_type") or "")
    if not _allowed(role, path, request.method.upper(), task_type):
        return jsonify({"error": "Forbidden: your role does not have permission for this action."}), 403
    return None
