from __future__ import annotations

from flask import Blueprint, jsonify, request

import database as db
from services.auth_service import api_login_required, current_user
from services.workflow_admin_service import (
    mark_bench_unavailable,
    override_bench_selection,
    readiness_payload,
    require_manager,
    run_backfill,
    update_jd_required_count,
    update_vendor_categories,
)

workflow_admin_bp = Blueprint("workflow_admin_routes", __name__)


@workflow_admin_bp.route("/api/admin/workflow-readiness", methods=["GET"], endpoint="api_workflow_readiness")
@api_login_required
def api_workflow_readiness():
    try:
        require_manager(current_user() or {})
        return jsonify(readiness_payload())
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403


@workflow_admin_bp.route("/api/admin/workflow-backfill", methods=["POST"], endpoint="api_workflow_backfill")
@api_login_required
def api_workflow_backfill():
    user = current_user() or {}
    data = request.get_json(silent=True) or {}
    try:
        require_manager(user)
        raw_default = data.get("default_required_candidate_count")
        default_count = int(raw_default) if raw_default not in {None, ""} else None
        result = run_backfill(default_count)
        db.log_audit("Workflow Defaults Backfilled", user.get("username") or "", f"Backfilled workflow defaults: {result}.")
        return jsonify({"success": True, "result": result, "readiness": readiness_payload()})
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@workflow_admin_bp.route("/api/admin/jds/<int:jd_id>/required-count", methods=["POST"], endpoint="api_admin_jd_required_count")
@api_login_required
def api_admin_jd_required_count(jd_id: int):
    user = current_user() or {}
    data = request.get_json(silent=True) or {}
    try:
        jd = update_jd_required_count(jd_id, int(data.get("required_candidate_count") or 0), user)
        return jsonify({"success": True, "jd": jd, "readiness": readiness_payload()})
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@workflow_admin_bp.route("/api/admin/vendors/<int:vendor_id>/categories", methods=["POST"], endpoint="api_admin_vendor_categories")
@api_login_required
def api_admin_vendor_categories(vendor_id: int):
    user = current_user() or {}
    data = request.get_json(silent=True) or {}
    try:
        vendor = update_vendor_categories(vendor_id, data.get("supported_categories") or [], data.get("supported_sub_tags") or [], user)
        return jsonify({"success": True, "vendor": vendor, "readiness": readiness_payload()})
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@workflow_admin_bp.route("/api/jds/<int:jd_id>/bench-candidates/<int:candidate_id>/selection", methods=["POST"], endpoint="api_override_bench_selection")
@api_login_required
def api_override_bench_selection(jd_id: int, candidate_id: int):
    user = current_user() or {}
    data = request.get_json(silent=True) or {}
    try:
        result = override_bench_selection(jd_id, candidate_id, data.get("selection_status") or "", user)
        return jsonify({"success": True, "fulfilment": result})
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@workflow_admin_bp.route("/api/jds/<int:jd_id>/bench-candidates/<int:candidate_id>/unavailable", methods=["POST"], endpoint="api_mark_bench_unavailable")
@api_login_required
def api_mark_bench_unavailable(jd_id: int, candidate_id: int):
    user = current_user() or {}
    try:
        result = mark_bench_unavailable(jd_id, candidate_id, user)
        return jsonify({"success": True, "fulfilment": result})
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@workflow_admin_bp.route("/api/jds/<int:jd_id>/fulfilment/timeline", methods=["GET"], endpoint="api_jd_fulfilment_timeline")
@api_login_required
def api_jd_fulfilment_timeline(jd_id: int):
    return jsonify({"events": db.get_jd_audit_events(jd_id, 50)})

