import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fulfilment_service import calculate_remaining_requirement
from services.fulfilment_service import apply_bench_selection
from services.fulfilment_service import _assign_shortage
from services.fulfilment_service import run_automated_bench_workflow


@pytest.mark.parametrize(
    ("total", "selected", "accepted", "expected"),
    [
        (5, 3, 0, 2),
        (5, 5, 0, 0),
        (5, 7, 0, 0),
        (5, 0, 0, 5),
        (5, 3, 1, 1),
        (5, 3, 2, 0),
    ],
)
def test_remaining_requirement(total, selected, accepted, expected):
    assert calculate_remaining_requirement(total, selected, accepted) == expected


@pytest.mark.parametrize("value", [0, -1, None])
def test_required_count_must_be_positive(value):
    with pytest.raises(ValueError):
        calculate_remaining_requirement(value, 0, 0)


def test_selection_marks_top_qualified_candidates(monkeypatch):
    class FakeDb:
        def __init__(self):
            self.metadata = []
        def get_jd_by_id(self, *_args, **_kwargs):
            return {"id": 8, "required_candidate_count": 1, "bench_matched_count": 2}
        def update_comparison_metadata(self, jd_id, candidate_id, data):
            self.metadata.append((candidate_id, data)); return True
        def count_selected_bench_candidates(self, *_args): return 1
        def count_accepted_vendor_candidates(self, *_args): return 0
        def update_jd(self, *_args, **_kwargs): return True
    fake = FakeDb()
    monkeypatch.setattr("services.fulfilment_service.db", fake)
    result = apply_bench_selection(8, [{"id": 1, "match_score": 90}, {"id": 2, "match_score": 80}])
    assert [row["id"] for row in result["selected"]] == [1]
    assert [row["id"] for row in result["waitlisted"]] == [2]


def test_shortage_assignment_spreads_across_eligible_vendors(monkeypatch):
    class FakeDb:
        def __init__(self):
            self.assigned_vendor_ids = []
            self.allocation = {}
        def get_jd_by_id(self, *_args, **_kwargs):
            return {"id": 8, "required_candidate_count": 5, "job_category": "Backend"}
        def get_eligible_vendors_for_category(self, category):
            assert category == "Backend"
            return [{"id": 10}, {"id": 11}]
        def get_jd_vendor_assignments(self, *_args, **_kwargs):
            return [{"id": 99}]
        def assign_vendors_to_jd(self, jd_id, vendor_ids, allocation=None):
            self.assigned_vendor_ids = vendor_ids
            self.allocation = allocation or {}
            return [{"id": vendor_id, **self.allocation.get(vendor_id, {})} for vendor_id in vendor_ids]
        def update_jd(self, *_args, **_kwargs):
            return True
    fake = FakeDb()
    monkeypatch.setattr("services.fulfilment_service.db", fake)
    result = _assign_shortage(8, {"total_required": 5, "selected_bench_count": 2, "remaining_vendor_requirement": 3}, "manager")
    assert fake.assigned_vendor_ids == [99, 10, 11]
    assert fake.allocation[10]["allocated_count"] == 2
    assert fake.allocation[11]["allocated_count"] == 1
    assert len(result) == 3


def test_full_bench_fulfilment_skips_vendor_assignment(monkeypatch):
    class FakeDb:
        def __init__(self):
            self.assign_called = False
        def get_jd_by_id(self, *_args, **_kwargs):
            return {"id": 8, "required_candidate_count": 1, "job_category": "Backend", "bench_matched_count": 1}
        def update_jd(self, *_args, **_kwargs):
            return True
        def get_available_bench_candidates_for_category(self, *_args, **_kwargs):
            return [{"id": 1}]
        def update_comparison_metadata(self, *_args, **_kwargs):
            return True
        def count_selected_bench_candidates(self, *_args):
            return 1
        def count_accepted_vendor_candidates(self, *_args):
            return 0
        def assign_vendors_to_jd(self, *_args, **_kwargs):
            self.assign_called = True
            return []
        def log_audit(self, *_args, **_kwargs):
            return None
    fake = FakeDb()
    monkeypatch.setattr("services.fulfilment_service.db", fake)
    result = run_automated_bench_workflow(
        8,
        username="manager",
        runner=lambda *_args, **_kwargs: {"run_id": "r1", "ranked_candidates": [{"id": 1, "match_score": 90}]},
    )
    assert result["fulfilment_summary"]["remaining_vendor_requirement"] == 0
    assert result["vendor_assignments"] == []
    assert fake.assign_called is False


def test_no_bench_and_no_eligible_vendor_preserves_shortage(monkeypatch):
    class FakeDb:
        def get_jd_by_id(self, *_args, **_kwargs):
            return {"id": 8, "required_candidate_count": 2, "job_category": "Backend", "bench_matched_count": 0}
        def update_jd(self, *_args, **_kwargs):
            return True
        def get_available_bench_candidates_for_category(self, *_args, **_kwargs):
            return []
        def update_comparison_metadata(self, *_args, **_kwargs):
            return True
        def count_selected_bench_candidates(self, *_args):
            return 0
        def count_accepted_vendor_candidates(self, *_args):
            return 0
        def get_eligible_vendors_for_category(self, *_args):
            return []
        def log_audit(self, *_args, **_kwargs):
            return None
    monkeypatch.setattr("services.fulfilment_service.db", FakeDb())
    result = run_automated_bench_workflow(8, username="manager", runner=lambda *_args, **_kwargs: {})
    assert result["fulfilment_summary"]["remaining_vendor_requirement"] == 2
    assert result["vendor_assignments"] == []
