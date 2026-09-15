# Backend file purpose: Flask route handlers for interview features.
from __future__ import annotations

from flask import Blueprint, jsonify, request

import database as db
from services.auth_service import api_login_required, current_user
from services.interview_service import (
    assert_slot_available,
    day_window,
    default_from_email,
    generate_cancellation_email,
    generate_followup_email,
    generate_interview_email,
    interview_window,
    schedule_context,
    send_email,
    send_text_message,
)

interview_bp = Blueprint("interview_routes", __name__)


def _with_candidate_phone(interview: dict) -> dict:
    candidate_id = int(interview.get("candidate_id") or 0)
    if not candidate_id or interview.get("candidate_phone"):
        return interview
    candidate = db.get_candidate_by_id(candidate_id) or {}
    return {**interview, "candidate_phone": candidate.get("phone") or ""}


# Purpose: API endpoint handler for interview defaults.
@interview_bp.route("/api/interviews/defaults", endpoint="api_interview_defaults")
@api_login_required
def api_interview_defaults():
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"from_email": default_from_email(user)})


# Purpose: API endpoint handler for interview blocked slots.
@interview_bp.route("/api/interviews/blocked-slots", endpoint="api_interview_blocked_slots")
@api_login_required
def api_interview_blocked_slots():
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    interview_date = (request.args.get("date") or "").strip()
    exclude_interview_id = int(request.args.get("exclude_interview_id") or 0)
    if not interview_date:
        return jsonify({"error": "date is required"}), 400
    try:
        start, end = day_window(interview_date)
    except ValueError:
        return jsonify({"error": "Use date as YYYY-MM-DD."}), 400

    rows = [
        row
        for row in db.get_interviews_for_recruiter_on_day(int(user["id"]), start, end)
        if not exclude_interview_id or int(row.get("id") or 0) != exclude_interview_id
    ]
    blocked_slots = [
        {
            "start": str(row.get("interview_start") or "")[11:16],
            "end": str(row.get("interview_end") or "")[11:16],
            "candidate_name": row.get("candidate_name") or "",
            "job_role": row.get("job_role") or "",
        }
        for row in rows
    ]
    return jsonify({"blocked_slots": blocked_slots})


@interview_bp.route("/api/interviews", endpoint="api_interviews")
@api_login_required
def api_interviews():
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    rows = db.get_interviews({"recruiter_id": int(user["id"])})
    rows = [_with_candidate_phone(row) for row in rows]
    return jsonify({"interviews": rows})


# Purpose: API endpoint handler for generate interview email.
@interview_bp.route("/api/interviews/generate-email", methods=["POST"], endpoint="api_generate_interview_email")
@api_login_required
def api_generate_interview_email():
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    try:
        candidate_id = int(data.get("candidate_id") or 0)
        jd_id = int(data.get("jd_id") or 0)
        interview_date = str(data.get("interview_date") or "").strip()
        interview_time = str(data.get("interview_time") or "").strip()
        exclude_interview_id = int(data.get("exclude_interview_id") or 0)
        interview_start, interview_end = interview_window(interview_date, interview_time)
        assert_slot_available(int(user["id"]), interview_start, interview_end, exclude_interview_id or None)
        ctx = schedule_context(candidate_id, jd_id)
        from_email = default_from_email(user)
        email = generate_interview_email(
            ctx["candidate"],
            ctx["jd"],
            interview_date,
            interview_time,
            from_email,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Could not generate interview email."}), 500

    return jsonify(
        {
            "from_email": from_email,
            "to_email": ctx["candidate"].get("email") or "",
            "subject": email["subject"],
            "body": email["body"],
            "interview_start": interview_start.isoformat(),
            "interview_end": interview_end.isoformat(),
        }
    )


# Purpose: API endpoint handler for schedule interview.
@interview_bp.route("/api/interviews/schedule", methods=["POST"], endpoint="api_schedule_interview")
@api_login_required
def api_schedule_interview():
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    try:
        candidate_id = int(data.get("candidate_id") or 0)
        jd_id = int(data.get("jd_id") or 0)
        interview_date = str(data.get("interview_date") or "").strip()
        interview_time = str(data.get("interview_time") or "").strip()
        subject = str(data.get("subject") or "").strip()
        body = str(data.get("body") or "").strip()
        interviewer = str(data.get("interviewer") or "").strip()
        interview_mode = str(data.get("interview_mode") or "Online").strip()
        meeting_link = str(data.get("meeting_link") or "").strip()
        notes = str(data.get("notes") or "").strip()
        text_body = str(data.get("text_body") or "").strip()
        if not subject or not body:
            return jsonify({"error": "Email subject and body are required."}), 400
        if not interviewer:
            return jsonify({"error": "Interviewer is required."}), 400
        if interview_mode.lower() == "online" and not meeting_link:
            return jsonify({"error": "Meeting link is required for online interviews."}), 400

        interview_start, interview_end = interview_window(interview_date, interview_time)
        assert_slot_available(int(user["id"]), interview_start, interview_end)
        ctx = schedule_context(candidate_id, jd_id)
        from_email = default_from_email(user)
        to_email = ctx["candidate"].get("email") or ""
        send_email(to_email, subject, body, from_email)
        text_error = ""
        if text_body:
            try:
                send_text_message(ctx["candidate"].get("phone") or "", text_body)
            except Exception as exc:
                text_error = str(exc)
        interview_id = db.create_interview(
            {
                "candidate_id": candidate_id,
                "candidate_email": to_email,
                "candidate_name": ctx["candidate"].get("name") or "",
                "jd_id": jd_id,
                "job_role": ctx["jd"].get("title") or "",
                "recruiter_id": int(user["id"]),
                "recruiter_email": user.get("email") or "",
                "interview_start": interview_start,
                "interview_end": interview_end,
                "interviewer": interviewer,
                "interview_mode": interview_mode,
                "meeting_link": meeting_link,
                "notes": notes,
                "text_body": text_body,
                "from_email": from_email,
                "to_email": to_email,
                "email_subject": subject,
                "email_body": body,
                "email_status": "sent",
                "email_sent_at": db._now(),
                "text_status": "sent",
                "text_error": text_error,
                "text_sent_at": db._now(),
                "status": "Scheduled",
            }
        )
        db.update_candidate(candidate_id, {"hiring_stage": "Interview Scheduled"})
        db.log_audit(
            "Interview Scheduled",
            user.get("username") or "",
            f"Scheduled interview for '{ctx['candidate'].get('name') or to_email}' against JD '{ctx['jd'].get('title') or jd_id}'.",
            jd_id,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception:
        return jsonify({"error": "Could not send email or schedule interview."}), 500

    return jsonify({"success": True, "interview_id": interview_id})


@interview_bp.route("/api/interviews/<int:interview_id>/reschedule", methods=["POST"], endpoint="api_reschedule_interview")
@api_login_required
def api_reschedule_interview(interview_id: int):
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    interview = db.get_interview_by_id(interview_id)
    if not interview or int(interview.get("recruiter_id") or 0) != int(user["id"]):
        return jsonify({"error": "Interview not found"}), 404

    data = request.get_json(silent=True) or {}
    try:
        interview_date = str(data.get("interview_date") or "").strip()
        interview_time = str(data.get("interview_time") or "").strip()
        interviewer = str(data.get("interviewer") or "").strip()
        interview_mode = str(data.get("interview_mode") or "Online").strip()
        meeting_link = str(data.get("meeting_link") or "").strip()
        notes = str(data.get("notes") or "").strip()
        subject = str(data.get("subject") or "").strip()
        body = str(data.get("body") or "").strip()
        text_body = str(data.get("text_body") or "").strip()
        if not interviewer:
            return jsonify({"error": "Interviewer is required."}), 400
        if interview_mode.lower() == "online" and not meeting_link:
            return jsonify({"error": "Meeting link is required for online interviews."}), 400
        if not subject or not body:
            return jsonify({"error": "Email subject and body are required."}), 400

        interview_start, interview_end = interview_window(interview_date, interview_time)
        assert_slot_available(int(user["id"]), interview_start, interview_end, interview_id)
        text_error = ""
        if text_body:
            candidate = db.get_candidate_by_id(int(interview.get("candidate_id") or 0)) or {}
            try:
                send_text_message(candidate.get("phone") or "", text_body)
            except Exception as exc:
                text_error = str(exc)
        db.update_interview(
            interview_id,
            {
                "interview_start": interview_start,
                "interview_end": interview_end,
                "interviewer": interviewer,
                "interview_mode": interview_mode,
                "meeting_link": meeting_link,
                "notes": notes,
                "email_subject": subject,
                "email_body": body,
                "text_body": text_body,
                "text_error": text_error,
                "status": "Rescheduled",
            },
        )
        db.update_candidate(int(interview.get("candidate_id") or 0), {"hiring_stage": "Interview Rescheduled"})
        updated = _with_candidate_phone(db.get_interview_by_id(interview_id) or {})
        db.log_audit(
            "Interview Rescheduled",
            user.get("username") or "",
            f"Rescheduled interview for '{interview.get('candidate_name') or interview.get('to_email')}'.",
            interview.get("jd_id"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Could not reschedule interview."}), 500
    return jsonify({"success": True, "interview": updated})


@interview_bp.route("/api/interviews/<int:interview_id>/generate-followup", methods=["POST"], endpoint="api_generate_followup")
@api_login_required
def api_generate_followup(interview_id: int):
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    interview = db.get_interview_by_id(interview_id)
    if not interview or int(interview.get("recruiter_id") or 0) != int(user["id"]):
        return jsonify({"error": "Interview not found"}), 404
    data = request.get_json(silent=True) or {}
    try:
        draft = generate_followup_email(interview, str(data.get("type") or "thanks"))
    except Exception:
        return jsonify({"error": "Could not generate follow-up email."}), 500
    return jsonify({"success": True, **draft})


@interview_bp.route("/api/interviews/<int:interview_id>/send-followup", methods=["POST"], endpoint="api_send_followup")
@api_login_required
def api_send_followup(interview_id: int):
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    interview = db.get_interview_by_id(interview_id)
    if not interview or int(interview.get("recruiter_id") or 0) != int(user["id"]):
        return jsonify({"error": "Interview not found"}), 404
    data = request.get_json(silent=True) or {}
    subject = str(data.get("subject") or "").strip()
    body = str(data.get("body") or "").strip()
    if not subject or not body:
        return jsonify({"error": "Follow-up subject and body are required."}), 400
    try:
        send_email(interview.get("to_email") or interview.get("candidate_email") or "", subject, body, default_from_email(user))
        db.update_interview(
            interview_id,
            {
                "followup_subject": subject,
                "followup_body": body,
                "followup_status": "sent",
                "followup_sent_at": db._now(),
            },
        )
        db.log_audit(
            "Interview Follow-up Sent",
            user.get("username") or "",
            f"Sent follow-up to '{interview.get('candidate_name') or interview.get('to_email')}'.",
            interview.get("jd_id"),
        )
    except RuntimeError as exc:
        db.update_interview(interview_id, {"followup_status": "failed"})
        return jsonify({"error": str(exc)}), 503
    except Exception:
        db.update_interview(interview_id, {"followup_status": "failed"})
        return jsonify({"error": "Could not send follow-up email."}), 500
    return jsonify({"success": True})


@interview_bp.route("/api/interviews/<int:interview_id>/outcome", methods=["POST"], endpoint="api_interview_outcome")
@api_login_required
def api_interview_outcome(interview_id: int):
    return _update_interview_outcome(interview_id)


@interview_bp.route("/api/interviews/outcome", methods=["POST"], endpoint="api_interview_outcome_fallback")
@api_login_required
def api_interview_outcome_fallback():
    data = request.get_json(silent=True) or {}
    try:
        interview_id = int(data.get("interview_id") or 0)
    except (TypeError, ValueError):
        interview_id = 0
    if not interview_id:
        return jsonify({"error": "interview_id is required."}), 400
    return _update_interview_outcome(interview_id, data)


def _update_interview_outcome(interview_id: int, payload: dict | None = None):
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    interview = db.get_interview_by_id(interview_id)
    if not interview or int(interview.get("recruiter_id") or 0) != int(user["id"]):
        return jsonify({"error": "Interview not found"}), 404

    data = payload if payload is not None else (request.get_json(silent=True) or {})
    outcome = str(data.get("outcome") or "").strip().lower()
    if outcome not in {"selected", "rejected"}:
        return jsonify({"error": "Outcome must be selected or rejected."}), 400

    status = "Client Interview Pending" if outcome == "selected" else "Rejected After Interview"
    action = "Interview Candidate Selected" if outcome == "selected" else "Interview Candidate Rejected"
    try:
        db.update_interview(interview_id, {"status": status})
    except Exception as exc:
        return jsonify({"error": f"Could not update interview outcome: {exc}"}), 500

    candidate_id = int(interview.get("candidate_id") or 0)
    if candidate_id:
        try:
            db.update_candidate(candidate_id, {"hiring_stage": status})
        except Exception:
            pass

    try:
        db.log_audit(
            action,
            user.get("username") or "",
            f"Marked interview outcome for '{interview.get('candidate_name') or interview.get('to_email')}' as {status}.",
            int(interview["jd_id"]) if interview.get("jd_id") not in {None, ""} else None,
        )
    except Exception:
        pass

    updated = _with_candidate_phone(db.get_interview_by_id(interview_id) or {**interview, "status": status})
    return jsonify({"success": True, "interview": updated})


@interview_bp.route("/api/interviews/<int:interview_id>/generate-cancellation", methods=["POST"], endpoint="api_generate_cancellation")
@api_login_required
def api_generate_cancellation(interview_id: int):
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    interview = db.get_interview_by_id(interview_id)
    if not interview or int(interview.get("recruiter_id") or 0) != int(user["id"]):
        return jsonify({"error": "Interview not found"}), 404
    data = request.get_json(silent=True) or {}
    try:
        draft = generate_cancellation_email(interview, str(data.get("type") or "schedule_conflict"))
    except Exception:
        return jsonify({"error": "Could not generate cancellation email."}), 500
    return jsonify({"success": True, **draft})


@interview_bp.route("/api/interviews/<int:interview_id>/send-cancellation", methods=["POST"], endpoint="api_send_cancellation")
@api_login_required
def api_send_cancellation(interview_id: int):
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    interview = db.get_interview_by_id(interview_id)
    if not interview or int(interview.get("recruiter_id") or 0) != int(user["id"]):
        return jsonify({"error": "Interview not found"}), 404
    data = request.get_json(silent=True) or {}
    cancel_type = str(data.get("type") or "schedule_conflict").strip()
    subject = str(data.get("subject") or "").strip()
    body = str(data.get("body") or "").strip()
    if not subject or not body:
        return jsonify({"error": "Cancellation subject and body are required."}), 400
    try:
        send_email(interview.get("to_email") or interview.get("candidate_email") or "", subject, body, default_from_email(user))
        db.update_interview(
            interview_id,
            {
                "status": "Cancelled",
                "cancellation_type": cancel_type,
                "cancellation_subject": subject,
                "cancellation_body": body,
                "cancellation_status": "sent",
                "cancellation_sent_at": db._now(),
            },
        )
        db.update_candidate(int(interview.get("candidate_id") or 0), {"hiring_stage": "Interview Cancelled"})
        updated = db.get_interview_by_id(interview_id) or {}
        db.log_audit(
            "Interview Cancelled",
            user.get("username") or "",
            f"Cancelled interview for '{interview.get('candidate_name') or interview.get('to_email')}'.",
            interview.get("jd_id"),
        )
    except RuntimeError as exc:
        db.update_interview(interview_id, {"cancellation_status": "failed"})
        return jsonify({"error": str(exc)}), 503
    except Exception:
        db.update_interview(interview_id, {"cancellation_status": "failed"})
        return jsonify({"error": "Could not send cancellation email."}), 500
    return jsonify({"success": True, "interview": updated})
