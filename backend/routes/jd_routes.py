# Backend file purpose: Flask route handlers for jd features.
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, redirect, request

import database as db
from spa_urls import redirect_to_spa

from services.auth_service import api_login_required, current_user, login_required, role_required
from services.fulfilment_service import run_automated_bench_workflow
from services.hiring_process_service import build_steps, validate_mappings, validate_step_removal, normalize_process
from services.jd_service import allowed_file, create_jd_from_upload, jd_details_payload, jd_summary_list_payload

jd_bp = Blueprint("jd_routes", __name__)


# Purpose: Implements the jd list backend behavior.
@jd_bp.route("/jds", endpoint="jd_list")
@login_required
def jd_list():
    return redirect_to_spa("/jobs")


# Purpose: Implements the jd create backend behavior.
@jd_bp.route("/jds/create", methods=["GET", "POST"], endpoint="jd_create")
@login_required
def jd_create():
    if request.method == "POST":
        if "file" not in request.files:
            return redirect_to_spa("/jobs/create")
        file = request.files["file"]
        if not file.filename or not allowed_file(file.filename):
            return redirect_to_spa("/jobs/create")
        try:
            client_id = int(request.form.get("client_id") or 0) or None
            required_count = int(request.form.get("required_candidate_count") or 0)
            if required_count <= 0:
                raise ValueError("required_candidate_count must be greater than zero")
            job_code = request.form.get("job_code") or ""
            created = create_jd_from_upload(file, current_app.config["UPLOAD_FOLDER"], client_id, required_count, job_code)
            user = current_user()
            db.log_audit(
                "JD Created",
                user["username"] if user else "",
                f"User '{user['username'] if user else 'unknown'}' created JD '{created['title']}' (id={created['id']}).",
                created["id"],
            )
            try:
                run_automated_bench_workflow(created["id"], username=user["username"] if user else "")
            except Exception as exc:
                current_app.logger.exception("JD workflow after create: %s", exc)
            return redirect_to_spa(f"/jobs/{created['id']}")
        except Exception:
            return redirect_to_spa("/jobs/create")
    return redirect_to_spa("/jobs/create")


# Purpose: Implements the jd details backend behavior.
@jd_bp.route("/jds/<int:jd_id>", endpoint="jd_details")
@login_required
def jd_details(jd_id: int):
    payload = jd_details_payload(jd_id)
    if not payload:
        return redirect_to_spa("/jobs")
    return redirect_to_spa(f"/jobs/{jd_id}")


# Purpose: Implements the jd delete backend behavior.
@jd_bp.route("/jds/<int:jd_id>/delete", methods=["POST"], endpoint="jd_delete")
@login_required
def jd_delete(jd_id: int):
    user = current_user()
    if db.delete_jd(jd_id):
        db.log_audit(
            "JD Deleted",
            user["username"] if user else "",
            f"User '{user['username'] if user else 'unknown'}' deleted JD id={jd_id}.",
            None,
        )
    return redirect_to_spa("/jobs")


# Purpose: API endpoint handler for jd list.
@jd_bp.route("/api/jds", endpoint="api_jd_list")
@api_login_required
def api_jd_list():
    return jsonify(jd_summary_list_payload())


# Purpose: API endpoint handler for jd details.
@jd_bp.route("/api/jds/<int:jd_id>", endpoint="api_jd_details")
@api_login_required
def api_jd_details(jd_id: int):
    payload = jd_details_payload(jd_id)
    if not payload:
        return jsonify({"error": "JD not found"}), 404
    return jsonify(payload)


# Purpose: API endpoint handler for create jd.
@jd_bp.route("/api/jds/create", methods=["POST"], endpoint="api_create_jd")
@api_login_required
def api_create_jd():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["file"]
    if not file.filename or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Use PDF or DOCX."}), 400
    try:
        client_id = int(request.form.get("client_id") or 0) or None
        required_count = int(request.form.get("required_candidate_count") or 0)
        if required_count <= 0:
            return jsonify({"error": "required_candidate_count must be greater than zero"}), 400
        job_code = request.form.get("job_code") or ""
        created = create_jd_from_upload(file, current_app.config["UPLOAD_FOLDER"], client_id, required_count, job_code)
        user = current_user()
        db.log_audit(
            "JD Created",
            user["username"] if user else "",
            f"API user '{user['username'] if user else 'unknown'}' created JD '{created['title']}' (id={created['id']}).",
            created["id"],
        )
        workflow = run_automated_bench_workflow(created["id"], username=user["username"] if user else "")
        return jsonify({"success": True, "jd": created["jd"], "workflow": workflow})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# Purpose: API endpoint handler for editing a JD's core fields.
@jd_bp.route("/api/jds/<int:jd_id>", methods=["PUT"], endpoint="api_jd_update")
@api_login_required
def api_jd_update(jd_id: int):
    jd = db.get_jd_by_id(jd_id)
    if not jd:
        return jsonify({"error": "JD not found"}), 404
    data = request.get_json(silent=True) or {}

    if "required_candidate_count" in data:
        try:
            required_count = int(data["required_candidate_count"])
        except (TypeError, ValueError):
            return jsonify({"error": "required_candidate_count must be a number"}), 400
        if required_count <= 0:
            return jsonify({"error": "required_candidate_count must be greater than zero"}), 400
        data["required_candidate_count"] = required_count

    if "title" in data and not str(data.get("title") or "").strip():
        return jsonify({"error": "Title cannot be empty."}), 400

    allowed = {
        "title",
        "job_code",
        "department",
        "location",
        "experience_required",
        "job_category",
        "required_candidate_count",
        "skills",
        "responsibilities",
        "raw_text",
        "status",
    }
    patch = {key: data[key] for key in allowed if key in data}
    if "status" in patch and patch["status"] != jd.get("status") and patch["status"] in {"Closed", "Filled"}:
        return jsonify({"error": "Use Close job to close a JD; Filled is set automatically."}), 400
    if not patch:
        return jsonify({"error": "No editable fields provided."}), 400

    db.update_jd(jd_id, patch)
    user = current_user()
    db.log_audit(
        "JD Updated",
        user["username"] if user else "",
        f"User '{user['username'] if user else 'unknown'}' updated JD '{jd.get('title') or jd_id}' fields: {', '.join(sorted(patch))}.",
        jd_id,
    )
    payload = jd_details_payload(jd_id)
    return jsonify({"success": True, "jd": payload["jd"]})


# Purpose: API endpoint handler for saving a JD's configurable hiring process.
@jd_bp.route("/api/jds/<int:jd_id>/hiring-process", methods=["POST"], endpoint="api_jd_hiring_process")
@api_login_required
@role_required("recruiter")
def api_jd_hiring_process(jd_id: int):
    jd = db.get_jd_by_id(jd_id)
    if not jd:
        return jsonify({"error": "JD not found"}), 404
    data = request.get_json(silent=True) or {}
    steps, error = build_steps(data.get("steps"))
    if error:
        return jsonify({"error": error}), 400
    mappings, error = validate_mappings(steps, data.get("event_mappings"))
    if error:
        return jsonify({"error": error}), 400
    previous_steps = normalize_process(jd.get("hiring_process"))["steps"]
    error = validate_step_removal(jd_id, previous_steps, steps, data.get("event_mappings"))
    if error:
        return jsonify({"error": error}), 400
    db.update_jd(jd_id, {"hiring_process": {"steps": steps, "event_mappings": mappings}})
    user = current_user()
    db.log_audit(
        "Hiring Process Updated",
        user["username"] if user else "",
        f"Updated the hiring process for JD '{jd.get('title') or jd_id}' ({len(steps)} step(s)).",
        jd_id,
    )
    return jsonify({"success": True, "steps": steps, "event_mappings": mappings})


def _username() -> str:
    user = current_user()
    return (user or {}).get("username") or ""


# Purpose: Admin closes a JD that is no longer needed (it will not reopen by itself).
@jd_bp.route("/api/jds/<int:jd_id>/close", methods=["POST"], endpoint="api_jd_close")
@api_login_required
@role_required()
def api_jd_close(jd_id: int):
    if not db.get_jd_by_id(jd_id):
        return jsonify({"error": "JD not found"}), 404
    reason = str((request.get_json(silent=True) or {}).get("reason") or "").strip()
    if not db.close_jd(jd_id, _username(), reason):
        return jsonify({"error": "This job is already closed."}), 400
    db.log_audit("JD Closed", _username(), f"Closed JD id={jd_id}." + (f" Reason: {reason}" if reason else ""), jd_id)
    return jsonify({"success": True, "status": "Closed"})


# Purpose: Admin reopens a closed JD.
@jd_bp.route("/api/jds/<int:jd_id>/reopen", methods=["POST"], endpoint="api_jd_reopen")
@api_login_required
@role_required()
def api_jd_reopen(jd_id: int):
    if not db.get_jd_by_id(jd_id):
        return jsonify({"error": "JD not found"}), 404
    status = db.reopen_jd(jd_id, _username())
    if not status:
        return jsonify({"error": "Only a closed job can be reopened."}), 400
    db.log_audit("JD Reopened", _username(), f"Reopened JD id={jd_id}; status is now {status}.", jd_id)
    return jsonify({"success": True, "status": status})


# Purpose: Records whether a selected candidate joined, dropped out or did not join;
# a drop-out or no-show frees the post and reopens a Filled JD automatically.
@jd_bp.route("/api/jds/<int:jd_id>/candidates/<int:candidate_id>/placement", methods=["POST"], endpoint="api_jd_candidate_placement")
@api_login_required
@role_required("recruiter", "managers_consultant", "hr")
def api_jd_candidate_placement(jd_id: int, candidate_id: int):
    data = request.get_json(silent=True) or {}
    try:
        ok = db.set_candidate_placement(jd_id, candidate_id, data.get("placement_status") or "", data.get("reason") or "", _username())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not ok:
        return jsonify({"error": "This candidate has not been screened for this job."}), 404
    status = data.get("placement_status") or "cleared"
    db.log_audit("Candidate Placement", _username(), f"Set candidate id={candidate_id} placement to {status} for JD id={jd_id}.", jd_id)
    jd = db.get_jd_by_id(jd_id) or {}
    return jsonify({"success": True, "jd_status": jd.get("status"), "filled_count": db.jd_filled_count(jd_id)})


# Purpose: API endpoint handler for jd delete.
@jd_bp.route("/api/jds/<int:jd_id>/delete", methods=["POST"], endpoint="api_jd_delete")
@api_login_required
def api_jd_delete(jd_id: int):
    user = current_user()
    if db.delete_jd(jd_id):
        db.log_audit(
            "JD Deleted",
            user["username"] if user else "",
            f"API user '{user['username'] if user else 'unknown'}' deleted JD id={jd_id}.",
            None,
        )
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Could not delete job description."}), 400


