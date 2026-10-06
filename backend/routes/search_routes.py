# Backend file purpose: Flask route handler for the top-bar global search.
from __future__ import annotations

from flask import Blueprint, jsonify, request

import database as db
from security.rbac import normalize_role
from services.auth_service import api_login_required, current_user

search_bp = Blueprint("search_routes", __name__)

# Mirrors the page access rules in frontend/src/roleAccess.js so search can't
# reveal records from pages a role cannot open. Admin sees every section.
SECTION_ROLES = {
    "jobs": {"recruiter"},
    "candidates": {"recruiter"},
    "clients": {"managers_consultant"},
    "vendors": {"managers_consultant"},
}


def allowed_sections(role: str) -> set[str]:
    role = normalize_role(role)
    if role == "admin":
        return set(SECTION_ROLES)
    return {section for section, roles in SECTION_ROLES.items() if role in roles}


# Purpose: API endpoint handler searching JDs, candidates, clients and vendors by name.
@search_bp.route("/api/search", methods=["GET"], endpoint="api_search")
@api_login_required
def api_search():
    user = current_user() or {}
    query = str(request.args.get("q") or "").strip()[:80]
    try:
        limit = max(1, min(int(request.args.get("limit") or 6), 20))
    except ValueError:
        limit = 6
    return jsonify({"query": query, **db.global_search(query, allowed_sections(user.get("role")), limit)})
