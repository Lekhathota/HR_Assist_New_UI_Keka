import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database as db


def test_bench_availability_label_reflects_real_counts():
    assert db._bench_availability_label(3, 3) == "All available"
    assert db._bench_availability_label(2, 3) == "2 of 3 available"
    assert db._bench_availability_label(0, 2) == "None available"
    assert db._bench_availability_label(0, 0) == "No one on bench"


def test_role_priority_is_derived_from_the_shortfall():
    assert db._role_priority(required_count=3, gap=2, configured="Low") == "High"
    assert db._role_priority(required_count=1, gap=1, configured=None) == "Medium"
    assert db._role_priority(required_count=2, gap=0, configured=None) == "Low"
    assert db._role_priority(required_count=1, gap=1, configured="High") == "High"


class _Cursor(list):
    def sort(self, *args, **kwargs):
        return self


class _Candidates:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query):
        return _Cursor(dict(r) for r in self.rows)


class _Db:
    def __init__(self, rows):
        self.candidates = _Candidates(rows)


def test_bench_cards_count_actual_availability(monkeypatch):
    rows = [
        {"id": 1, "applied_roles": ["Data Engineer"], "availability_status": "Available", "match_score": 80},
        {"id": 2, "applied_roles": ["Data Engineer"], "availability_status": "Unavailable", "match_score": 60},
        {"id": 3, "applied_roles": ["Data Engineer"], "availability_status": "", "match_score": 70},
    ]
    monkeypatch.setattr(db, "_database", lambda: _Db(rows))
    monkeypatch.setattr(db, "_candidate_skill_names", lambda c: [])
    [card] = db._bench_cards(1)
    assert card["count"] == 3 and card["available_count"] == 2
    assert card["availability"] == "2 of 3 available"
    assert card["avg_match"] == 70
