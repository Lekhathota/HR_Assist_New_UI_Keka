# Backend file purpose: Flask route handlers for dashboard features.
from __future__ import annotations

from flask import Blueprint, jsonify

from spa_urls import redirect_to_spa

from services.auth_service import api_login_required, login_required
from services.report_service import dashboard_payload, jd_performance_payload

dashboard_bp = Blueprint("dashboard_routes", __name__)


# Purpose: Implements the dashboard backend behavior.
@dashboard_bp.route("/dashboard", endpoint="dashboard")
@login_required
def dashboard():
    return redirect_to_spa("/dashboard")


# Purpose: API endpoint handler for dashboard.
@dashboard_bp.route("/api/dashboard", endpoint="api_dashboard")
@api_login_required
def api_dashboard():
    return jsonify(dashboard_payload())


# Purpose: API endpoint handler for jd performance.
@dashboard_bp.route("/api/metrics/jd-performance", endpoint="api_jd_performance")
@api_login_required
def api_jd_performance():
    return jsonify(jd_performance_payload())


# Purpose: API endpoint handler for dashboard team.
@dashboard_bp.route("/api/dashboard/team", endpoint="api_dashboard_team")
@api_login_required
def api_dashboard_team():
    """Team recruiting metrics (static placeholder until team/reporting data is modeled in DB)."""
    return jsonify([])
