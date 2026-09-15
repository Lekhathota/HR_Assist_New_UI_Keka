from __future__ import annotations

import os

from flask import Blueprint, current_app, jsonify, request

import database as db
from services.auth_service import api_login_required, current_user
from security.policy import PolicyEngine, ToolRequest
from services.jd_service import unique_upload_filename
from services.vendor_service import (
    VendorServiceError,
    assign_and_send_vendor_email,
    assign_jds_to_vendor,
    assigned_vendors,
    assign_vendors,
    candidate_history,
    create_vendor,
    delete_vendor,
    email_history,
    generate_vendor_email,
    list_vendors,
    remove_assignment,
    send_vendor_email,
    update_vendor,
    vendor_jds,
)
from services.fulfilment_service import accept_vendor_candidate, recalculate_fulfilment

vendor_bp = Blueprint("vendor_routes", __name__)


def _save_vendor_email_attachments() -> list[str]:
    paths: list[str] = []
    files = request.files.getlist("attachments") + request.files.getlist("attachment")
    if not files:
        return paths
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "vendor_email_attachments")
    os.makedirs(folder, exist_ok=True)
    for file in files:
        if not file or not file.filename:
            continue
        filename = unique_upload_filename(file.filename)
        if not filename:
            continue
        path = os.path.join(folder, filename)
        file.save(path)
        paths.append(path)
    return paths


@vendor_bp.route("/api/vendors", methods=["GET"], endpoint="api_vendors")
@api_login_required
def api_vendors():
    filters = {
        "search": request.args.get("search") or "",
        "status": request.args.get("status") or "Active",
        "sort": request.args.get("sort") or "company_name",
    }
    return jsonify({"vendors": list_vendors(filters)})


@vendor_bp.route("/api/vendors", methods=["POST"], endpoint="api_create_vendor")
@api_login_required
def api_create_vendor():
    user = current_user() or {}
    data = request.get_json(silent=True) or {}
    try:
        vendor = create_vendor(data)
        db.log_audit(
            "Vendor Created",
            user.get("username") or "",
            f"Created vendor '{vendor.get('vendor_name') or vendor.get('company_name') or vendor.get('email')}'.",
        )
        return jsonify({"success": True, "vendor": vendor})
    except VendorServiceError as exc:
        return jsonify({"error": str(exc)}), 400
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Could not create vendor."}), 500


@vendor_bp.route("/api/vendors/<int:vendor_id>", methods=["PUT"], endpoint="api_update_vendor")
@api_login_required
def api_update_vendor(vendor_id: int):
    user = current_user() or {}
    data = request.get_json(silent=True) or {}
    try:
        vendor = update_vendor(vendor_id, data)
        db.log_audit(
            "Vendor Updated",
            user.get("username") or "",
            f"Updated vendor '{vendor.get('vendor_name') or vendor.get('company_name') or vendor_id}'.",
        )
        return jsonify({"success": True, "vendor": vendor})
    except VendorServiceError as exc:
        return jsonify({"error": str(exc)}), 400
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Could not update vendor."}), 500


@vendor_bp.route("/api/vendors/<int:vendor_id>", methods=["DELETE"], endpoint="api_delete_vendor")
@api_login_required
def api_delete_vendor(vendor_id: int):
    user = current_user() or {}
    try:
        delete_vendor(vendor_id)
        db.log_audit("Vendor Deleted", user.get("username") or "", f"Soft deleted vendor id={vendor_id}.")
        return jsonify({"success": True})
    except VendorServiceError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception:
        return jsonify({"error": "Could not delete vendor."}), 500


@vendor_bp.route("/api/vendors/<int:vendor_id>/jds", methods=["GET"], endpoint="api_vendor_jds")
@api_login_required
def api_vendor_jds(vendor_id: int):
    try:
        return jsonify(vendor_jds(vendor_id))
    except VendorServiceError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception:
        return jsonify({"error": "Could not load vendor JD assignments."}), 500


@vendor_bp.route("/api/vendors/<int:vendor_id>/jds", methods=["POST"], endpoint="api_assign_vendor_jds")
@api_login_required
def api_assign_vendor_jds(vendor_id: int):
    user = current_user() or {}
    data = request.get_json(silent=True) or {}
    try:
        payload = assign_jds_to_vendor(vendor_id, data.get("jd_ids") or [], user)
        db.log_audit(
            "Vendor JDs Assigned",
            user.get("username") or "",
            f"Updated JD assignments for vendor id={vendor_id}.",
        )
        return jsonify({"success": True, **payload})
    except VendorServiceError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Could not assign JDs to vendor."}), 500


@vendor_bp.route("/api/jds/<int:jd_id>/vendors", methods=["GET"], endpoint="api_jd_vendors")
@api_login_required
def api_jd_vendors(jd_id: int):
    try:
        vendors = assigned_vendors(jd_id)
        try:
            fulfilment = recalculate_fulfilment(jd_id)
        except ValueError:
            fulfilment = None
        return jsonify({"vendors": vendors, "fulfilment": fulfilment})
    except VendorServiceError as exc:
        return jsonify({"error": str(exc)}), 404


@vendor_bp.route("/api/jds/<int:jd_id>/vendors", methods=["POST"], endpoint="api_assign_jd_vendors")
@api_login_required
def api_assign_jd_vendors(jd_id: int):
    user = current_user() or {}
    data = request.get_json(silent=True) or {}
    try:
        vendors = assign_vendors(jd_id, data.get("vendor_ids") or [], user)
        db.log_audit(
            "JD Vendors Assigned",
            user.get("username") or "",
            f"Updated vendor assignments for JD id={jd_id}.",
            jd_id,
        )
        return jsonify({"success": True, "vendors": vendors})
    except VendorServiceError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Could not assign vendors."}), 500


@vendor_bp.route("/api/jds/<int:jd_id>/vendors/<int:vendor_id>", methods=["DELETE"], endpoint="api_remove_jd_vendor")
@api_login_required
def api_remove_jd_vendor(jd_id: int, vendor_id: int):
    user = current_user() or {}
    try:
        remove_assignment(jd_id, vendor_id)
        db.log_audit(
            "JD Vendor Removed",
            user.get("username") or "",
            f"Removed vendor id={vendor_id} from JD id={jd_id}.",
            jd_id,
        )
        return jsonify({"success": True})
    except VendorServiceError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception:
        return jsonify({"error": "Could not remove vendor assignment."}), 500


@vendor_bp.route("/api/jds/<int:jd_id>/vendors/<int:vendor_id>/generate-email", methods=["POST"], endpoint="api_generate_vendor_email")
@api_login_required
def api_generate_vendor_email(jd_id: int, vendor_id: int):
    try:
        return jsonify(generate_vendor_email(jd_id, vendor_id, current_user() or {}))
    except VendorServiceError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Could not generate vendor email."}), 500


@vendor_bp.route("/api/jds/<int:jd_id>/vendors/<int:vendor_id>/send-email", methods=["POST"], endpoint="api_send_vendor_email")
@api_login_required
def api_send_vendor_email(jd_id: int, vendor_id: int):
    user = current_user() or {}
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        data = request.form.to_dict()
        data["manual_attachment_paths"] = _save_vendor_email_attachments()
    else:
        data = request.get_json(silent=True) or {}
    try:
        result = send_vendor_email(jd_id, vendor_id, data, user)
        db.log_audit(
            "Vendor JD Email Sent",
            user.get("username") or "",
            f"Sent JD id={jd_id} to vendor id={vendor_id}.",
            jd_id,
        )
        return jsonify(result)
    except VendorServiceError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception:
        return jsonify({"error": "Could not send vendor email."}), 500


@vendor_bp.route("/api/jds/<int:jd_id>/vendors/<int:vendor_id>/assign-send-email", methods=["POST"], endpoint="api_assign_send_vendor_email")
@api_login_required
def api_assign_send_vendor_email(jd_id: int, vendor_id: int):
    user = current_user() or {}
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        data = request.form.to_dict()
        data["manual_attachment_paths"] = _save_vendor_email_attachments()
    else:
        data = request.get_json(silent=True) or {}
    try:
        result = assign_and_send_vendor_email(jd_id, vendor_id, data, user)
        db.log_audit(
            "Vendor Assigned And JD Email Sent",
            user.get("username") or "",
            f"Assigned and sent JD id={jd_id} to vendor id={vendor_id}.",
            jd_id,
        )
        return jsonify(result)
    except VendorServiceError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception:
        return jsonify({"error": "Could not assign vendor because the email was not sent."}), 500


@vendor_bp.route("/api/jds/<int:jd_id>/vendors/<int:vendor_id>/email-history", methods=["GET"], endpoint="api_vendor_email_history")
@api_login_required
def api_vendor_email_history(jd_id: int, vendor_id: int):
    return jsonify({"history": email_history(jd_id, vendor_id), "candidates": candidate_history(jd_id, vendor_id)})


@vendor_bp.route("/api/jds/<int:jd_id>/vendor-candidates/<int:candidate_id>/accept", methods=["POST"], endpoint="api_accept_vendor_candidate")
@api_login_required
def api_accept_vendor_candidate(jd_id: int, candidate_id: int):
    user = current_user() or {}
    try:
        decision = PolicyEngine().check(ToolRequest("bench.selection.override", user=user, confirmed=True))
        if not decision.allowed:
            return jsonify({"error": decision.reason}), 403
        result = accept_vendor_candidate(jd_id, candidate_id)
        db.log_audit("Vendor Candidate Accepted", user.get("username") or "", f"Accepted vendor candidate id={candidate_id} for JD id={jd_id}.", jd_id)
        return jsonify({"success": True, "fulfilment": result})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Could not accept vendor candidate."}), 500
