# Backend file purpose: Flask route handlers for lightweight client account features.
from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request

import database as db
from services.auth_service import api_login_required

client_bp = Blueprint("client_routes", __name__)


@client_bp.route("/api/clients", endpoint="api_clients")
@api_login_required
def api_clients():
    filters: dict[str, Any] = {}
    status = request.args.get("status")
    search = request.args.get("search")
    if status:
        filters["status"] = status
    if search:
        filters["search"] = search
    db.ensure_default_client_and_backfill()
    return jsonify({"clients": db.get_all_clients(filters if filters else None)})


@client_bp.route("/api/clients/<int:client_id>", endpoint="api_client_details")
@api_login_required
def api_client_details(client_id: int):
    db.ensure_default_client_and_backfill()
    payload = db.get_client_details(client_id)
    if not payload:
        return jsonify({"error": "Client not found"}), 404
    return jsonify(payload)


@client_bp.route("/api/clients", methods=["POST"], endpoint="api_create_client")
@api_login_required
def api_create_client():
    data = request.get_json(silent=True) or {}
    try:
        client_id = db.create_client(data)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({"success": True, "client": db.get_client_by_id(client_id)})


def _client_config_request_data() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    return data


@client_bp.route(
    "/api/clients/<int:client_id>/pipelines",
    methods=["POST"],
    endpoint="api_create_client_pipeline",
)
@api_login_required
def api_create_client_pipeline(client_id: int):
    try:
        data = _client_config_request_data()
        client = db.add_client_pipeline(client_id, data)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    if not client:
        return jsonify({"success": False, "error": "Client not found"}), 404
    return jsonify({"success": True, "client": client})


@client_bp.route(
    "/api/clients/<int:client_id>/pipelines/<pipeline_id>",
    methods=["PUT"],
    endpoint="api_update_client_pipeline",
)
@api_login_required
def api_update_client_pipeline(client_id: int, pipeline_id: str):
    try:
        data = _client_config_request_data()
        client = db.update_client_pipeline(client_id, pipeline_id, data)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    if not client:
        return jsonify({"success": False, "error": "Client or hiring pipeline not found"}), 404
    return jsonify({"success": True, "client": client})


@client_bp.route(
    "/api/clients/<int:client_id>/roles",
    methods=["POST"],
    endpoint="api_create_client_role",
)
@api_login_required
def api_create_client_role(client_id: int):
    try:
        data = _client_config_request_data()
        client = db.add_client_role(client_id, data)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    if not client:
        return jsonify({"success": False, "error": "Client not found"}), 404
    return jsonify({"success": True, "client": client})


@client_bp.route(
    "/api/clients/<int:client_id>/roles/<role_id>",
    methods=["PUT"],
    endpoint="api_update_client_role",
)
@api_login_required
def api_update_client_role(client_id: int, role_id: str):
    try:
        data = _client_config_request_data()
        client = db.update_client_role(client_id, role_id, data)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    if not client:
        return jsonify({"success": False, "error": "Client or role not found"}), 404
    return jsonify({"success": True, "client": client})
