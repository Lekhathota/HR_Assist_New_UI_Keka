from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import workflow_admin_service


def test_readiness_payload_identifies_legacy_gaps(monkeypatch):
    class FakeDb:
        def get_all_jds(self, *_args, **_kwargs):
            return [
                {"id": 1, "title": "Ready", "required_candidate_count": 2, "job_category": "Backend"},
                {"id": 2, "title": "Missing Count", "required_candidate_count": None, "job_category": "QA"},
                {"id": 3, "title": "Needs Category", "required_candidate_count": 1, "job_category": "Others"},
            ]
        def get_all_vendors(self, *_args, **_kwargs):
            return [
                {"id": 4, "vendor_name": "Configured", "supported_categories": ["Backend"]},
                {"id": 5, "vendor_name": "Gap", "supported_categories": []},
            ]
    monkeypatch.setattr(workflow_admin_service, "db", FakeDb())
    payload = workflow_admin_service.readiness_payload()
    assert payload["summary"]["active_jds"] == 3
    assert payload["summary"]["missing_required_counts"] == 1
    assert payload["summary"]["category_review_required"] == 1
    assert payload["summary"]["vendors_without_categories"] == 1
    assert payload["summary"]["workflow_ready_jds"] == 1


def test_recruiter_cannot_update_workflow_admin_fields():
    with pytest.raises(PermissionError):
        workflow_admin_service.require_manager({"role": "Recruiter"})


def test_override_bench_selection_recalculates(monkeypatch):
    calls = {}
    class FakeDb:
        def update_comparison_metadata(self, jd_id, candidate_id, data):
            calls["metadata"] = (jd_id, candidate_id, data)
            return True
        def log_audit(self, *_args, **_kwargs):
            calls["audit"] = True
    monkeypatch.setattr(workflow_admin_service, "db", FakeDb())
    monkeypatch.setattr(workflow_admin_service, "recalculate_fulfilment", lambda jd_id: {"remaining_vendor_requirement": 0, "jd_id": jd_id})
    result = workflow_admin_service.override_bench_selection(8, 9, "selected_bench", {"role": "manager", "username": "m"})
    assert calls["metadata"][2]["selection_status"] == "selected_bench"
    assert calls["metadata"][2]["qualification_status"] == "qualified"
    assert result["remaining_vendor_requirement"] == 0


def test_mark_bench_unavailable_reopens_shortage(monkeypatch):
    calls = {}
    class FakeDb:
        def update_candidate(self, candidate_id, data):
            calls["candidate"] = (candidate_id, data)
            return True
        def update_comparison_metadata(self, jd_id, candidate_id, data):
            calls["metadata"] = data
            return True
        def log_audit(self, *_args, **_kwargs):
            calls["audit"] = True
    monkeypatch.setattr(workflow_admin_service, "db", FakeDb())
    monkeypatch.setattr(workflow_admin_service, "recalculate_fulfilment", lambda jd_id: {"remaining_vendor_requirement": 1})
    result = workflow_admin_service.mark_bench_unavailable(8, 9, {"role": "admin", "username": "a"})
    assert calls["candidate"][1]["availability_status"] == "Unavailable"
    assert calls["metadata"]["selection_status"] == "rejected"
    assert result["remaining_vendor_requirement"] == 1

