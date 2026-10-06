import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database as db
from routes.search_routes import allowed_sections


def _match(doc, query):
    if "$and" in query:
        return all(_match(doc, q) for q in query["$and"])
    if "$or" in query:
        return any(_match(doc, q) for q in query["$or"])
    for key, cond in query.items():
        value = doc.get(key)
        if isinstance(cond, dict) and "$regex" in cond:
            if not re.search(cond["$regex"], str(value or ""), re.I):
                return False
        elif isinstance(cond, dict) and "$in" in cond:
            if value not in cond["$in"]:
                return False
        elif value != cond:
            return False
    return True


class Cursor(list):
    def sort(self, key, direction):
        return Cursor(sorted(self, key=lambda d: str(d.get(key) or ""), reverse=True))

    def limit(self, n):
        return Cursor(self[:n])


class Collection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query, projection=None):
        return Cursor(dict(d) for d in self.docs if _match(d, query))


class FakeDb(dict):
    def __getattr__(self, name):
        return self[name]


def fake_db():
    return FakeDb(
        job_descriptions=Collection([
            {"id": 1, "title": "Senior Data Engineer", "client_name": "ABC Corp", "status": "Active", "updated_at": "2"},
            {"id": 2, "title": "QA Lead", "client_name": "Data Systems Ltd", "status": "Closed", "updated_at": "1"},
            {"id": 3, "title": "C++ Developer", "status": "Active", "updated_at": "3"},
        ]),
        candidates=Collection([
            {"id": 10, "name": "Priya Sharma", "email": "priya@x.io", "jd_id": 1, "uploaded_at": "1"},
            {"id": 11, "name": "Rahul Verma", "email": "rahul@x.io", "primary_category": "Data", "uploaded_at": "2"},
        ]),
        clients=Collection([{"id": 5, "name": "ABC Corp", "client_account_id": "ABC"}]),
        vendors=Collection([
            {"id": 7, "company_name": "TalentBridge", "contact_person": "Asha", "deleted_at": None},
            {"id": 8, "company_name": "Talent Old", "deleted_at": "2026-01-01"},
        ]),
    )


def test_finds_jobs_and_candidates_by_name_and_key_fields(monkeypatch):
    monkeypatch.setattr(db, "_database", fake_db)
    result = db.global_search("data", {"jobs", "candidates", "clients", "vendors"})
    assert [j["title"] for j in result["jobs"]] == ["Senior Data Engineer", "QA Lead"]   # title or client name
    assert [c["name"] for c in result["candidates"]] == ["Rahul Verma"]                  # role category
    priya = db.global_search("priya", {"candidates"})["candidates"][0]
    assert priya["jd_title"] == "Senior Data Engineer"


def test_special_characters_are_literal_and_deleted_vendors_hidden(monkeypatch):
    monkeypatch.setattr(db, "_database", fake_db)
    assert [j["title"] for j in db.global_search("c++", {"jobs"})["jobs"]] == ["C++ Developer"]
    assert [v["company_name"] for v in db.global_search("talent", {"vendors"})["vendors"]] == ["TalentBridge"]


def test_short_queries_and_disallowed_sections_return_nothing(monkeypatch):
    monkeypatch.setattr(db, "_database", fake_db)
    assert db.global_search("d", {"jobs", "candidates"}) == {"jobs": [], "candidates": [], "clients": [], "vendors": []}
    assert db.global_search("abc", {"clients"})["jobs"] == []


def test_sections_follow_page_access_rules():
    assert allowed_sections("admin") == {"jobs", "candidates", "clients", "vendors"}
    assert allowed_sections("recruiter") == {"jobs", "candidates"}
    assert allowed_sections("Managers/Consultant") == {"clients", "vendors"}
    assert allowed_sections("finance") == set()
