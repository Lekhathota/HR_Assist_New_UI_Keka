# Backend file purpose: Flask route handlers for agentic features.
from __future__ import annotations

import os
from typing import Any

from flask import Blueprint, current_app, jsonify, request

import database as db
from orchestration.main_orchestrator import run_main_orchestrator
from schemas.agentic import validate_agentic_payload
from services.auth_service import api_login_required, current_user
from services.jd_service import allowed_file, unique_upload_filename

agentic_bp = Blueprint("agentic_routes", __name__)


# Purpose: Implements the collect resume files backend behavior.
def _collect_resume_files():
    """Collect uploaded resume files from all supported multipart field names."""
    keys = ("resumes", "resumes[]", "resume", "resume[]", "files", "file", "file[]", "uploads")
    files = []
    for key in keys:
        files.extend(request.files.getlist(key))
    return [f for f in files if f and getattr(f, "filename", "")]


# Purpose: Implements the save resume items backend behavior.
def _save_resume_items() -> tuple[list[dict[str, str]], int]:
    """Save valid uploaded resume files and return file metadata for the Resume Agent."""
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    items: list[dict[str, str]] = []
    skipped = 0
    for rf in _collect_resume_files():
        if not allowed_file(rf.filename):
            skipped += 1
            continue
        filename = unique_upload_filename(rf.filename or "")
        path = os.path.join(upload_folder, filename)
        rf.save(path)
        items.append({"filename": filename, "original_filename": rf.filename or "", "path": path})
    return items, skipped


# Purpose: Implements the multipart payload backend behavior.
def _multipart_payload(task_type: str = "screening") -> dict[str, Any]:
    """Convert multipart screening form data into the orchestrator payload shape."""
    resume_items, skipped = _save_resume_items()
    return {
        "task_type": request.form.get("task_type") or task_type,
        "jd_id": request.form.get("jd_id"),
        "candidate_ids": request.form.getlist("candidate_ids"),
        "resume_items": resume_items,
        "skipped_files": skipped,
    }


# Purpose: Implements the request payload backend behavior.
def _request_payload() -> dict[str, Any]:
    """Normalize JSON, screening upload, and JD upload requests into one payload dictionary."""
    if request.files or request.form:
        task_type = request.form.get("task_type") or "screening"
        if task_type == "jd_create":
            return {
                "task_type": "jd_create",
                "file": request.files.get("file"),
                "upload_folder": current_app.config["UPLOAD_FOLDER"],
                "client_id": request.form.get("client_id"),
                "required_candidate_count": request.form.get("required_candidate_count"),
            }
        return _multipart_payload(task_type)
    return request.get_json(silent=True) or {}


# Purpose: API endpoint handler for agentic run.
@agentic_bp.route("/api/agentic/run", methods=["POST"], endpoint="api_agentic_run")
@api_login_required
def api_agentic_run():
    """Main protected API endpoint that invokes the LangGraph HR orchestrator."""
    user = current_user() or {}
    try:
        payload = validate_agentic_payload(_request_payload())
        payload["_user"] = user
        result = run_main_orchestrator(payload, username=user.get("username") or "")
        db.log_audit(
            "Agentic Run",
            user.get("username") or "",
            f"Main HR Orchestrator completed task '{result.get('task_type')}' with run_id={result.get('run_id')}.",
            int(payload["jd_id"]) if payload.get("jd_id") else None,
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("agentic run failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


# Purpose: API endpoint handler for agentic screening.
@agentic_bp.route("/api/agentic/screening", methods=["POST"], endpoint="api_agentic_screening")
@api_login_required
def api_agentic_screening():
    """Compatibility endpoint for direct agentic screening multipart requests."""
    user = current_user() or {}
    try:
        payload = validate_agentic_payload(_multipart_payload("screening"))
        payload["_user"] = user
        result = run_main_orchestrator(payload, username=user.get("username") or "")
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("agentic screening failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


# Purpose: API endpoint handler for agentic runs.
@agentic_bp.route("/api/agentic/runs", endpoint="api_agentic_runs")
@api_login_required
def api_agentic_runs():
    """Return recent agent run records, optionally filtered to the current user."""
    user = current_user() or {}
    filters: dict[str, Any] = {
        "task_type": request.args.get("task_type") or "",
        "limit": request.args.get("limit") or 50,
    }
    if request.args.get("mine") in {"1", "true", "yes"}:
        filters["username"] = user.get("username") or ""
    return jsonify({"runs": db.get_agent_runs(filters)})


# Purpose: API endpoint handler for agentic run detail.
@agentic_bp.route("/api/agentic/runs/<run_id>", endpoint="api_agentic_run_detail")
@api_login_required
def api_agentic_run_detail(run_id: str):
    """Return one stored agent run record by run_id."""
    row = db.get_agent_run(run_id)
    if not row:
        return jsonify({"error": "Agent run not found"}), 404
    return jsonify({"run": row})
