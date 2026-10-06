import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database as db


class FakeCursor(list):
    def sort(self, key, direction):
        return FakeCursor(sorted(self, key=lambda d: d[key], reverse=direction == db.DESCENDING))

    def limit(self, n):
        return FakeCursor(self[:n])


def _matches(doc, query):
    for key, cond in query.items():
        value = doc.get(key)
        if isinstance(cond, dict):
            if "$ne" in cond and (cond["$ne"] in value if isinstance(value, list) else value == cond["$ne"]):
                return False
            if "$in" in cond and value not in cond["$in"]:
                return False
        elif value != cond:
            return False
    return True


class FakeNotifications:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query):
        return FakeCursor(d for d in self.docs if _matches(d, query))

    def count_documents(self, query):
        return len(self.find(query))

    def update_many(self, query, update):
        hits = [d for d in self.docs if _matches(d, query)]
        for doc in hits:
            for key, value in update["$addToSet"].items():
                doc.setdefault(key, [])
                if value not in doc[key]:
                    doc[key].append(value)
        return type("Result", (), {"modified_count": len(hits)})()


class FakeDb:
    def __init__(self, docs):
        self.notifications = FakeNotifications(docs)


def _docs():
    return [
        {"_id": "a", "id": 1, "title": "Older", "message": "m1", "read_by": [7], "created_at": 1},
        {"_id": "b", "id": 2, "title": "Newer", "message": "m2", "read_by": [], "created_at": 2},
    ]


def test_lists_newest_first_with_per_user_read_state(monkeypatch):
    fake = FakeDb(_docs())
    monkeypatch.setattr(db, "_database", lambda: fake)
    result = db.list_notifications(7)
    assert [n["title"] for n in result["notifications"]] == ["Newer", "Older"]
    assert [n["read"] for n in result["notifications"]] == [False, True]
    assert result["unread_count"] == 1
    assert "read_by" not in result["notifications"][0] and "_id" not in result["notifications"][0]
    assert db.list_notifications(8)["unread_count"] == 2


def test_mark_selected_and_all_read_is_per_user(monkeypatch):
    fake = FakeDb(_docs())
    monkeypatch.setattr(db, "_database", lambda: fake)
    assert db.mark_notifications_read(8, [2]) == 1
    assert db.list_notifications(8)["unread_count"] == 1
    assert db.mark_notifications_read(8) == 1
    assert db.list_notifications(8)["unread_count"] == 0
    assert db.list_notifications(7)["unread_count"] == 1


class BackfillJds:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query, projection=None):
        return [d for d in self.docs if d.get("status") == query.get("status")]


class BackfillNotifications:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find_one(self, query):
        return next((d for d in self.docs if all(d.get(k) == v for k, v in query.items())), None)

    def insert_one(self, doc):
        self.docs.append(doc)


class BackfillComparisons:
    def __init__(self, selected_by_jd):
        self.selected_by_jd = selected_by_jd

    def count_documents(self, query):
        return self.selected_by_jd.get(query["jd_id"], 0)


class BackfillCounters:
    seq = 0

    def find_one_and_update(self, *args, **kwargs):
        BackfillCounters.seq += 1
        return {"seq": BackfillCounters.seq}


class BackfillDb:
    def __init__(self, jds, selected, notes=None):
        self.job_descriptions = BackfillJds(jds)
        self.notifications = BackfillNotifications(notes)
        self.comparisons = BackfillComparisons(selected)
        self.counters = BackfillCounters()


def test_backfill_creates_missing_notifications_once(monkeypatch):
    fake = BackfillDb(
        jds=[
            {"id": 1, "status": "Closed", "title": "Data Engineer", "required_candidate_count": 2, "updated_at": "t1"},
            {"id": 2, "status": "Closed", "title": "QA", "required_candidate_count": 3},       # not met
            {"id": 3, "status": "Closed", "title": "Ops", "required_candidate_count": None},   # no target
            {"id": 4, "status": "Active", "title": "ML", "required_candidate_count": 1},       # still open
        ],
        selected={1: 2, 2: 1, 4: 5},
    )
    monkeypatch.setattr(db, "_database", lambda: fake)
    assert db.backfill_fulfilled_jd_notifications() == 1
    [note] = fake.notifications.docs
    assert note["jd_id"] == 1 and note["type"] == "jd_requirement_fulfilled"
    assert "Data Engineer has 2 of 2" in note["message"] and note["created_at"] == "t1"
    assert db.backfill_fulfilled_jd_notifications() == 0
    assert len(fake.notifications.docs) == 1
