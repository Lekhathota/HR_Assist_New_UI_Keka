import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database as db


def _matches(doc, query):
    for key, cond in query.items():
        value = doc.get(key)
        if isinstance(cond, dict):
            if "$nin" in cond and value in cond["$nin"]:
                return False
            if "$exists" in cond and (key in doc) != cond["$exists"]:
                return False
        elif value != cond:
            return False
    return True


class Result:
    def __init__(self, n):
        self.matched_count = self.modified_count = n


class Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, query=None, projection=None):
        return [d for d in self.docs if _matches(d, query or {})]

    def find_one(self, query, projection=None):
        hits = self.find(query)
        return hits[0] if hits else None

    def count_documents(self, query):
        return len(self.find(query))

    def update_one(self, query, update):
        doc = self.find_one(query)
        if not doc:
            return Result(0)
        doc.update(update.get("$set", {}))
        for key in update.get("$unset", {}):
            doc.pop(key, None)
        return Result(1)


class FakeDb:
    def __init__(self, required=2, status="Active"):
        self.job_descriptions = Collection([{"id": 1, "title": "Senior AI Engineer", "status": status, "required_candidate_count": required}])
        self.comparisons = Collection()
        self.notifications = Collection()


def setup(monkeypatch, **kwargs):
    fake = FakeDb(**kwargs)
    monkeypatch.setattr(db, "_database", lambda: fake)
    monkeypatch.setattr(db, "refresh_dashboard_metrics", lambda: None)
    monkeypatch.setattr(db, "create_notification", lambda kind, title, message, **kw: fake.notifications.docs.append(
        {"type": kind, "title": title, "message": message, **kw}))
    return fake


def select(fake, candidate_id):
    fake.comparisons.docs.append({"jd_id": 1, "candidate_id": candidate_id, "status": "Selected"})


def status(fake):
    return fake.job_descriptions.docs[0]["status"]


def test_jd_becomes_filled_not_closed_when_requirement_met(monkeypatch):
    fake = setup(monkeypatch)
    select(fake, 10)
    assert db.sync_jd_fill_status(1) is None and status(fake) == "Active"
    select(fake, 11)
    assert db.sync_jd_fill_status(1) == "Filled"
    assert status(fake) == "Filled"
    assert [n["type"] for n in fake.notifications.docs] == ["jd_requirement_fulfilled"]


def test_drop_out_or_no_show_reopens_filled_jd(monkeypatch):
    fake = setup(monkeypatch)
    select(fake, 10)
    select(fake, 11)
    db.sync_jd_fill_status(1)

    assert db.set_candidate_placement(1, 11, "Not Joined", "Accepted another offer", "admin")
    assert status(fake) == "Active"
    assert fake.notifications.docs[-1]["type"] == "jd_reopened"
    assert db.jd_filled_count(1) == 1

    # A replacement is selected -> Filled again; a "Joined" mark keeps the post held.
    select(fake, 12)
    db.sync_jd_fill_status(1)
    assert status(fake) == "Filled"
    db.set_candidate_placement(1, 12, "Joined")
    assert status(fake) == "Filled"

    # Undoing the drop-out (empty status) counts the candidate again.
    db.set_candidate_placement(1, 10, "Dropped")
    assert status(fake) == "Active"
    db.set_candidate_placement(1, 10, "")
    assert status(fake) == "Filled"


def test_raising_post_count_reopens(monkeypatch):
    fake = setup(monkeypatch)
    select(fake, 10)
    select(fake, 11)
    db.sync_jd_fill_status(1)
    fake.job_descriptions.docs[0]["required_candidate_count"] = 3
    assert db.sync_jd_fill_status(1) == "Active"


def test_invalid_placement_rejected(monkeypatch):
    fake = setup(monkeypatch)
    select(fake, 10)
    try:
        db.set_candidate_placement(1, 10, "Fired")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
    assert not db.set_candidate_placement(1, 99, "Dropped")


def test_admin_close_is_final_until_reopened(monkeypatch):
    fake = setup(monkeypatch, required=1)
    assert db.close_jd(1, "admin", "Client cancelled the role")
    assert status(fake) == "Closed"
    assert fake.job_descriptions.docs[0]["closed_by"] == "admin"
    assert not db.close_jd(1, "admin")

    # Selections and drop-outs never touch a closed JD.
    select(fake, 10)
    db.sync_jd_fill_status(1)
    assert status(fake) == "Closed"

    # Reopening lands on Filled straight away because the one post is still held.
    assert db.reopen_jd(1, "admin") == "Filled"
    assert "closed_by" not in fake.job_descriptions.docs[0]
    assert db.reopen_jd(1, "admin") is None


def test_old_auto_closed_jds_migrate_to_filled(monkeypatch):
    fake = setup(monkeypatch, required=1, status="Closed")
    fake.job_descriptions.docs.append({"id": 2, "title": "Manual", "status": "Closed", "required_candidate_count": 1})
    fake.notifications.docs.append({"type": "jd_requirement_fulfilled", "jd_id": 1})
    select(fake, 10)
    monkeypatch.setattr(db, "_fill_status_migrated", False)
    assert db.migrate_auto_closed_jds() == 1
    assert status(fake) == "Filled"
    assert fake.job_descriptions.docs[1]["status"] == "Closed"
