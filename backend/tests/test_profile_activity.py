import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import activity_feed
import database as db


def _match(doc, query):
    for key, cond in query.items():
        value = doc.get(key)
        if isinstance(cond, dict):
            if "$ne" in cond and (cond["$ne"] in value if isinstance(value, list) else value == cond["$ne"]):
                return False
            if "$nin" in cond and value in cond["$nin"]:
                return False
            if "$in" in cond and value not in cond["$in"]:
                return False
        elif value != cond:
            return False
    return True


class Cursor(list):
    def sort(self, key, direction):
        return Cursor(sorted(self, key=lambda d: d[key], reverse=direction == db.DESCENDING))

    def limit(self, n):
        return Cursor(self[:n])


class Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, query=None, projection=None):
        return Cursor(d for d in self.docs if _match(d, query or {}))

    def find_one(self, query=None, projection=None, sort=None):
        rows = self.find(query)
        if sort:
            key, direction = sort[0]
            rows = rows.sort(key, direction)
        return rows[0] if rows else None

    def count_documents(self, query):
        return len(self.find(query))

    def distinct(self, field, query):
        return sorted({d.get(field) for d in self.find(query)})

    def insert_one(self, doc):
        self.docs.append(doc)

    def insert_many(self, docs):
        self.docs.extend(docs)

    def update_one(self, query, update):
        for doc in self.find(query):
            for key, value in update.get("$set", {}).items():
                target = doc
                *parents, leaf = key.split(".")
                for part in parents:
                    target = target.setdefault(part, {})
                target[leaf] = value
            return
        return


class Counters:
    def __init__(self):
        self.seq = {}

    def find_one_and_update(self, query, update, **kwargs):
        name = query["_id"]
        self.seq[name] = self.seq.get(name, 0) + 1
        return {"seq": self.seq[name]}


class FakeDb:
    def __init__(self):
        self.users = Collection([{"id": 7, "username": "lekha"}, {"id": 8, "username": "ravi"}])
        self.notifications = Collection()
        self.activity_log = Collection()
        self.report_logs = Collection()
        self.job_descriptions = Collection()
        self.comparisons = Collection()
        self.counters = Counters()


def setup(monkeypatch):
    fake = FakeDb()
    monkeypatch.setattr(db, "_database", lambda: fake)
    monkeypatch.setattr(db, "_notification_backfill_done", True)
    return fake


def test_preferences_default_on_and_only_known_keys_are_saved(monkeypatch):
    setup(monkeypatch)
    assert db.get_user_preferences(7) == {"notify_jobs": True, "notify_talent": True, "notify_pipeline": True}
    saved = db.save_user_preferences(7, {"notify_talent": False, "is_admin": True})
    assert saved == {"notify_jobs": True, "notify_talent": False, "notify_pipeline": True}
    assert "is_admin" not in db._database().users.find_one({"id": 7}).get("preferences", {})
    assert db.get_user_preferences(8)["notify_talent"] is True  # per user


def test_muted_categories_hide_notifications_and_their_unread_count(monkeypatch):
    fake = setup(monkeypatch)
    fake.notifications.docs = [
        {"id": 1, "type": "resume_uploaded", "title": "t", "message": "m", "read_by": [], "created_at": 1},
        {"id": 2, "type": "jd_created", "title": "t", "message": "m", "read_by": [], "created_at": 2},
    ]
    assert db.list_notifications(7)["unread_count"] == 2
    db.save_user_preferences(7, {"notify_talent": False})
    result = db.list_notifications(7)
    assert [n["type"] for n in result["notifications"]] == ["jd_created"]
    assert result["unread_count"] == 1


def test_report_ids_are_sequential_and_logged(monkeypatch):
    fake = setup(monkeypatch)
    first = db.issue_report({"id": 7, "username": "lekha"}, "jobs", "pdf")
    second = db.issue_report({"id": 7, "username": "lekha"}, "talent", "csv")
    assert re.fullmatch(r"RPT-\d{8}-0001", first) and second.endswith("-0002")
    assert [r["scope"] for r in fake.report_logs.docs] == ["jobs", "talent"]


def test_user_activity_stats_count_only_that_users_actions(monkeypatch):
    setup(monkeypatch)
    lekha, ravi = {"id": 7, "username": "lekha"}, {"id": 8, "username": "ravi"}
    db.record_activity_events([{"kind": "jd_created", "jd_id": 1}], lekha, "r1")
    db.record_activity_events([{"kind": "resume_uploaded", "candidate_id": c} for c in (1, 2, 3)]
                              + [{"kind": "screening", "candidate_id": c} for c in (1, 2, 3)], lekha, "r2")
    db.record_activity_events([{"kind": "screening", "candidate_id": 4}], lekha, "r3")
    db.record_activity_events([{"kind": "jd_created", "jd_id": 2}], ravi, "r4")
    db.issue_report(lekha, "jobs", "pdf")
    stats = db.user_activity_stats(7)
    assert {k: stats[k] for k in ("jds_created", "screenings_run", "candidates_added", "reports_generated")} == {
        "jds_created": 1, "screenings_run": 2, "candidates_added": 3, "reports_generated": 1,
    }
    assert stats["tracking_since"] is not None
    assert db.user_activity_stats(8)["jds_created"] == 1


def test_report_generated_notification_text():
    [note] = activity_feed.build_notifications(
        [{"kind": "report_generated", "report_id": "RPT-20261006-0007", "scope": "talent", "format": "pdf"}], "lekha", {})
    assert note["message"] == "Talent report RPT-20261006-0007 (PDF) was generated by lekha."
    assert note["type"] in db.NOTIFICATION_CATEGORIES["notify_jobs"]
