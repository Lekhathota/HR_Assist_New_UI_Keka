# Backend file purpose: Service-layer business logic for interview features.
from __future__ import annotations

import os
import json
import re
import smtplib
from datetime import datetime, time, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import database as db
from app.llm_extraction import llm_call
from services.candidate_service import candidates_payload, normalize_candidate_record

INTERVIEW_DURATION_MINUTES = 60


# Purpose: Implements the default from email backend behavior.
def default_from_email(user: dict | None = None) -> str:
    return (
        os.environ.get("DEFAULT_FROM_EMAIL")
        or os.environ.get("SMTP_USER")
        or (user or {}).get("email")
        or "hr@localhost"
    )


# Purpose: Parses interview start into structured values.
def parse_interview_start(interview_date: str, interview_time: str) -> datetime:
    raw_date = (interview_date or "").strip()
    raw_time = (interview_time or "").strip()
    if not raw_date or not raw_time:
        raise ValueError("Interview date and time are required.")
    try:
        return datetime.fromisoformat(f"{raw_date}T{raw_time}")
    except ValueError as exc:
        raise ValueError("Use interview_date as YYYY-MM-DD and interview_time as HH:MM.") from exc


# Purpose: Implements the interview window backend behavior.
def interview_window(interview_date: str, interview_time: str) -> tuple[datetime, datetime]:
    start = parse_interview_start(interview_date, interview_time)
    return start, start + timedelta(minutes=INTERVIEW_DURATION_MINUTES)


# Purpose: Implements the day window backend behavior.
def day_window(interview_date: str) -> tuple[datetime, datetime]:
    day = datetime.fromisoformat((interview_date or "").strip())
    start = datetime.combine(day.date(), time.min)
    return start, start + timedelta(days=1)


# Purpose: Validates slot available and raises if it is not allowed.
def assert_slot_available(
    recruiter_id: int,
    interview_start: datetime,
    interview_end: datetime,
    exclude_interview_id: int | None = None,
) -> None:
    if not db.recruiter_slot_is_available(recruiter_id, interview_start, interview_end, exclude_interview_id):
        raise ValueError("This recruiter already has an interview scheduled during that time.")


# Purpose: Implements the candidate selected for jd backend behavior.
def _candidate_selected_for_jd(candidate_id: int, jd_id: int) -> bool:
    for candidate in candidates_payload({"jd_id": jd_id, "status": "Selected"}):
        if int(candidate.get("id") or 0) == int(candidate_id):
            return True
    return False


def candidate_jd_context(candidate_id: int, jd_id: int) -> dict[str, Any]:
    candidate = db.get_candidate_by_id(candidate_id)
    jd = db.get_jd_by_id(jd_id, include_raw_text=False)
    if not candidate:
        raise ValueError("Candidate not found.")
    candidate = normalize_candidate_record(candidate)
    if not jd:
        raise ValueError("Job description not found.")
    if not _candidate_selected_for_jd(candidate_id, jd_id):
        raise ValueError("Only selected candidates can be scheduled for interviews.")
    if not candidate.get("email"):
        raise ValueError("Candidate email is missing.")
    return {"candidate": candidate, "jd": jd}


# Purpose: Schedules context after validation.
def schedule_context(candidate_id: int, jd_id: int) -> dict[str, Any]:
    ctx = candidate_jd_context(candidate_id, jd_id)
    if not db.assessment_allows_scheduling(candidate_id, jd_id):
        raise ValueError("Candidate must pass the assessment before scheduling an interview.")
    return ctx


# Purpose: Implements the llm json with temperature backend behavior.
def _llm_json_with_temperature(prompt: str, temperature: float = 0.7) -> dict:
    raw = llm_call(prompt, temperature=temperature)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {}


# Purpose: Generates interview email from available context.
def generate_interview_email(
    candidate: dict,
    jd: dict,
    interview_date: str,
    interview_time: str,
    from_email: str,
) -> dict[str, str]:
    candidate_name = candidate.get("name") or "Candidate"
    job_role = jd.get("title") or "the role"
    jd_summary = " ".join(
        str(part)
        for part in [
            jd.get("department") or "",
            jd.get("location") or "",
            ", ".join(str(skill) for skill in (jd.get("skills") or [])[:8]),
        ]
        if part
    )
    prompt = f"""
Return ONLY valid JSON with keys "subject" and "body".
Write a polished, senior-recruiter quality interview invitation email.

Details:
- Candidate name: {candidate_name}
- Candidate email: {candidate.get("email") or ""}
- Job role: {job_role}
- Job context: {jd_summary or "Not specified"}
- Interview date: {interview_date}
- Interview time: {interview_time}
- Sender email: {from_email}

Requirements:
- Say the candidate has been selected for an interview for the job role.
- Include the interview date and time exactly as provided.
- Ask the candidate to confirm availability or suggest a conflict promptly.
- Use a warm, confident, professional tone suitable for a corporate recruitment team.
- Make the email feel personally written, not like a generic template.
- Include a clear next-step line and a courteous closing.
- Vary the wording and structure naturally while preserving the same context.
- Keep the body ready to send as plain text.
- Do not invent meeting links, interviewer names, company policies, or documents.
- Do not use markdown.
"""
    generated = _llm_json_with_temperature(prompt)
    subject = (generated.get("subject") or f"Interview Invitation for {job_role}").strip()
    body = (generated.get("body") or "").strip()
    if not body:
        body = (
            f"Dear {candidate_name},\n\n"
            f"Congratulations. You have been selected for an interview for the {job_role} role.\n\n"
            f"Interview Date: {interview_date}\n"
            f"Interview Time: {interview_time}\n\n"
            "Please confirm your availability for this interview.\n\n"
            "Regards,\n"
            "Recruitment Team"
        )
    return {"subject": subject, "body": body}


def generate_followup_email(interview: dict, tone: str = "thanks") -> dict[str, str]:
    candidate_name = interview.get("candidate_name") or "Candidate"
    job_role = interview.get("job_role") or "the role"
    interview_time = str(interview.get("interview_start") or "")
    prompt = f"""
Return ONLY valid JSON with keys "subject" and "body".
Write a concise, professional interview follow-up email.

Details:
- Candidate name: {candidate_name}
- Job role: {job_role}
- Interview time: {interview_time}
- Follow-up type: {tone}

Requirements:
- Do not invent interview outcomes, links, documents, or salary details.
- If the follow-up type is thanks, thank the candidate and say the team will share next steps.
- If the follow-up type is next_round, say the team would like to proceed to the next round.
- If the follow-up type is rejection, write a courteous rejection after interview.
- Keep it ready to send as plain text.
"""
    generated = _llm_json_with_temperature(prompt, temperature=0.5)
    subject = (generated.get("subject") or f"Interview Follow-up for {job_role}").strip()
    body = (generated.get("body") or "").strip()
    if not body:
        body = (
            f"Dear {candidate_name},\n\n"
            f"Thank you for your time discussing the {job_role} role. "
            "Our team will review the discussion and share the next steps shortly.\n\n"
            "Regards,\n"
            "Recruitment Team"
        )
    return {"subject": subject, "body": body}


def generate_cancellation_email(interview: dict, reason_type: str = "schedule_conflict") -> dict[str, str]:
    candidate_name = interview.get("candidate_name") or "Candidate"
    job_role = interview.get("job_role") or "the role"
    interview_time = str(interview.get("interview_start") or "")
    prompt = f"""
Return ONLY valid JSON with keys "subject" and "body".
Write a concise, professional interview cancellation email.

Details:
- Candidate name: {candidate_name}
- Job role: {job_role}
- Interview time: {interview_time}
- Cancellation type: {reason_type}

Requirements:
- Clearly say the scheduled interview is cancelled.
- If the cancellation type is schedule_conflict, say there is a scheduling conflict and the team will share next steps if needed.
- If the cancellation type is role_on_hold, say the hiring process for this role is currently on hold.
- If the cancellation type is position_closed, say the position is no longer moving forward.
- If the cancellation type is candidate_request, acknowledge the candidate's request to cancel.
- Keep the tone respectful and recruiter-facing.
- Do not invent new interview dates, links, salary details, or outcomes.
- Keep it ready to send as plain text.
"""
    generated = _llm_json_with_temperature(prompt, temperature=0.45)
    subject = (generated.get("subject") or f"Interview Cancellation for {job_role}").strip()
    body = (generated.get("body") or "").strip()
    if not body:
        body = (
            f"Dear {candidate_name},\n\n"
            f"We are writing to let you know that the scheduled interview for the {job_role} role has been cancelled.\n\n"
            "Thank you for your understanding. Our recruitment team will share any further updates if needed.\n\n"
            "Regards,\n"
            "Recruitment Team"
        )
    return {"subject": subject, "body": body}


def _twilio_config() -> dict[str, str]:
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID") or ""
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN") or ""
    from_number = os.environ.get("TWILIO_FROM_NUMBER") or os.environ.get("TWILIO_PHONE_NUMBER") or ""
    messaging_service_sid = os.environ.get("TWILIO_MESSAGING_SERVICE_SID") or ""
    if not account_sid or not auth_token:
        raise RuntimeError("Twilio credentials are not configured.")
    if not from_number and not messaging_service_sid:
        raise RuntimeError("Set TWILIO_FROM_NUMBER or TWILIO_MESSAGING_SERVICE_SID.")
    return {
        "account_sid": account_sid,
        "auth_token": auth_token,
        "from_number": from_number,
        "messaging_service_sid": messaging_service_sid,
    }


def send_text_message(to_phone: str, body: str) -> str:
    if not to_phone:
        raise RuntimeError("Candidate phone number is missing.")
    if not body:
        raise RuntimeError("Text message body is missing.")

    try:
        from twilio.rest import Client
    except ImportError as exc:
        raise RuntimeError("Twilio package is not installed.") from exc

    config = _twilio_config()
    client = Client(config["account_sid"], config["auth_token"])
    message_args = {
        "to": to_phone,
        "body": body,
    }
    if config["messaging_service_sid"]:
        message_args["messaging_service_sid"] = config["messaging_service_sid"]
    else:
        message_args["from_"] = config["from_number"]
    try:
        message = client.messages.create(**message_args)
    except Exception as exc:
        raise RuntimeError(f"Could not send text message: {exc}") from exc
    return str(message.sid or "")


# Purpose: Sends email using configured delivery settings.
def send_email(
    to_email: str,
    subject: str,
    body: str,
    from_email: str,
    primary_link: str = "",
    attachment_paths: list[str] | None = None,
) -> None:
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")

    if not smtp_user or not smtp_pass:
        raise RuntimeError("SMTP credentials are not configured.")

    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    for raw_path in attachment_paths or []:
        path = Path(raw_path)
        if not path.is_file():
            continue
        data = path.read_bytes()
        subtype = "pdf" if path.suffix.lower() == ".pdf" else "octet-stream"
        msg.add_attachment(data, maintype="application", subtype=subtype, filename=path.name)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError("SMTP authentication failed. For Gmail, use an app password for SMTP_PASS.") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise RuntimeError(f"Could not send email via SMTP: {exc}") from exc
