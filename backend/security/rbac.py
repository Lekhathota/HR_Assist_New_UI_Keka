"""Central role-based access policy for Recruitment Assist API routes.

Role checks here are defense-in-depth; sensitive business operations should
also enforce ownership/assignment constraints in their service layer.
"""
from __future__ import annotations

from flask import jsonify, request

ROLE_ALIASES = {
    "admin": "admin", "administrator": "admin",
    "recruiter": "recruiter", "talent acquisition": "recruiter",
    "hiring manager": "hiring_manager", "hiring_manager": "hiring_manager",
    "manager": "hiring_manager",
}


def normalize_role(value: object) -> str:
    key = " ".join(str(value or "").strip().lower().replace("_", " ").split())
    return ROLE_ALIASES.get(key, key)


def _allowed(role: str, path: str, method: str, task_type: str = "") -> bool:
    if role == "admin":
        return True

    # Shared, signed-in utility pages/APIs.
    if path.startswith(("/api/profile", "/api/dashboard", "/api/metrics/jd-performance")):
        return True

    # Recruiters can run the recruitment workflow (not manage tenant settings).
    if role == "recruiter":
        if path.startswith(("/api/jds", "/api/candidates", "/api/interviews", "/api/compare")):
            return True
        if path.startswith("/api/agentic/"):
            return task_type in {
                "dashboard", "dashboard_team", "jd_performance", "jd_list", "jd_details",
                "jd_create", "jd_delete", "candidate_list", "candidate_profile",
                "candidate_delete", "screening", "interview_defaults", "interview_blocked_slots",
                "interview_generate_email", "interview_schedule", "interview_reschedule",
                "interview_outcome", "interview_send_cancellation", "profile_get", "profile_update",
            }
        return False

    # Hiring managers may inspect candidates and participate in review/interview
    # decisions, but cannot create/delete jobs, edit candidates, or administer.
    if role == "hiring_manager":
        if path.startswith("/api/candidates") and method in {"GET", "HEAD"}:
            return True
        if path.startswith("/api/interviews"):
            if method in {"GET", "HEAD"}:
                return True
            if method == "POST" and any(x in path for x in ("/outcome", "/review", "/approve")):
                return True
        if path.startswith("/api/agentic/"):
            return task_type in {
                "dashboard", "dashboard_team", "candidate_list", "candidate_profile",
                "interview_defaults", "interview_blocked_slots", "interview_outcome",
                "profile_get", "profile_update",
            }
        return False

    return False


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
