from __future__ import annotations

import os
from typing import Any

from flask import current_app

import database as db
from email_utils import is_valid_email, normalize_email
from services.interview_service import default_from_email, send_email


class VendorServiceError(ValueError):
    pass


def _clean_status(value: Any) -> str:
    status = str(value or "Active").strip().title()
    return status if status in {"Active", "Inactive"} else "Active"


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _vendor_payload(data: dict, *, partial: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    text_fields = ("vendor_name", "company_name", "contact_person", "phone", "notes")
    for field in text_fields:
        if field in data or not partial:
            payload[field] = str(data.get(field) or "").strip()

    if "status" in data or not partial:
        payload["status"] = _clean_status(data.get("status"))
    if "supported_categories" in data or not partial:
        payload["supported_categories"] = _list(data.get("supported_categories"))
    if "supported_sub_tags" in data or not partial:
        payload["supported_sub_tags"] = _list(data.get("supported_sub_tags"))

    if "email" in data or not partial:
        email = normalize_email(str(data.get("email") or ""))
        if not is_valid_email(email):
            raise VendorServiceError("A valid vendor email is required.")
        payload["email"] = email
        payload["email_normalized"] = email.lower()

    if not partial and not (payload.get("vendor_name") or payload.get("company_name")):
        raise VendorServiceError("Vendor name or company name is required.")
    return payload


def list_vendors(filters: dict | None = None) -> list[dict]:
    return db.get_all_vendors(filters or {})


def create_vendor(data: dict) -> dict:
    payload = _vendor_payload(data)
    existing = db.get_vendor_by_email(payload["email_normalized"])
    if existing:
        raise VendorServiceError("A vendor with this email already exists.")
    vendor_id = db.create_vendor(payload)
    vendor = db.get_vendor_by_id(vendor_id)
    if not vendor:
        raise VendorServiceError("Vendor could not be created.")
    return vendor


def update_vendor(vendor_id: int, data: dict) -> dict:
    if not db.get_vendor_by_id(vendor_id):
        raise VendorServiceError("Vendor not found.")
    payload = _vendor_payload(data, partial=True)
    if payload.get("email_normalized"):
        existing = db.get_vendor_by_email(payload["email_normalized"])
        if existing and int(existing.get("id") or 0) != int(vendor_id):
            raise VendorServiceError("A vendor with this email already exists.")
    db.update_vendor(vendor_id, payload)
    vendor = db.get_vendor_by_id(vendor_id)
    if not vendor:
        raise VendorServiceError("Vendor not found.")
    return vendor


def delete_vendor(vendor_id: int) -> None:
    if not db.soft_delete_vendor(vendor_id):
        raise VendorServiceError("Vendor not found.")


def assign_vendors(jd_id: int, vendor_ids: list[Any], user: dict | None = None) -> list[dict]:
    jd = db.get_jd_by_id(jd_id, include_raw_text=False)
    if not jd:
        raise VendorServiceError("JD not found.")
    cleaned_ids = []
    for raw_id in vendor_ids:
        try:
            vendor_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise VendorServiceError("Vendor IDs must be numbers.") from exc
        if vendor_id in cleaned_ids:
            continue
        vendor = db.get_vendor_by_id(vendor_id)
        if not vendor:
            raise VendorServiceError(f"Vendor {vendor_id} not found.")
        if str(vendor.get("status") or "") != "Active":
            raise VendorServiceError(f"Vendor {vendor_id} is inactive.")
        cleaned_ids.append(vendor_id)
    return db.assign_vendors_to_jd(
        jd_id,
        cleaned_ids,
        assigned_by=int(user["id"]) if user and user.get("id") is not None else None,
        assigned_by_username=str((user or {}).get("username") or ""),
    )


def vendor_jds(vendor_id: int) -> dict[str, Any]:
    vendor = db.get_vendor_by_id(vendor_id)
    if not vendor:
        raise VendorServiceError("Vendor not found.")
    active_assignments = db.get_vendor_jd_assignments(vendor_id)
    assigned_ids = {int(row.get("jd_id") or 0) for row in active_assignments}
    jobs = []
    for jd in db.get_all_jds({"status": "Active"}):
        jobs.append(
            {
                "id": jd.get("id"),
                "title": jd.get("title") or "",
                "client_name": jd.get("client_name") or "ShimentoX",
                "location": jd.get("location") or "",
                "status": jd.get("status") or "Active",
                "assigned": int(jd.get("id") or 0) in assigned_ids,
            }
        )
    return {"vendor": vendor, "jobs": jobs, "assigned_jd_ids": sorted(assigned_ids)}


def assign_jds_to_vendor(vendor_id: int, jd_ids: list[Any], user: dict | None = None) -> dict[str, Any]:
    vendor = db.get_vendor_by_id(vendor_id)
    if not vendor:
        raise VendorServiceError("Vendor not found.")
    if str(vendor.get("status") or "") != "Active":
        raise VendorServiceError("Vendor is inactive.")

    cleaned_ids = []
    for raw_id in jd_ids:
        try:
            jd_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise VendorServiceError("JD IDs must be numbers.") from exc
        if jd_id in cleaned_ids:
            continue
        jd = db.get_jd_by_id(jd_id, include_raw_text=False)
        if not jd:
            raise VendorServiceError(f"JD {jd_id} not found.")
        cleaned_ids.append(jd_id)

    db.assign_jds_to_vendor(
        vendor_id,
        cleaned_ids,
        assigned_by=int(user["id"]) if user and user.get("id") is not None else None,
        assigned_by_username=str((user or {}).get("username") or ""),
    )
    return vendor_jds(vendor_id)


def remove_assignment(jd_id: int, vendor_id: int) -> None:
    if not db.remove_vendor_assignment(jd_id, vendor_id):
        raise VendorServiceError("Vendor assignment not found.")


def assigned_vendors(jd_id: int) -> list[dict]:
    if not db.get_jd_by_id(jd_id, include_raw_text=False):
        raise VendorServiceError("JD not found.")
    return db.get_jd_vendor_assignments(jd_id)


def _ensure_pair_can_be_assigned(jd_id: int, vendor_id: int) -> tuple[dict, dict]:
    jd = db.get_jd_by_id(jd_id, include_raw_text=False)
    vendor = db.get_vendor_by_id(vendor_id)
    if not jd:
        raise VendorServiceError("JD not found.")
    if not vendor:
        raise VendorServiceError("Vendor not found.")
    if str(vendor.get("status") or "") != "Active":
        raise VendorServiceError("Vendor is inactive.")
    return jd, vendor


def _add_single_assignment(jd_id: int, vendor_id: int, user: dict | None = None) -> None:
    current_ids = [int(row.get("id") or 0) for row in db.get_jd_vendor_assignments(jd_id)]
    wanted = list(dict.fromkeys([*current_ids, int(vendor_id)]))
    db.assign_vendors_to_jd(
        jd_id,
        wanted,
        assigned_by=int(user["id"]) if user and user.get("id") is not None else None,
        assigned_by_username=str((user or {}).get("username") or ""),
    )


def _jd_text_block(jd: dict) -> str:
    structured = jd.get("structured_data") if isinstance(jd.get("structured_data"), dict) else {}
    skills = jd.get("skills") or structured.get("required_skills") or []
    responsibilities = jd.get("responsibilities") or structured.get("responsibilities") or []
    employment_type = structured.get("employment_type") or structured.get("job_type") or ""
    apply_instructions = structured.get("apply_instructions") or structured.get("application_instructions") or ""
    description = structured.get("job_description") or structured.get("description") or jd.get("raw_text") or ""

    lines = [
        f"JD Title: {jd.get('title') or 'Not specified'}",
        f"Client: {jd.get('client_name') or 'ShimentoX'}",
        f"Location: {jd.get('location') or 'Not specified'}",
        f"Experience: {jd.get('experience_required') or jd.get('experience') or 'Not specified'}",
    ]
    if employment_type:
        lines.append(f"Employment Type: {employment_type}")
    if skills:
        lines.append(f"Skills: {', '.join(str(skill) for skill in skills)}")
    if responsibilities:
        lines.extend(["", "Responsibilities:"])
        lines.extend(f"- {item}" for item in responsibilities[:12])
    elif description:
        lines.extend(["", "Job Description:", str(description)[:2500]])
    if apply_instructions:
        lines.extend(["", "Apply Instructions:", str(apply_instructions)])
    return "\n".join(lines)


def _jd_attachment_paths(jd: dict) -> list[str]:
    upload_folder = current_app.config.get("UPLOAD_FOLDER", "") if current_app else ""
    candidates: list[str] = []
    for key in ("file_name", "file", "uploaded_file", "upload_filename", "jd_file", "source_file", "original_filename"):
        value = str(jd.get(key) or "").strip()
        if value:
            candidates.append(value)

    paths: list[str] = []
    for raw in candidates:
        filename = os.path.basename(raw)
        for path in (raw, os.path.join(upload_folder, filename) if upload_folder else filename):
            if path and os.path.isfile(path) and path not in paths:
                paths.append(path)

    if paths or not upload_folder or not os.path.isdir(upload_folder):
        return paths

    title_key = "".join(ch for ch in str(jd.get("title") or "").lower() if ch.isalnum())
    if not title_key:
        return []
    for filename in os.listdir(upload_folder):
        path = os.path.join(upload_folder, filename)
        if not os.path.isfile(path):
            continue
        stem_key = "".join(ch for ch in os.path.splitext(filename)[0].lower() if ch.isalnum())
        if title_key and (title_key in stem_key or stem_key in title_key):
            return [path]
    return []


def generate_vendor_email(jd_id: int, vendor_id: int, user: dict | None = None, *, require_assignment: bool = False) -> dict[str, str]:
    jd = db.get_jd_by_id(jd_id, include_raw_text=True)
    vendor = db.get_vendor_by_id(vendor_id)
    assignment = db.get_active_jd_vendor_assignment(jd_id, vendor_id)
    if not jd:
        raise VendorServiceError("JD not found.")
    if not vendor:
        raise VendorServiceError("Vendor not found.")
    if require_assignment and not assignment:
        raise VendorServiceError("Assign this vendor to the JD before sending email.")
    to_email = normalize_email(vendor.get("email"))
    if not is_valid_email(to_email):
        raise VendorServiceError("Vendor email is invalid.")

    vendor_name = vendor.get("contact_person") or vendor.get("vendor_name") or vendor.get("company_name") or "Team"
    from services.fulfilment_service import get_fulfilment
    fulfilment = get_fulfilment(jd_id)
    subject = f"JD Requirement: {jd.get('title') or 'Role'}"
    body = (
        f"Hello {vendor_name},\n\n"
        f"Please share {int(fulfilment.get('remaining_vendor_requirement') or 0)} suitable profiles for this role. "
        f"The total requirement is {int(fulfilment.get('total_required') or 0)}, with "
        f"{int(fulfilment.get('selected_bench_count') or 0)} already fulfilled from the internal bench.\n\n"
        f"{_jd_text_block(jd)}\n\n"
        "Regards,\n"
        "Recruitment Team"
    )
    return {
        "from_email": default_from_email(user),
        "to_email": to_email,
        "subject": subject,
        "body": body,
        "attachments": [os.path.basename(path) for path in _jd_attachment_paths(jd)],
    }


def assign_and_send_vendor_email(jd_id: int, vendor_id: int, data: dict, user: dict | None = None) -> dict:
    _ensure_pair_can_be_assigned(jd_id, vendor_id)
    already_assigned = db.get_active_jd_vendor_assignment(jd_id, vendor_id) is not None
    if not already_assigned:
        _add_single_assignment(jd_id, vendor_id, user)
    try:
        return send_vendor_email(jd_id, vendor_id, data, user)
    except Exception:
        if not already_assigned:
            db.remove_vendor_assignment(jd_id, vendor_id)
        raise


def send_vendor_email(jd_id: int, vendor_id: int, data: dict, user: dict | None = None) -> dict:
    draft = generate_vendor_email(jd_id, vendor_id, user)
    subject = str(data.get("subject") or draft["subject"]).strip()
    body = str(data.get("body") or draft["body"]).strip()
    to_email = normalize_email(str(data.get("to_email") or draft["to_email"]))
    if not subject or not body:
        raise VendorServiceError("Email subject and body are required.")
    if not is_valid_email(to_email):
        raise VendorServiceError("A valid recipient email is required.")

    assignment = db.get_active_jd_vendor_assignment(jd_id, vendor_id)
    if not assignment:
        raise VendorServiceError("Vendor assignment not found.")

    retry_count = db.count_vendor_email_attempts(jd_id, vendor_id)
    sent_at = db._now()
    status = "sent"
    error_message = ""
    try:
        jd = db.get_jd_by_id(jd_id, include_raw_text=False) or {}
        attachment_paths = [
            *_jd_attachment_paths(jd),
            *(path for path in data.get("manual_attachment_paths") or [] if path),
        ]
        send_email(to_email, subject, body, draft["from_email"], attachment_paths=attachment_paths)
    except RuntimeError as exc:
        status = "failed"
        error_message = str(exc)
    except Exception as exc:
        status = "failed"
        error_message = f"Could not send vendor email: {exc}"

    log_id = db.create_vendor_email_log(
        {
            "assignment_id": assignment["id"],
            "vendor_id": vendor_id,
            "jd_id": jd_id,
            "subject": subject,
            "body": body,
            "status": status,
            "sent_by": (user or {}).get("id"),
            "sent_by_username": (user or {}).get("username") or "",
            "sent_at": sent_at,
            "retry_count": retry_count,
            "error_message": error_message,
        }
    )
    db.update_vendor_assignment_email_status(int(assignment["id"]), status, log_id, sent_at)
    if status != "sent":
        raise VendorServiceError(error_message or "Could not send vendor email.")
    return {"success": True, "email_log_id": log_id}


def email_history(jd_id: int, vendor_id: int) -> list[dict]:
    return db.get_vendor_email_history(jd_id, vendor_id)


def candidate_history(jd_id: int, vendor_id: int) -> list[dict]:
    return db.get_vendor_candidates_for_jd(jd_id, vendor_id)
