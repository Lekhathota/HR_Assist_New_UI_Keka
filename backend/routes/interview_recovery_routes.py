# Backend file purpose: Flask routes for automated interview reschedule and no-show recovery.
from __future__ import annotations

import hmac
import logging
import os

from flask import Blueprint, jsonify, request

import database as db
from interview_recovery.config import RecoveryConfigError
from interview_recovery.models import RecoveryStatus
from interview_recovery.service import RecoveryError, get_service
from services.auth_service import api_login_required, current_user

logger = logging.getLogger("recruitment.interview_recovery")

interview_recovery_bp = Blueprint("interview_recovery_routes", __name__)


def _error(exc: Exception):
    if isinstance(exc, RecoveryConfigError):
        return jsonify({"error": f"Interview recovery is misconfigured: {exc}"}), 503
    if isinstance(exc, RecoveryError):
        return jsonify({"error": str(exc)}), exc.status_code
    if isinstance(exc, ValueError):
        return jsonify({"error": str(exc)}), 400
    logger.exception("Interview recovery request failed")
    return jsonify({"error": "Interview recovery request failed."}), 500


def _owned_interview(interview_id: int, user: dict):
    interview = db.get_interview_by_id(interview_id)
    if not interview or int(interview.get("recruiter_id") or 0) != int(user["id"]):
        return None
    return interview


# ------------------------------------------------------------ recruiter APIs
@interview_recovery_bp.route("/api/interviews/<int:interview_id>/recovery/reschedule-request", methods=["POST"],
                             endpoint="api_recovery_log_reschedule_request")
@api_login_required
def api_recovery_log_reschedule_request(interview_id: int):
    """Recruiter logs a reschedule request the candidate sent by email/phone; automation takes over."""
    user = current_user()
    if not user or not _owned_interview(interview_id, user):
        return jsonify({"error": "Interview not found"}), 404
    data = request.get_json(silent=True) or {}
    try:
        case = get_service().request_reschedule(
            interview_id, source="recruiter_logged", actor=user.get("username") or "",
            reason=str(data.get("reason") or "").strip(), preferred_windows=data.get("preferred_windows"))
    except Exception as exc:
        return _error(exc)
    return jsonify({"success": True, "case": case})


@interview_recovery_bp.route("/api/interviews/<int:interview_id>/attendance", methods=["POST"],
                             endpoint="api_recovery_attendance")
@api_login_required
def api_recovery_attendance(interview_id: int):
    user = current_user()
    if not user or not _owned_interview(interview_id, user):
        return jsonify({"error": "Interview not found"}), 404
    data = request.get_json(silent=True) or {}
    try:
        result = get_service().report_attendance(interview_id, str(data.get("attendance") or ""),
                                                 actor=user.get("username") or "")
    except Exception as exc:
        return _error(exc)
    return jsonify({"success": True, **result})


@interview_recovery_bp.route("/api/interview-recovery/cases", methods=["GET"], endpoint="api_recovery_cases")
@api_login_required
def api_recovery_cases():
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    raw = (request.args.get("status") or "").strip()
    statuses = [s.strip().upper() for s in raw.split(",") if s.strip()] or None
    if statuses and any(s not in RecoveryStatus.OPEN | RecoveryStatus.TERMINAL | {RecoveryStatus.PROCESSING} for s in statuses):
        return jsonify({"error": "Unknown recovery status filter."}), 400
    try:
        cases = get_service().list_cases_for_recruiter(int(user["id"]), statuses)
    except Exception as exc:
        return _error(exc)
    return jsonify({"cases": cases})


@interview_recovery_bp.route("/api/interview-recovery/cases/<int:case_id>", methods=["GET"], endpoint="api_recovery_case")
@api_login_required
def api_recovery_case(case_id: int):
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return jsonify({"case": get_service().get_case_for_recruiter(case_id, int(user["id"]))})
    except Exception as exc:
        return _error(exc)


@interview_recovery_bp.route("/api/interview-recovery/cases/<int:case_id>/retry", methods=["POST"], endpoint="api_recovery_retry")
@api_login_required
def api_recovery_retry(case_id: int):
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        case = get_service().retry_case(case_id, recruiter_id=int(user["id"]), actor=user.get("username") or "")
    except Exception as exc:
        return _error(exc)
    return jsonify({"success": True, "case": case})


@interview_recovery_bp.route("/api/interview-recovery/cases/<int:case_id>/close", methods=["POST"], endpoint="api_recovery_close")
@api_login_required
def api_recovery_close(case_id: int):
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    try:
        case = get_service().close_case(case_id, recruiter_id=int(user["id"]), actor=user.get("username") or "",
                                        note=str(data.get("note") or ""))
    except Exception as exc:
        return _error(exc)
    return jsonify({"success": True, "case": case})


# ------------------------------------------------------------ scheduler tick
@interview_recovery_bp.route("/api/interview-recovery/run", methods=["GET", "POST"], endpoint="api_recovery_run")
def api_recovery_run():
    """Called by Vercel Cron (or any scheduler) with Authorization: Bearer <secret>."""
    secret = (os.environ.get("INTERVIEW_RECOVERY_CRON_SECRET") or os.environ.get("CRON_SECRET") or "").strip()
    if not secret:
        return jsonify({"error": "Set INTERVIEW_RECOVERY_CRON_SECRET (or CRON_SECRET) to enable the scheduler endpoint."}), 503
    supplied = (request.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), secret.encode()):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        summary = get_service().run_due(limit=int(request.args.get("limit") or 50))
    except Exception as exc:
        return _error(exc)
    return jsonify({"success": True, **summary})


# ------------------------------------------------------- candidate (public)
@interview_recovery_bp.route("/api/interview-recovery/public/<token>", methods=["GET"], endpoint="api_recovery_public_view")
def api_recovery_public_view(token: str):
    try:
        return jsonify(get_service().public_view(token))
    except Exception as exc:
        return _error(exc)


@interview_recovery_bp.route("/api/interview-recovery/public/<token>/reschedule", methods=["POST"],
                             endpoint="api_recovery_public_reschedule")
def api_recovery_public_reschedule(token: str):
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(get_service().public_request_reschedule(
            token, str(data.get("reason") or "").strip(), data.get("preferred_windows")))
    except Exception as exc:
        return _error(exc)


@interview_recovery_bp.route("/api/interview-recovery/public/<token>/respond", methods=["POST"],
                             endpoint="api_recovery_public_respond")
def api_recovery_public_respond(token: str):
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("wants_reschedule"), bool):
        return jsonify({"error": "wants_reschedule must be true or false."}), 400
    try:
        return jsonify(get_service().public_respond(token, data["wants_reschedule"]))
    except Exception as exc:
        return _error(exc)


@interview_recovery_bp.route("/api/interview-recovery/public/<token>/confirm", methods=["POST"],
                             endpoint="api_recovery_public_confirm")
def api_recovery_public_confirm(token: str):
    data = request.get_json(silent=True) or {}
    chosen = str(data.get("slot_id") or "").strip()
    if not chosen:
        return jsonify({"error": "slot_id is required."}), 400
    try:
        result = get_service().public_confirm_slot(token, chosen)
    except Exception as exc:
        return _error(exc)
    return jsonify(result), (409 if result.get("slot_unavailable") else 200)
