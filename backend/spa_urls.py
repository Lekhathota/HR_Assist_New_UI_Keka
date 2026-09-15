# Backend file purpose: Backend entrypoint or shared infrastructure for spa urls.
"""Redirect helpers: Flask HTML routes → React app (FRONTEND_URL)."""

from __future__ import annotations

import os

from flask import redirect


# Purpose: Implements the frontend base backend behavior.
def frontend_base() -> str:
    return (os.environ.get("FRONTEND_URL") or "http://localhost:3001").rstrip("/")


# Purpose: Implements the redirect to spa backend behavior.
def redirect_to_spa(path: str, code: int = 302):
    path = path if path.startswith("/") else f"/{path}"
    return redirect(f"{frontend_base()}{path}", code=code)


# Purpose: Implements the legacy path to spa backend behavior.
def legacy_path_to_spa(path: str) -> str:
    """Map legacy Flask paths and mixed paths to React Router paths."""
    if not path or not isinstance(path, str):
        return "/dashboard"
    raw = path.strip().split("?", 1)[0]
    if not raw.startswith("/"):
        return "/dashboard"
    if raw.startswith("/api/"):
        return "/dashboard"

    if raw.startswith("/jobs") or raw.startswith("/talent"):
        return raw.split("#")[0]
    if raw.startswith("/analyze") or raw.startswith("/insights"):
        return raw.split("#")[0]
    if raw in {"/", "/dashboard"}:
        return "/dashboard"
    if raw.startswith("/profile"):
        return "/profile"
    if raw.startswith("/login"):
        return "/login"

    if raw.startswith("/jds/create"):
        return "/jobs/create"
    if raw.startswith("/jds/"):
        tail = raw[len("/jds/"):].strip("/")
        if tail.isdigit():
            return f"/jobs/{tail}"
        return "/jobs"
    if raw == "/jds":
        return "/jobs"

    if raw.startswith("/candidates/"):
        tail = raw[len("/candidates/"):].split("/")[0]
        if tail.isdigit():
            return f"/talent/{tail}"
        return "/talent"
    if raw == "/candidates":
        return "/talent"

    if raw.startswith("/compare"):
        return "/analyze"
    if raw.startswith("/reports"):
        return "/insights"

    return "/dashboard"


# Purpose: Implements the safe next path backend behavior.
def safe_next_path(raw: str | None) -> str:
    if not raw or not isinstance(raw, str):
        return "/dashboard"
    s = raw.strip()
    if s.startswith("http://") or s.startswith("https://"):
        return "/dashboard"
    return legacy_path_to_spa(s)
