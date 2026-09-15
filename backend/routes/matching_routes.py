# Backend file purpose: Flask route handlers for matching features.
from __future__ import annotations

import os

from flask import Blueprint, current_app, jsonify, redirect, request

import database as db
from orchestration.main_orchestrator import run_main_orchestrator
from spa_urls import redirect_to_spa
from security.policy import PolicyEngine, ToolRequest

from services.auth_service import api_login_required, current_user, login_required
from services.fulfilment_service import get_fulfilment, recalculate_fulfilment, run_automated_bench_workflow
from services.jd_service import allowed_file, unique_upload_filename

matching_bp = Blueprint("matching_routes", __name__)


# Purpose: Implements the collect resume files backend behavior.
def _collect_resume_files():
    """Accept common multipart field names used by web, mobile, and API clients."""
    keys = (
        "resumes",
        "resumes[]",
        "resume",
        "resume[]",
        "files",
        "file",
        "file[]",
        "upload",
        "uploads",
        "attachment",
        "attachments",
    )
    files = []
    for key in keys:
        files.extend(request.files.getlist(key))
    out = []
    seen: set[tuple[str, int]] = set()
    for f in files:
        if not f or not getattr(f, "filename", ""):
            continue
        marker = (f.filename, id(f))
        if marker in seen:
            continue
        seen.add(marker)
        out.append(f)
    return out


# Purpose: Implements the save resume items backend behavior.
def _save_resume_items(resume_files) -> tuple[list[dict[str, str]], int]:
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    resume_items: list[dict[str, str]] = []
    skipped_bad_ext = 0
    for rf in resume_files:
        if not rf or not rf.filename:
            continue
        if not allowed_file(rf.filename):
            skipped_bad_ext += 1
            continue
        filename = unique_upload_filename(rf.filename or "")
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
        rf.save(path)
        resume_items.append({"filename": filename, "original_filename": rf.filename or "", "path": path})
    return resume_items, skipped_bad_ext


# Purpose: Implements the run agentic compare backend behavior.
def _run_agentic_compare(jd_id: str, username: str = "") -> dict:
    resume_files = _collect_resume_files()
    resume_items, skipped_bad_ext = _save_resume_items(resume_files)
    source_vendor_id = int(request.form.get("source_vendor_id") or 0)
    source_vendor = db.get_vendor_by_id(source_vendor_id) if source_vendor_id else None
    if source_vendor:
        for item in resume_items:
            item["source_vendor_id"] = source_vendor_id
            item["source_vendor_name"] = source_vendor.get("vendor_name") or source_vendor.get("company_name") or source_vendor.get("email") or ""
    candidate_ids = request.form.getlist("candidate_ids")
    result = run_main_orchestrator(
        {
            "task_type": "screening",
            "jd_id": int(jd_id),
            "candidate_ids": candidate_ids,
            "resume_items": resume_items,
        },
        username=username,
    )
    ranked = result.get("ranked_candidates") or []
    result["resume_parts_received"] = len(resume_files)
    result["resume_parts_skipped_bad_ext"] = skipped_bad_ext
    result["uploaded_count"] = len(resume_items)
    result["processed_count"] = len(ranked)
    result["existing_count"] = len(candidate_ids)
    return result


# Purpose: Implements the compare backend behavior.
@matching_bp.route("/compare", methods=["GET", "POST"], endpoint="compare")
@login_required
def compare():
    if request.method == "POST":
        jd_id = request.form.get("jd_id")
        if not jd_id:
            return redirect_to_spa("/analyze")
        try:
            user = current_user()
            result = _run_agentic_compare(jd_id, username=user["username"] if user else "")
            received = int(result.get("resume_parts_received") or 0)
            skipped_ext = int(result.get("resume_parts_skipped_bad_ext") or 0)
            uploaded_count = int(result.get("uploaded_count") or 0)
            processed_count = int(result.get("processed_count") or 0)
            existing_count = int(result.get("existing_count") or 0)
            summary = result.get("summary") or {}
            db.log_audit(
                "Screening Run",
                user["username"] if user else "",
                f"User '{user['username'] if user else 'unknown'}' screened JD '{summary.get('jd_title') or jd_id}' "
                f"(id={jd_id}). File parts received: {received}, PDF/DOCX queued: {uploaded_count}, "
                f"non-PDF/DOCX skipped: {skipped_ext}, processed OK: {processed_count}, "
                f"existing candidates in run: {existing_count}, selected: {len(result.get('selected_results') or [])}, "
                f"rejected: {len(result.get('rejected_results') or [])}.",
                int(jd_id),
            )
            return redirect_to_spa("/analyze")
        except Exception as exc:
            current_app.logger.exception("compare resume: %s", exc)
            return redirect_to_spa("/analyze")
    return redirect_to_spa("/analyze")


# Purpose: API endpoint handler for compare.
@matching_bp.route("/api/compare", methods=["POST"], endpoint="api_compare")
@api_login_required
def api_compare():
    jd_id = request.form.get("jd_id")
    if not jd_id:
        return jsonify({"error": "Please select a Job Description"}), 400
    try:
        user = current_user()
        result = run_automated_bench_workflow(int(jd_id), username=user["username"] if user else "")
        summary = result.get("summary") or {}
        db.log_audit(
            "Bench Workflow Completed",
            user["username"] if user else "",
            f"Automated bench workflow completed for JD id={jd_id}; "
            f"selected={len((result.get('bench_results') or {}).get('selected') or [])}, "
            f"remaining={int((result.get('fulfilment_summary') or {}).get('remaining_vendor_requirement') or 0)}.",
            int(jd_id),
        )
        bench = result.get("bench_results") or {}
        return jsonify(
            {
                "run_id": result.get("run_id"),
                "results": (bench.get("selected") or []) + (bench.get("waitlisted") or []) + (bench.get("rejected") or []),
                "selected_results": bench.get("selected") or [],
                "waitlisted_results": bench.get("waitlisted") or [],
                "rejected_results": bench.get("rejected") or [],
                "fulfilment_summary": result.get("fulfilment_summary") or {},
                "vendor_assignments": result.get("vendor_assignments") or [],
                "summary": summary,
            }
        )
    except Exception as exc:
        current_app.logger.exception("api compare: %s", exc)
        return jsonify({"error": str(exc)}), 500


@matching_bp.route("/api/jds/<int:jd_id>/fulfilment", methods=["GET"], endpoint="api_jd_fulfilment")
@api_login_required
def api_jd_fulfilment(jd_id: int):
    try:
        return jsonify(get_fulfilment(jd_id))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@matching_bp.route("/api/jds/<int:jd_id>/fulfilment/recalculate", methods=["POST"], endpoint="api_jd_fulfilment_recalculate")
@api_login_required
def api_jd_fulfilment_recalculate(jd_id: int):
    try:
        user = current_user()
        decision = PolicyEngine().check(ToolRequest("jd.fulfilment.recalculate", user=user or {}, confirmed=True))
        if not decision.allowed:
            return jsonify({"error": decision.reason}), 403
        result = recalculate_fulfilment(jd_id)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("fulfilment recalculate: %s", exc)
        return jsonify({"error": str(exc)}), 500


