import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database as db


class FakeJobDescriptions:
    def __init__(self, doc):
        self.doc = doc
        self.updates = []

    def find_one(self, query, projection=None):
        if self.doc.get("id") == query.get("id"):
            return dict(self.doc)
        return None

    def update_one(self, query, update):
        matches = all(self.doc.get(key) == value for key, value in query.items())
        if matches:
            self.updates.append((query, update))
            self.doc.update(update.get("$set", {}))
        return type("Result", (), {"modified_count": 1 if matches else 0})()


class FakeComparisons:
    def __init__(self, selected_count):
        self.selected_count = selected_count

    def count_documents(self, query):
        assert query.get("status") == "Selected"
        return self.selected_count


class FakeNotifications:
    def __init__(self):
        self.docs = []

    def insert_one(self, doc):
        self.docs.append(doc)


class FakeCounters:
    def __init__(self):
        self.seq = 0

    def find_one_and_update(self, *args, **kwargs):
        self.seq += 1
        return {"seq": self.seq}


class FakeDb:
    def __init__(self, jd_doc, selected_count):
        self.job_descriptions = FakeJobDescriptions(jd_doc)
        self.comparisons = FakeComparisons(selected_count)
        self.notifications = FakeNotifications()
        self.counters = FakeCounters()


def test_closes_when_selected_meets_requirement(monkeypatch):
    fake = FakeDb({"id": 1, "status": "Active", "required_candidate_count": 2, "title": "Data Engineer"}, selected_count=2)
    monkeypatch.setattr(db, "_database", lambda: fake)
    db._close_jd_if_fulfilled(1)
    assert fake.job_descriptions.doc["status"] == "Closed"
    assert fake.job_descriptions.updates
    [note] = fake.notifications.docs
    assert note["type"] == "jd_requirement_fulfilled"
    assert note["jd_id"] == 1
    assert "Data Engineer" in note["message"] and "closed" in note["message"]
    assert note["read_by"] == []


def test_notifies_only_once_when_already_closed_by_another_request(monkeypatch):
    fake = FakeDb({"id": 1, "status": "Active", "required_candidate_count": 1, "title": "QA"}, selected_count=1)
    monkeypatch.setattr(db, "_database", lambda: fake)
    db._close_jd_if_fulfilled(1)
    db._close_jd_if_fulfilled(1)
    assert len(fake.notifications.docs) == 1


def test_stays_open_when_below_requirement(monkeypatch):
    fake = FakeDb({"id": 1, "status": "Active", "required_candidate_count": 3}, selected_count=2)
    monkeypatch.setattr(db, "_database", lambda: fake)
    db._close_jd_if_fulfilled(1)
    assert fake.job_descriptions.doc["status"] == "Active"
    assert not fake.job_descriptions.updates
    assert not fake.notifications.docs


def test_noop_when_no_required_count(monkeypatch):
    fake = FakeDb({"id": 1, "status": "Active", "required_candidate_count": None}, selected_count=5)
    monkeypatch.setattr(db, "_database", lambda: fake)
    db._close_jd_if_fulfilled(1)
    assert fake.job_descriptions.doc["status"] == "Active"
    assert not fake.job_descriptions.updates
    assert not fake.notifications.docs


def test_noop_when_already_closed(monkeypatch):
    fake = FakeDb({"id": 1, "status": "Closed", "required_candidate_count": 1}, selected_count=5)
    monkeypatch.setattr(db, "_database", lambda: fake)
    db._close_jd_if_fulfilled(1)
    assert not fake.job_descriptions.updates
    assert not fake.notifications.docs
