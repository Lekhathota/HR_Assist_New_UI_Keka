import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask

import database as db
import routes.jd_routes as jd_routes
import services.auth_service as auth_service


def test_edit_jd_saves_and_returns_recruiter(monkeypatch):
    store = {1: {"id": 1, "title": "Data Engineer", "status": "Active", "recruiter": ""}}

    def update_jd(jd_id, patch):
        store[jd_id].update(patch)
        return True

    monkeypatch.setattr(auth_service, "effective_user_id", lambda: 1)
    monkeypatch.setattr(jd_routes, "current_user", lambda: {"username": "admin", "role": "admin"})
    monkeypatch.setattr(db, "get_jd_by_id", lambda jd_id, include_raw_text=False: dict(store[jd_id]))
    monkeypatch.setattr(db, "update_jd", update_jd)
    monkeypatch.setattr(db, "log_audit", lambda *a, **k: None)
    monkeypatch.setattr(jd_routes, "jd_details_payload", lambda jd_id: {"jd": dict(store[jd_id])})

    app = Flask(__name__)
    app.register_blueprint(jd_routes.jd_bp)
    response = app.test_client().put("/api/jds/1", json={"title": "Data Engineer", "recruiter": "Mamatha M"})

    assert response.status_code == 200
    assert store[1]["recruiter"] == "Mamatha M"
    assert response.get_json()["jd"]["recruiter"] == "Mamatha M"
