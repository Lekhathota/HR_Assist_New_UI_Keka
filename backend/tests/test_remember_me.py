import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database as db


class Tokens:
    def __init__(self):
        self.docs = []

    def insert_one(self, doc):
        self.docs.append(dict(doc))

    def find(self, query, projection=None):
        return [d for d in self.docs if all(d.get(k) == v for k, v in query.items())]

    def find_one(self, query):
        rows = self.find(query)
        return rows[0] if rows else None

    def delete_one(self, query):
        self.docs = [d for d in self.docs if not all(d.get(k) == v for k, v in query.items())]

    def delete_many(self, query):
        tokens = set(query["token"]["$in"])
        self.docs = [d for d in self.docs if d["token"] not in tokens]


class FakeDb:
    def __init__(self):
        self.user_session_tokens = Tokens()


NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def setup(monkeypatch, now=NOW):
    fake = FakeDb()
    monkeypatch.setattr(db, "_database", lambda: fake)
    monkeypatch.setattr(db, "_now", lambda: now)
    return fake


def test_remember_me_sessions_last_30_days_normal_ones_12_hours(monkeypatch):
    setup(monkeypatch)
    assert db.create_user_session_token(1, "short", remember=False) == NOW + timedelta(hours=12)
    assert db.create_user_session_token(1, "long", remember=True) == NOW + timedelta(days=30)


def test_token_validity_follows_its_own_expiry(monkeypatch):
    fake = setup(monkeypatch)
    db.create_user_session_token(1, "short", remember=False)
    db.create_user_session_token(1, "long", remember=True)
    monkeypatch.setattr(db, "_now", lambda: NOW + timedelta(days=2))
    assert db.user_id_for_session_token("short") is None          # expired after 12h
    assert db.user_id_for_session_token("long") == 1               # remembered: still signed in
    assert [d["token"] for d in fake.user_session_tokens.docs] == ["long"]
    monkeypatch.setattr(db, "_now", lambda: NOW + timedelta(days=31))
    assert db.user_id_for_session_token("long") is None


def test_logging_in_elsewhere_keeps_other_sessions_and_prunes_stale_ones(monkeypatch):
    fake = setup(monkeypatch)
    fake.user_session_tokens.insert_one({"token": "old", "user_id": 1, "created_at": NOW - timedelta(days=3),
                                         "expires_at": NOW - timedelta(days=1)})
    db.create_user_session_token(1, "laptop", remember=True)
    db.create_user_session_token(1, "desktop", remember=True)
    assert sorted(d["token"] for d in fake.user_session_tokens.docs) == ["desktop", "laptop"]


def test_only_the_newest_sessions_are_kept(monkeypatch):
    fake = setup(monkeypatch)
    for i in range(db.MAX_SESSIONS_PER_USER + 2):
        monkeypatch.setattr(db, "_now", lambda i=i: NOW + timedelta(minutes=i))
        db.create_user_session_token(1, f"t{i}", remember=True)
    tokens = {d["token"] for d in fake.user_session_tokens.docs}
    assert len(tokens) == db.MAX_SESSIONS_PER_USER and "t0" not in tokens and "t1" not in tokens


def test_tokens_issued_before_this_change_keep_the_12_hour_rule(monkeypatch):
    fake = setup(monkeypatch)
    fake.user_session_tokens.insert_one({"token": "legacy", "user_id": 2, "created_at": NOW - timedelta(hours=2)})
    assert db.user_id_for_session_token("legacy") == 2
    monkeypatch.setattr(db, "_now", lambda: NOW + timedelta(hours=11))
    assert db.user_id_for_session_token("legacy") is None
