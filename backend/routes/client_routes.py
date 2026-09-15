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
