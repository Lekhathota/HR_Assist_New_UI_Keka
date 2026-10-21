"""
HTTP routes for the Assessment module.
"""

from __future__ import annotations

import re

from flask import Blueprint, Response, jsonify, request

from assessment.schemas import (
    SchemaValidationError,
    validate_generate_payload,
    validate_question_create_payload,
    validate_question_update_payload,
    validate_run_payload,
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
    generate_jd_exam,
    generate_assessment_email,
    get_assessment_by_token,
    get_assessment_detail,
    get_assessment_result,
    get_proctoring_evidence,
    get_proctoring_snapshot,
    get_recording_chunk,
    lookup_assessment,
    preview_assessment,
    regrade_assessment,
    regenerate_question,
    approve_assessment,
    get_assessment_versions,
    get_code_attempts,
    publication_check,
    return_to_draft,
    remove_question,
    get_reference_config,
    save_reference_config,
    verify_reference_solution,
    run_candidate_code,
    save_answer,
    save_assessment_draft,
    send_assessment,
    submit_assessment,
    start_candidate_assessment,
    report_proctoring_violation,
    store_face_snapshot,
    store_recording_chunk,
    update_question,
)
from services.auth_service import api_login_required, current_user, role_required
from services.coding_question_service import (
    add_spec,
    discard_draft,
    generate_spec_question,
    get_coding_config,
    remove_spec,
    save_client_prompt,
    save_spec_question,
    update_spec,
    verify_spec_draft,
)
from services.mcq_question_service import generate_mcq_draft, save_mcq_question
from services.candidate_assessment_service import (
    AssessmentWorkflowError,
    list_candidate_assessments,
    send_assessment_to_candidate,
)

assessment_bp = Blueprint("assessment_routes", __name__)


def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _candidate_error(exc: AssessmentServiceError):
    return _json_error(str(exc), getattr(exc, "status_code", 400))


PROCTORING_REASONS = frozenset({
    "tab_hidden", "window_blur", "fullscreen_exit", "back_navigation", "navigation_attempt",
    "browser_shortcut", "page_unload", "media_stopped",
})
FACE_ISSUES = frozenset({"", "no_face", "looking_away", "camera_unavailable"})
_CLIENT_ID = re.compile(r"^[A-Za-z0-9-]{1,80}$")
MAX_SNAPSHOT_BYTES = 1024 * 1024
# Vercel rejects request bodies above 4.5 MB; the recorder targets far smaller timeslices.
MAX_RECORDING_CHUNK_BYTES = 4 * 1024 * 1024
MAX_RECORDING_SEQUENCE = 20000


def _valid_client_id(value) -> bool:
    return isinstance(value, str) and bool(_CLIENT_ID.match(value))


def _uploaded_bytes(field: str, limit: int, allowed_prefix: str):
    upload = request.files.get(field)
    if upload is None:
        return None, None, f"A {field} file is required."
    mime_type = str(upload.mimetype or "").split(";")[0].strip().lower()
    if not mime_type.startswith(allowed_prefix):
        return None, None, f"Unsupported {field} type."
    data = upload.read(limit + 1)
    if not data:
        return None, None, f"The {field} file is empty."
    if len(data) > limit:
        return None, None, f"The {field} file is too large."
    return data, mime_type, None


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


@assessment_bp.route("/api/candidates/<int:candidate_id>/assessments", methods=["GET"],
                     endpoint="api_candidate_assessments")
@api_login_required
@role_required("recruiter")
def api_candidate_assessments(candidate_id: int):
    try:
        return jsonify(list_candidate_assessments(candidate_id))
    except AssessmentWorkflowError as exc:
        return jsonify(exc.payload()), exc.status_code
    except Exception:
        return _json_error("Could not load assessments for this candidate.", 500)


# Shared by the Talent table and All Details: generate (or reuse) and email an assessment for a chosen JD.
@assessment_bp.route("/api/candidates/<int:candidate_id>/assessments/send", methods=["POST"],
                     endpoint="api_candidate_assessment_send")
@api_login_required
@role_required("recruiter")
def api_candidate_assessment_send(candidate_id: int):
    user = current_user()
    data = request.get_json(silent=True) or {}
    try:
        jd_id = int(data.get("jd_id") or 0)
    except (TypeError, ValueError):
        jd_id = 0
    if jd_id < 1:
        return jsonify({"error": "Select a job description.", "code": "invalid_jd"}), 400
    try:
        result = send_assessment_to_candidate(
            candidate_id,
            jd_id=jd_id,
            recruiter=user,
            request_id=str(data.get("request_id") or ""),
            to_email=str(data.get("to_email") or ""),
            resend=data.get("resend") is True,
        )
    except AssessmentWorkflowError as exc:
        return jsonify(exc.payload()), exc.status_code
    except AssessmentServiceError as exc:
        return jsonify({"error": str(exc), "code": "invalid_request"}), getattr(exc, "status_code", 400)
    except Exception:
        return jsonify({"error": "Could not send the assessment. Please retry.", "code": "server_error"}), 500
    # 202: the link is live but delivery could not be confirmed.
    return jsonify(result), 202 if result.get("code") == "delivery_unknown" else 200


def _coding_call(action, failure: str = "Could not update coding questions. Please retry."):
    """Shared error mapping for the Coding Questions and AI question endpoints."""
    if not current_user():
        return _json_error("Unauthorized", 401)
    try:
        return jsonify({"success": True, **action()})
    except AssessmentServiceError as exc:
        return _json_error(str(exc), getattr(exc, "status_code", 400))
    except Exception:
        return _json_error(failure, 500)


@assessment_bp.route("/api/assessment/<int:assessment_id>/coding", methods=["GET"], endpoint="api_assessment_coding_config")
@api_login_required
def api_assessment_coding_config(assessment_id: int):
    return _coding_call(lambda: get_coding_config(assessment_id))


@assessment_bp.route("/api/assessment/<int:assessment_id>/coding/client-prompt", methods=["PUT"],
                     endpoint="api_assessment_coding_client_prompt")
@api_login_required
def api_assessment_coding_client_prompt(assessment_id: int):
    data = request.get_json(silent=True) or {}
    return _coding_call(lambda: save_client_prompt(assessment_id, data.get("prompt", ""),
                                                   save_as_client_default=data.get("save_as_client_default") is True))


@assessment_bp.route("/api/assessment/<int:assessment_id>/coding/specs", methods=["POST"], endpoint="api_assessment_coding_spec_add")
@api_login_required
def api_assessment_coding_spec_add(assessment_id: int):
    return _coding_call(lambda: add_spec(assessment_id, request.get_json(silent=True) or {}))


@assessment_bp.route("/api/assessment/<int:assessment_id>/coding/specs/<spec_id>", methods=["PUT"],
                     endpoint="api_assessment_coding_spec_update")
@api_login_required
def api_assessment_coding_spec_update(assessment_id: int, spec_id: str):
    return _coding_call(lambda: update_spec(assessment_id, spec_id, request.get_json(silent=True) or {}))


@assessment_bp.route("/api/assessment/<int:assessment_id>/coding/specs/<spec_id>", methods=["DELETE"],
                     endpoint="api_assessment_coding_spec_remove")
@api_login_required
def api_assessment_coding_spec_remove(assessment_id: int, spec_id: str):
    return _coding_call(lambda: remove_spec(assessment_id, spec_id))


@assessment_bp.route("/api/assessment/<int:assessment_id>/coding/specs/<spec_id>/generate", methods=["POST"],
                     endpoint="api_assessment_coding_spec_generate")
@api_login_required
def api_assessment_coding_spec_generate(assessment_id: int, spec_id: str):
    return _coding_call(lambda: generate_spec_question(assessment_id, spec_id, request.get_json(silent=True) or {}))


@assessment_bp.route("/api/assessment/<int:assessment_id>/coding/specs/<spec_id>/save", methods=["POST"],
                     endpoint="api_assessment_coding_spec_save")
@api_login_required
def api_assessment_coding_spec_save(assessment_id: int, spec_id: str):
    """Validate the reviewed draft question and add it to the assessment."""
    return _coding_call(lambda: save_spec_question(assessment_id, spec_id, request.get_json(silent=True) or {}))


@assessment_bp.route("/api/assessment/<int:assessment_id>/coding/specs/<spec_id>/draft", methods=["DELETE"],
                     endpoint="api_assessment_coding_spec_discard_draft")
@api_login_required
def api_assessment_coding_spec_discard_draft(assessment_id: int, spec_id: str):
    return _coding_call(lambda: discard_draft(assessment_id, spec_id))


@assessment_bp.route("/api/assessment/<int:assessment_id>/coding/specs/<spec_id>/draft/verify", methods=["POST"],
                     endpoint="api_assessment_coding_spec_verify_draft")
@api_login_required
def api_assessment_coding_spec_verify_draft(assessment_id: int, spec_id: str):
    """Execute the reviewed draft's reference solution against its tests; nothing is added or sent."""
    return _coding_call(lambda: verify_spec_draft(assessment_id, spec_id, request.get_json(silent=True) or {}),
                        "Could not validate the reference solution. Please retry.")


@assessment_bp.route("/api/assessment/<int:assessment_id>/mcq/generate", methods=["POST"], endpoint="api_assessment_mcq_generate")
@api_login_required
def api_assessment_mcq_generate(assessment_id: int):
    """Generate one MCQ draft for review. Nothing is stored or sent."""
    return _coding_call(lambda: generate_mcq_draft(assessment_id, request.get_json(silent=True) or {}),
                        "Could not generate the question. Please retry.")


@assessment_bp.route("/api/assessment/<int:assessment_id>/mcq/save", methods=["POST"], endpoint="api_assessment_mcq_save")
@api_login_required
def api_assessment_mcq_save(assessment_id: int):
    """Add the reviewed MCQ to the draft assessment (idempotent per request_id). Nothing is sent."""
    return _coding_call(lambda: save_mcq_question(assessment_id, request.get_json(silent=True) or {}),
                        "Could not save the question. Please retry.")


@assessment_bp.route("/api/assessment/exam/generate", methods=["POST"])
@api_login_required
def api_jd_exam_generate():
    try:
        data = request.get_json(silent=True) or {}
        jd_id = int(data.get("jd_id") or 0)
        if jd_id < 1:
            return _json_error("A valid jd_id is required.")
        return jsonify(generate_jd_exam(jd_id))
    except AssessmentServiceError as exc:
        return _json_error(str(exc), exc.status_code)
    except (ValueError, TypeError, AttributeError):
        return _json_error("A valid jd_id is required.")


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
            confirm=payload["confirm"],
            reviewed_fingerprint=payload["reviewed_fingerprint"],
            request_id=payload["request_id"],
        )
    except SchemaValidationError as exc:
        return _json_error(str(exc), 400)
    except AssessmentServiceError as exc:
        return _json_error(str(exc), exc.status_code)
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
        result = save_answer(payload["token"], payload["question_id"], payload["answer"], payload["language"])
    except SchemaValidationError as exc:
        return _json_error(str(exc), 400)
    except AssessmentServiceError as exc:
        return _candidate_error(exc)
    except Exception:
        return _json_error("Could not save answer.", 500)
    return jsonify(result)


@assessment_bp.route("/api/assessment/execution-status", methods=["GET"], endpoint="api_assessment_execution_status")
@api_login_required
def api_assessment_execution_status():
    from assessment.code_execution.verification import execution_status

    return jsonify(execution_status())


@assessment_bp.route("/api/assessment/question/<int:question_id>/reference", methods=["GET", "PUT"], endpoint="api_assessment_reference")
@api_login_required
def api_assessment_reference(question_id: int):
    """Recruiter: read or save a question's reference solution and test cases (incl. hidden)."""
    user = current_user() or {}
    try:
        if request.method == "GET":
            return jsonify(get_reference_config(question_id))
        return jsonify(save_reference_config(question_id, request.get_json(silent=True) or {}, actor=user.get("username") or ""))
    except AssessmentServiceError as exc:
        return _json_error(str(exc), exc.status_code)
    except Exception:
        return _json_error("Could not update the reference solution.", 500)


@assessment_bp.route("/api/assessment/question/<int:question_id>/verify", methods=["POST"], endpoint="api_assessment_reference_verify")
@api_login_required
def api_assessment_reference_verify(question_id: int):
    """Recruiter: execute the reference solution against the enabled test cases."""
    user = current_user() or {}
    try:
        return jsonify(verify_reference_solution(question_id, actor=user.get("username") or ""))
    except AssessmentServiceError as exc:
        return _json_error(str(exc), exc.status_code)
    except Exception:
        return _json_error("Could not verify the reference solution.", 500)


def _recruiter_call(action, failure: str):
    """Shared error mapping for recruiter assessment-lifecycle endpoints."""
    user = current_user() or {}
    try:
        return jsonify(action(user.get("username") or ""))
    except AssessmentServiceError as exc:
        return _json_error(str(exc), exc.status_code)
    except Exception:
        return _json_error(failure, 500)


@assessment_bp.route("/api/assessment/<int:assessment_id>/publish-check", methods=["GET"], endpoint="api_assessment_publish_check")
@api_login_required
def api_assessment_publish_check(assessment_id: int):
    """Recruiter: what must be fixed before the assessment can be approved and sent."""
    return _recruiter_call(lambda actor: publication_check(assessment_id), "Could not check the assessment.")


@assessment_bp.route("/api/assessment/question/<int:question_id>/regenerate", methods=["POST"], endpoint="api_assessment_question_regenerate")
@api_login_required
def api_assessment_question_regenerate(question_id: int):
    """Recruiter: replace one draft question with a freshly generated one (same position and marks)."""
    return _recruiter_call(lambda actor: regenerate_question(question_id, actor=actor), "Could not regenerate the question.")


@assessment_bp.route("/api/assessment/<int:assessment_id>/approve", methods=["POST"], endpoint="api_assessment_approve")
@api_login_required
def api_assessment_approve(assessment_id: int):
    return _recruiter_call(lambda actor: approve_assessment(assessment_id, actor=actor), "Could not approve the assessment.")


@assessment_bp.route("/api/assessment/<int:assessment_id>/return-to-draft", methods=["POST"], endpoint="api_assessment_return_to_draft")
@api_login_required
def api_assessment_return_to_draft(assessment_id: int):
    return _recruiter_call(lambda actor: return_to_draft(assessment_id, actor=actor), "Could not return the assessment to draft.")


@assessment_bp.route("/api/assessment/<int:assessment_id>/versions", methods=["GET"], endpoint="api_assessment_versions")
@api_login_required
def api_assessment_versions(assessment_id: int):
    return _recruiter_call(lambda actor: get_assessment_versions(assessment_id), "Could not load published versions.")


@assessment_bp.route("/api/assessment/<int:assessment_id>/code-attempts", methods=["GET"], endpoint="api_assessment_code_attempts")
@api_login_required
def api_assessment_code_attempts(assessment_id: int):
    """Recruiter: the candidate's code runs and submissions (code is visible to signed-in recruiters only)."""
    return _recruiter_call(lambda actor: get_code_attempts(assessment_id), "Could not load the attempt history.")


@assessment_bp.route("/api/assessment/<int:assessment_id>/regrade", methods=["POST"], endpoint="api_assessment_regrade")
@api_login_required
def api_assessment_regrade(assessment_id: int):
    """Recruiter: score the saved final answers again with the current coding/SQL graders."""
    user = current_user() or {}
    try:
        return jsonify(regrade_assessment(assessment_id, actor=user.get("username") or ""))
    except AssessmentServiceError as exc:
        return _json_error(str(exc), exc.status_code)
    except Exception as exc:
        return _json_error(f"Could not re-grade assessment: {exc}", 500)


@assessment_bp.route("/api/assessment/run-code", methods=["POST"], endpoint="api_assessment_run_code")
def api_assessment_run_code():
    """Public candidate endpoint: run an answer against the visible sample tests only."""
    try:
        payload = validate_run_payload(request.get_json(silent=True) or {})
        result = run_candidate_code(payload["token"], payload["question_id"], payload["code"], payload["language"])
    except SchemaValidationError as exc:
        return _json_error(str(exc), 400)
    except AssessmentServiceError as exc:
        return _candidate_error(exc)
    except Exception:
        return _json_error("Could not run the code.", 500)
    return jsonify(result)


@assessment_bp.route("/api/assessment/start", methods=["POST"])
def api_assessment_start():
    try:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return _json_error("A JSON object is required.")
        return jsonify(start_candidate_assessment(
            payload.get("token"),
            accepted_terms=payload.get("accepted_terms") is True,
            recording_consent=payload.get("recording_consent") is True,
        ))
    except AssessmentServiceError as exc:
        return _candidate_error(exc)
    except Exception:
        return _json_error("Could not start assessment.", 500)


@assessment_bp.route("/api/assessment/proctoring-event", methods=["POST"])
def api_assessment_proctoring_event():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return _json_error("A JSON object is required.")
    event_id = payload.get("event_id")
    reason = payload.get("reason")
    if not _valid_client_id(event_id):
        return _json_error("A valid event_id is required.")
    if not isinstance(reason, str) or reason not in PROCTORING_REASONS:
        return _json_error("Invalid proctoring event reason.")
    try:
        return jsonify(report_proctoring_violation(payload.get("token"), event_id, reason))
    except AssessmentServiceError as exc:
        return _candidate_error(exc)
    except Exception:
        return _json_error("Could not record exam violation.", 500)


@assessment_bp.route("/api/assessment/proctoring/snapshot", methods=["POST"])
def api_assessment_proctoring_snapshot():
    """Public candidate endpoint: multipart face photo plus the browser's face-check result."""
    form = request.form
    snapshot_id, kind, issue = form.get("snapshot_id"), form.get("kind"), form.get("issue", "")
    if not _valid_client_id(snapshot_id):
        return _json_error("A valid snapshot_id is required.")
    if kind not in {"reference", "periodic"}:
        return _json_error("Invalid snapshot kind.")
    if issue not in FACE_ISSUES:
        return _json_error("Invalid face check issue.")
    try:
        face_count = int(form.get("face_count", "0"))
    except ValueError:
        return _json_error("face_count must be a number.")
    if not 0 <= face_count <= 20:
        return _json_error("face_count is out of range.")
    face_ok = form.get("face_ok") == "true" and face_count >= 1 and not issue
    image, mime_type, problem = _uploaded_bytes("image", MAX_SNAPSHOT_BYTES, "image/")
    if problem:
        return _json_error(problem)
    try:
        return jsonify(store_face_snapshot(form.get("token"), snapshot_id=snapshot_id, kind=kind, image=image,
                                           mime_type=mime_type, face_count=face_count, face_ok=face_ok,
                                           issue=issue or ("" if face_ok else "no_face")))
    except AssessmentServiceError as exc:
        return _candidate_error(exc)
    except Exception:
        return _json_error("Could not store exam photo.", 500)


@assessment_bp.route("/api/assessment/proctoring/recording", methods=["POST"])
def api_assessment_proctoring_recording():
    """Public candidate endpoint: one MediaRecorder timeslice of the camera or screen recording."""
    form = request.form
    stream, session_id = form.get("stream"), form.get("session_id")
    if stream not in {"camera", "screen"}:
        return _json_error("Invalid recording stream.")
    if not _valid_client_id(session_id):
        return _json_error("A valid session_id is required.")
    try:
        sequence = int(form.get("sequence", ""))
    except ValueError:
        return _json_error("sequence must be a number.")
    if not 0 <= sequence <= MAX_RECORDING_SEQUENCE:
        return _json_error("sequence is out of range.")
    data, mime_type, problem = _uploaded_bytes("chunk", MAX_RECORDING_CHUNK_BYTES, "video/")
    if problem:
        return _json_error(problem)
    try:
        return jsonify(store_recording_chunk(form.get("token"), stream=stream, session_id=session_id,
                                             sequence=sequence, data=data, mime_type=mime_type))
    except AssessmentServiceError as exc:
        return _candidate_error(exc)
    except Exception:
        return _json_error("Could not store exam recording.", 500)


@assessment_bp.route("/api/assessment/<int:assessment_id>/proctoring", methods=["GET"])
@api_login_required
def api_assessment_proctoring_evidence(assessment_id: int):
    if not current_user():
        return _json_error("Unauthorized", 401)
    try:
        return jsonify(get_proctoring_evidence(assessment_id))
    except AssessmentServiceError as exc:
        return _candidate_error(exc)


@assessment_bp.route("/api/assessment/<int:assessment_id>/proctoring/snapshots/<snapshot_id>", methods=["GET"])
@api_login_required
def api_assessment_proctoring_snapshot_image(assessment_id: int, snapshot_id: str):
    if not current_user():
        return _json_error("Unauthorized", 401)
    if not _valid_client_id(snapshot_id):
        return _json_error("Invalid snapshot id.")
    try:
        image, mime_type = get_proctoring_snapshot(assessment_id, snapshot_id)
    except AssessmentServiceError as exc:
        return _candidate_error(exc)
    return Response(image, mimetype=mime_type, headers={"Cache-Control": "private, max-age=3600"})


@assessment_bp.route("/api/assessment/<int:assessment_id>/proctoring/recordings/<stream>/<session_id>/<int:sequence>", methods=["GET"])
@api_login_required
def api_assessment_proctoring_recording_chunk(assessment_id: int, stream: str, session_id: str, sequence: int):
    if not current_user():
        return _json_error("Unauthorized", 401)
    if stream not in {"camera", "screen"} or not _valid_client_id(session_id):
        return _json_error("Invalid recording reference.")
    try:
        data, mime_type = get_recording_chunk(assessment_id, stream, session_id, sequence)
    except AssessmentServiceError as exc:
        return _candidate_error(exc)
    return Response(data, mimetype=mime_type, headers={"Cache-Control": "private, max-age=3600"})


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
