# Backend file purpose: Flask route handlers for jd features.
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, redirect, request

import database as db
from spa_urls import redirect_to_spa

from services.auth_service import api_login_required, current_user, login_required
from services.fulfilment_service import run_automated_bench_workflow
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
            created = create_jd_from_upload(file, current_app.config["UPLOAD_FOLDER"], client_id, required_count)
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
        created = create_jd_from_upload(file, current_app.config["UPLOAD_FOLDER"], client_id, required_count)
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


