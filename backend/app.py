# Backend file purpose: Backend entrypoint or shared infrastructure for app.
"""
Recruitment Assist — Flask application bootstrap and blueprint registration.
"""

from __future__ import annotations

import atexit
import os
import shutil
import socket
import subprocess
import sys
import traceback
from secrets import token_hex

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, request, send_from_directory, session, url_for
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database as db
from routes.audit_routes import audit_bp
from routes.agentic_routes import agentic_bp
from routes.assessment_routes import assessment_bp
from routes.auth_routes import auth_bp
from routes.candidate_routes import candidate_bp
from routes.client_routes import client_bp
from routes.dashboard_routes import dashboard_bp
from routes.interview_routes import interview_bp
from routes.jd_routes import jd_bp
from routes.matching_routes import matching_bp
from routes.profile_routes import profile_bp
from routes.report_routes import report_bp
from database import init_db, seed_data
from routes.vendor_routes import vendor_bp
from routes.workflow_admin_routes import workflow_admin_bp


BUILD_DIR = os.path.join(BASE_DIR, "build")

app = Flask(__name__, template_folder="templates", static_folder="static", static_url_path="/static")
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
app.secret_key = (os.environ.get("SECRET_KEY") or "").strip() or token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
)

_cors_raw = (
    os.environ.get("CORS_ORIGINS")
    or "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
)
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": _cors_origins}}, supports_credentials=True)

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(jd_bp)
app.register_blueprint(interview_bp)
app.register_blueprint(candidate_bp)
app.register_blueprint(client_bp)
app.register_blueprint(matching_bp)
app.register_blueprint(report_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(audit_bp)
app.register_blueprint(agentic_bp)
app.register_blueprint(assessment_bp)
app.register_blueprint(vendor_bp)
app.register_blueprint(workflow_admin_bp)


# Purpose: Implements the alias endpoint backend behavior.
def _alias_endpoint(old_endpoint: str, new_endpoint: str) -> None:
    if new_endpoint not in app.view_functions:
        return
    for rule in list(app.url_map.iter_rules(new_endpoint)):
        methods = sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"})
        app.add_url_rule(
            rule.rule,
            endpoint=old_endpoint,
            view_func=app.view_functions[new_endpoint],
            defaults=rule.defaults,
            methods=methods,
        )
        break


# Purpose: Checks whether port open is true.
def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


# Purpose: Implements the start frontend dev server backend behavior.
# NOTE: This is a LOCAL DEV convenience only. It is gated behind RA_AUTO_START_FRONTEND
# and never runs on Databricks Apps (single-process deployment), since that env var
# should never be set to true in production.
def _start_frontend_dev_server() -> subprocess.Popen | None:
    auto_start = (os.environ.get("RA_AUTO_START_FRONTEND") or "false").strip().lower()
    if auto_start not in {"1", "true", "yes", "on"}:
        return None

    frontend_port = int(os.environ.get("FRONTEND_PORT", "3001"))
    if _is_port_open("127.0.0.1", frontend_port):
        app.logger.info("Frontend already running on port %s; skipping auto-start.", frontend_port)
        return None

    frontend_dir = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
    if not os.path.isdir(frontend_dir):
        app.logger.warning("Frontend directory not found at %s; skipping auto-start.", frontend_dir)
        return None

    env = os.environ.copy()
    env["PORT"] = str(frontend_port)
    env["BROWSER"] = "none"
    npm_exe = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm_exe:
        app.logger.warning("npm is not available on PATH; cannot auto-start frontend.")
        return None

    cmd = [npm_exe, "start"]
    app.logger.info("Starting frontend dev server on port %s...", frontend_port)

    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(cmd, cwd=frontend_dir, env=env, creationflags=creationflags)  # noqa: S603
    return proc


# Backward compatibility for url_for() references from templates and route logic.
_alias_endpoint("index", "auth_routes.index")
_alias_endpoint("login", "auth_routes.login")
_alias_endpoint("logout", "auth_routes.logout")
_alias_endpoint("dashboard", "dashboard_routes.dashboard")
_alias_endpoint("jd_list", "jd_routes.jd_list")
_alias_endpoint("jd_create", "jd_routes.jd_create")
_alias_endpoint("jd_details", "jd_routes.jd_details")
_alias_endpoint("jd_delete", "jd_routes.jd_delete")
_alias_endpoint("candidates", "candidate_routes.candidates")
_alias_endpoint("candidate_profile", "candidate_routes.candidate_profile")
_alias_endpoint("candidate_delete", "candidate_routes.candidate_delete")
_alias_endpoint("compare", "matching_routes.compare")
_alias_endpoint("reports", "report_routes.reports")
_alias_endpoint("profile", "profile_routes.profile")
_alias_endpoint("api_login", "auth_routes.api_login")
_alias_endpoint("api_logout", "auth_routes.api_logout")
_alias_endpoint("api_dashboard", "dashboard_routes.api_dashboard")
_alias_endpoint("api_jd_performance", "dashboard_routes.api_jd_performance")
_alias_endpoint("api_jd_list", "jd_routes.api_jd_list")
_alias_endpoint("api_jd_details", "jd_routes.api_jd_details")
_alias_endpoint("api_create_jd", "jd_routes.api_create_jd")
_alias_endpoint("api_jd_delete", "jd_routes.api_jd_delete")
_alias_endpoint("api_interview_defaults", "interview_routes.api_interview_defaults")
_alias_endpoint("api_interview_blocked_slots", "interview_routes.api_interview_blocked_slots")
_alias_endpoint("api_generate_interview_email", "interview_routes.api_generate_interview_email")
_alias_endpoint("api_schedule_interview", "interview_routes.api_schedule_interview")
_alias_endpoint("api_reschedule_interview", "interview_routes.api_reschedule_interview")
_alias_endpoint("api_interview_outcome", "interview_routes.api_interview_outcome")
_alias_endpoint("api_interview_outcome_fallback", "interview_routes.api_interview_outcome_fallback")
_alias_endpoint("api_generate_cancellation", "interview_routes.api_generate_cancellation")
_alias_endpoint("api_send_cancellation", "interview_routes.api_send_cancellation")
_alias_endpoint("api_candidates", "candidate_routes.api_candidates")
_alias_endpoint("api_candidate_profile", "candidate_routes.api_candidate_profile")
_alias_endpoint("api_candidate_delete", "candidate_routes.api_candidate_delete")
_alias_endpoint("api_clients", "client_routes.api_clients")
_alias_endpoint("api_client_details", "client_routes.api_client_details")
_alias_endpoint("api_create_client", "client_routes.api_create_client")
_alias_endpoint("uploaded_file", "candidate_routes.uploaded_file")
_alias_endpoint("api_compare", "matching_routes.api_compare")
_alias_endpoint("api_reports", "report_routes.api_reports")
_alias_endpoint("api_profile", "profile_routes.api_profile")


# Purpose: Coordinates the teardown routine for this module.
@app.teardown_appcontext
def _teardown(_exc):
    pass


# Purpose: Coordinates the ensure db routine for this module.
@app.before_request
def _ensure_db():
    path = (request.path or "").rstrip("/") or ""
    login_or_static = request.endpoint in ("login", "static") or path.startswith("/static") or path == "/login"
    try:
        db.init_pool()
    except Exception:
        if request.path.startswith("/api/"):
            return jsonify({"error": "Database not configured"}), 503
        if login_or_static:
            return None
        flash("MongoDB is not configured. Set MONGODB_URI and restart.", "danger")
        session.clear()
        return redirect(url_for("login"))
    return None


@app.get("/favicon.ico")
def favicon():
    return ("", 204)


# Purpose: Serve the built React frontend directly from Flask.
# This replaces the old localhost:3001 redirect, which only works when a
# separate `npm start` dev server is running alongside Flask. Databricks
# Apps runs a single process, so the compiled React build (backend/build/,
# produced via `npm run build`) must be served by Flask itself.
@app.get("/")
@app.get("/<path:path>")
def serve_react(path: str = ""):
    if path.startswith("api/") or path.startswith("static/"):
        # Let API/static routes 404 normally instead of falling through to React.
        return jsonify({"error": "Not found"}), 404

    if not os.path.isdir(BUILD_DIR):
        return (
            "React build not found. Run `npm run build` in frontend/ and "
            "copy the output into backend/build/.",
            500,
        )

    full_path = os.path.join(BUILD_DIR, path)
    if path and os.path.isfile(full_path):
        return send_from_directory(BUILD_DIR, path)

    return send_from_directory(BUILD_DIR, "index.html")


if __name__ == "__main__":
    # Databricks Apps injects DATABRICKS_APP_PORT and expects the app to bind
    # to 0.0.0.0 so its internal proxy can route traffic in. FLASK_HOST/PORT
    # are kept as overrides for local development.
    host = (os.environ.get("FLASK_HOST") or "0.0.0.0").strip()
    port = int(os.environ.get("DATABRICKS_APP_PORT") or os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "").lower() == "true"
    try:
        init_db()
        seed_data()
    except Exception as exc:
        print(f"Warning: MongoDB startup initialization failed: {exc}", file=sys.stderr)
        if debug:
            traceback.print_exc()

    frontend_proc: subprocess.Popen | None = None
    should_bootstrap_frontend = (not debug) or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if should_bootstrap_frontend:
        frontend_proc = _start_frontend_dev_server()

        if frontend_proc is not None:
            # Purpose: Cleans and normalizes up frontend values.
            def _cleanup_frontend() -> None:
                if frontend_proc.poll() is None:
                    frontend_proc.terminate()

            atexit.register(_cleanup_frontend)

    app.run(debug=debug, host=host, port=port)