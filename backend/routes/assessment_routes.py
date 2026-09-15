"""
HTTP routes for the Assessment module.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from assessment.schemas import (
    SchemaValidationError,
    validate_generate_payload,
    validate_question_create_payload,
    validate_question_update_payload,
    validate_save_answer_payload,
    validate_save_draft_payload,
    validate_send_payload,
    validate_submit_payload,
)
from services.assessment_service import (
    AssessmentServiceError,
    add_question,
    assessment_pipeline_snapshot,
    generate_assessment,
    generate_assessment_email,
    get_assessment_by_token,
    get_assessment_detail,
    get_assessment_result,
    lookup_assessment,
    preview_assessment,
    remove_question,
    save_answer,
    save_assessment_draft,
    send_assessment,
    submit_assessment,
    update_question,
)
from services.auth_service import api_login_required, current_user

assessment_bp = Blueprint("assessment_routes", __name__)


def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _candidate_error(exc: AssessmentServiceError):
    return _json_error(str(exc), getattr(exc, "status_code", 400))


@assessment_bp.route("/api/assessment/generate", methods=["POST"], endpoint="api_assessment_generate")
@api_login_required
def api_assessment_generate():
    user = current_user()
    if not user:
        return _json_error("Unauthorized", 401)
    try:
        payload = validate_generate_payload(request.get_json(silent=True) or {})
        result = generate_assessment(
            recruiter_id=int(user["id"]),
            candidate_id=payload["candidate_id"],
            jd_id=payload["jd_id"],
            passing_score=payload["passing_score"],
            time_limit_minutes=payload["time_limit_minutes"],
            title=payload["title"],
        )
    except SchemaValidationError as exc:
        return _json_error(str(exc), 400)
    except AssessmentServiceError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f"Could not generate assessment: {exc}", 500)
    return jsonify({"success": True, **result})


@assessment_bp.route("/api/assessment/lookup", methods=["GET"], endpoint="api_assessment_lookup")
@api_login_required
def api_assessment_lookup():
    if not current_user():
        return _json_error("Unauthorized", 401)
    try:
        candidate_id = int(request.args.get("candidate_id") or 0)
        jd_id = int(request.args.get("jd_id") or 0)
        if not candidate_id or not jd_id:
            return _json_error("candidate_id and jd_id are required.", 400)
        result = lookup_assessment(candidate_id, jd_id)
    except AssessmentServiceError as exc:
        return _json_error(str(exc), 400)
    except Exception:
        return _json_error("Could not look up assessment.", 500)
    return jsonify(result)


@assessment_bp.route("/api/assessment/pipeline", methods=["GET"], endpoint="api_assessment_pipeline")
@api_login_required
def api_assessment_pipeline():
    if not current_user():
        return _json_error("Unauthorized", 401)
    try:
        limit = int(request.args.get("limit") or 200)
        rows = assessment_pipeline_snapshot(limit=max(1, min(limit, 500)))
    except Exception:
        return _json_error("Could not load assessment pipeline.", 500)
    return jsonify({"pipeline": rows})


@assessment_bp.route("/api/assessment/<int:assessment_id>", methods=["PUT"], endpoint="api_assessment_save_draft")
@api_login_required
def api_assessment_save_draft(assessment_id: int):
    if not current_user():
        return _json_error("Unauthorized", 401)
    try:
        payload = validate_save_draft_payload(request.get_json(silent=True) or {})
        result = save_assessment_draft(assessment_id, payload)
    except SchemaValidationError as exc:
        return _json_error(str(exc), 400)
    except AssessmentServiceError as exc:
        return _json_error(str(exc), 400)
    except Exception:
        return _json_error("Could not save assessment draft.", 500)
    return jsonify({"success": True, **result})


@assessment_bp.route("/api/assessment/<int:assessment_id>", methods=["GET"], endpoint="api_assessment_detail")
@api_login_required
def api_assessment_detail(assessment_id: int):
    if not current_user():
        return _json_error("Unauthorized", 401)
    try:
        result = get_assessment_detail(assessment_id)
    except AssessmentServiceError as exc:
        return _json_error(str(exc), 404)
    except Exception:
        return _json_error("Could not load assessment.", 500)
    return jsonify(result)


@assessment_bp.route("/api/assessment/question", methods=["POST"], endpoint="api_assessment_question_create")
@api_login_required
def api_assessment_question_create():
    if not current_user():
        return _json_error("Unauthorized", 401)
    try:
        payload = validate_question_create_payload(request.get_json(silent=True) or {})
        result = add_question(payload)
    except SchemaValidationError as exc:
        return _json_error(str(exc), 400)
    except AssessmentServiceError as exc:
        return _json_error(str(exc), 400)
    except Exception:
        return _json_error("Could not create question.", 500)
    return jsonify({"success": True, **result})


@assessment_bp.route("/api/assessment/question/<int:question_id>", methods=["PUT"], endpoint="api_assessment_question_update")
@api_login_required
def api_assessment_question_update(question_id: int):
    if not current_user():
        return _json_error("Unauthorized", 401)
    try:
        payload = validate_question_update_payload(request.get_json(silent=True) or {})
        result = update_question(question_id, payload)
    except SchemaValidationError as exc:
        return _json_error(str(exc), 400)
    except AssessmentServiceError as exc:
        return _json_error(str(exc), 400)
    except Exception:
        return _json_error("Could not update question.", 500)
    return jsonify({"success": True, **result})


@assessment_bp.route("/api/assessment/question/<int:question_id>", methods=["DELETE"], endpoint="api_assessment_question_delete")
@api_login_required
def api_assessment_question_delete(question_id: int):
    if not current_user():
        return _json_error("Unauthorized", 401)
    try:
        result = remove_question(question_id)
    except AssessmentServiceError as exc:
        return _json_error(str(exc), 400)
    except Exception:
        return _json_error("Could not delete question.", 500)
    return jsonify(result)


@assessment_bp.route("/api/assessment/<int:assessment_id>/preview", methods=["GET"], endpoint="api_assessment_preview")
@api_login_required
def api_assessment_preview(assessment_id: int):
    if not current_user():
        return _json_error("Unauthorized", 401)
    try:
        result = preview_assessment(assessment_id)
    except AssessmentServiceError as exc:
        return _json_error(str(exc), 404)
    except Exception:
        return _json_error("Could not preview assessment.", 500)
    return jsonify(result)


@assessment_bp.route("/api/assessment/<int:assessment_id>/generate-email", methods=["POST"], endpoint="api_assessment_generate_email")
@api_login_required
def api_assessment_generate_email(assessment_id: int):
    user = current_user()
    if not user:
        return _json_error("Unauthorized", 401)
    try:
        payload = validate_send_payload(request.get_json(silent=True) or {})
        result = generate_assessment_email(
            assessment_id,
            recruiter=user,
            to_email_override=payload["to_email"],
        )
    except SchemaValidationError as exc:
        return _json_error(str(exc), 400)
    except AssessmentServiceError as exc:
        return _json_error(str(exc), 400)
    except Exception:
        return _json_error("Could not generate assessment email.", 500)
    return jsonify(result)


@assessment_bp.route("/api/assessment/<int:assessment_id>/send", methods=["POST"], endpoint="api_assessment_send")
@api_login_required
def api_assessment_send(assessment_id: int):
    user = current_user()
    if not user:
        return _json_error("Unauthorized", 401)
    try:
        payload = validate_send_payload(request.get_json(silent=True) or {})
        result = send_assessment(
            assessment_id,
            recruiter=user,
            subject=payload["subject"],
            body=payload["body"],
            regenerate_email=payload["regenerate_email"],
            to_email_override=payload["to_email"],
        )
    except SchemaValidationError as exc:
        return _json_error(str(exc), 400)
    except AssessmentServiceError as exc:
        return _json_error(str(exc), 400)
    except RuntimeError as exc:
        return _json_error(str(exc), 503)
    except Exception as exc:
        return _json_error(f"Could not send assessment: {exc}", 500)
    return jsonify(result)


@assessment_bp.route("/api/assessment/token/<token>", methods=["GET"], endpoint="api_assessment_by_token")
def api_assessment_by_token(token: str):
    """Public candidate endpoint — secured by UUID access token."""
    try:
        result = get_assessment_by_token(token)
    except AssessmentServiceError as exc:
        return _candidate_error(exc)
    except Exception:
        return _json_error("Could not load assessment.", 500)
    return jsonify(result)


@assessment_bp.route("/api/assessment/save-answer", methods=["POST"], endpoint="api_assessment_save_answer")
def api_assessment_save_answer():
    """Public candidate endpoint — secured by UUID access token in request body."""
    try:
        payload = validate_save_answer_payload(request.get_json(silent=True) or {})
        result = save_answer(payload["token"], payload["question_id"], payload["answer"])
    except SchemaValidationError as exc:
        return _json_error(str(exc), 400)
    except AssessmentServiceError as exc:
        return _candidate_error(exc)
    except Exception:
        return _json_error("Could not save answer.", 500)
    return jsonify(result)


@assessment_bp.route("/api/assessment/submit", methods=["POST"], endpoint="api_assessment_submit")
def api_assessment_submit():
    """Public candidate endpoint — secured by UUID access token in request body."""
    try:
        payload = validate_submit_payload(request.get_json(silent=True) or {})
        result = submit_assessment(payload["token"], payload["answers"])
    except SchemaValidationError as exc:
        return _json_error(str(exc), 400)
    except AssessmentServiceError as exc:
        return _candidate_error(exc)
    except Exception:
        return _json_error("Could not submit assessment.", 500)
    return jsonify({"success": True, **result})


@assessment_bp.route("/api/assessment/result/<int:assessment_id>", methods=["GET"], endpoint="api_assessment_result")
@api_login_required
def api_assessment_result(assessment_id: int):
    if not current_user():
        return _json_error("Unauthorized", 401)
    try:
        result = get_assessment_result(assessment_id)
    except AssessmentServiceError as exc:
        return _json_error(str(exc), 404)
    except Exception:
        return _json_error("Could not load assessment result.", 500)
    return jsonify(result)
