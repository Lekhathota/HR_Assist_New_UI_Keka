import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database as db


class Cursor(list):
    def sort(self, key, direction):
        return Cursor(sorted(self, key=lambda d: d[key]))


class Recruiters:
    def __init__(self):
        self.docs = []

    def count_documents(self, query):
        return len(self.docs)

    def insert_one(self, doc):
        self.docs.append(doc)

    def find(self, query, projection=None):
        return Cursor(self.docs)

    def find_one(self, query, projection=None):
        cond = query["name"]
        pattern = re.compile(cond["$regex"], re.IGNORECASE if "i" in cond.get("$options", "") else 0)
        return next((d for d in self.docs if pattern.match(d["name"])), None)


class FakeDb:
    def __init__(self):
        self.recruiters = Recruiters()


def setup(monkeypatch):
    fake = FakeDb()
    ids = iter(range(1, 100))
    monkeypatch.setattr(db, "_database", lambda: fake)
    monkeypatch.setattr(db, "_next_id", lambda name: next(ids))
    return fake


def test_defaults_are_seeded_once(monkeypatch):
    fake = setup(monkeypatch)
    assert db.list_recruiters() == ["Prajwal P", "Rajeswari L", "Mamatha M", "Soumen S", "Afritha P"]
    assert db.list_recruiters() == db.DEFAULT_RECRUITERS
    assert len(fake.recruiters.docs) == 5


def test_add_new_recruiter_and_ignore_duplicates(monkeypatch):
    setup(monkeypatch)
    assert db.add_recruiter("  Kiran   R ", "admin") == ("Kiran R", True)
    assert db.list_recruiters()[-1] == "Kiran R"
    assert db.add_recruiter("kiran r") == ("Kiran R", False)
    assert db.add_recruiter("PRAJWAL p") == ("Prajwal P", False)
    assert db.list_recruiters().count("Kiran R") == 1


def test_invalid_names_rejected(monkeypatch):
    setup(monkeypatch)
    for bad in ["", "   ", "x" * 81]:
        try:
            db.add_recruiter(bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")
