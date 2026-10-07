import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask

import database as db
import routes.auth_routes as auth_routes
import services.auth_service as auth_service


class Result:
    def __init__(self, n):
        self.deleted_count = n


class Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find_one(self, query, projection=None):
        return next((d for d in self.docs if all(d.get(k) == v for k, v in query.items())), None)

    def delete_one(self, query):
        doc = self.find_one(query)
        if doc:
            self.docs.remove(doc)
        return Result(1 if doc else 0)

    def delete_many(self, query):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not all(d.get(k) == v for k, v in query.items())]
        return Result(before - len(self.docs))

    def update_one(self, query, update, upsert=False):
        doc = self.find_one(query)
        if doc is None and upsert:
            doc = dict(query)
            self.docs.append(doc)
        if doc is not None:
            doc.update(update.get("$set", {}))


class FakeDb:
    def __init__(self):
        self.users = Collection([
            {"id": 1, "username": "lekha", "role": "admin", "is_active": True},
            {"id": 2, "username": "recruiter", "role": "recruiter", "is_active": True},
            {"id": 3, "username": "boss", "role": "admin", "is_active": False},
        ])
        self.user_session_tokens = Collection([{"user_id": 2, "token": "a"}, {"user_id": 1, "token": "b"}])
        self.deleted_users = Collection()


def client(monkeypatch):
    fake = FakeDb()
    monkeypatch.setattr(db, "_database", lambda: fake)
    monkeypatch.setattr(db, "get_user_by_id", lambda uid: dict(fake.users.find_one({"id": int(uid)}) or {}) or None)
    monkeypatch.setattr(db, "list_users", lambda: [dict(u) for u in fake.users.docs])
    monkeypatch.setattr(db, "log_audit", lambda *a, **k: None)
    monkeypatch.setattr(auth_service, "effective_user_id", lambda: 1)
    monkeypatch.setattr(auth_routes, "_admin_user", lambda: ({"id": 1, "username": "lekha", "role": "admin"}, None))
    app = Flask(__name__)
    app.register_blueprint(auth_routes.auth_bp)
    return fake, app.test_client()


def test_admin_removes_user_and_their_sessions(monkeypatch):
    fake, http = client(monkeypatch)
    response = http.delete("/api/admin/users/2")
    assert response.status_code == 200
    assert [u["id"] for u in fake.users.docs] == [1, 3]
    assert [t["user_id"] for t in fake.user_session_tokens.docs] == [1]
    assert fake.deleted_users.find_one({"username": "recruiter"})["deleted_by"] == "lekha"


def test_cannot_remove_self_last_admin_or_missing_user(monkeypatch):
    fake, http = client(monkeypatch)
    assert http.delete("/api/admin/users/1").status_code == 400
    assert http.delete("/api/admin/users/99").status_code == 404
    # An inactive admin can be removed; the signed-in admin stays the active one.
    assert http.delete("/api/admin/users/3").status_code == 200
    assert [u["id"] for u in fake.users.docs] == [1, 2]


def test_last_active_admin_cannot_be_removed(monkeypatch):
    fake, http = client(monkeypatch)
    fake.users.docs.append({"id": 4, "username": "other", "role": "admin", "is_active": True})
    fake.users.docs[0]["is_active"] = False  # signed-in admin row inactive for this check
    assert http.delete("/api/admin/users/4").status_code == 400


def test_seeding_skips_removed_default_accounts(monkeypatch):
    fake = FakeDb()
    fake.users.docs = []
    fake.deleted_users.docs = [{"username": "recruiter"}]
    inserted = []
    fake.users.insert_one = inserted.append
    monkeypatch.setattr(db, "_database", lambda: fake)
    monkeypatch.setattr(db, "_next_id", lambda name: len(inserted) + 1)
    for key in ("SEED_DEFAULT_USERS", "DEFAULT_ADMIN_PASSWORD", "DEFAULT_RECRUITER_PASSWORD", "DEFAULT_HR_PASSWORD", "DEFAULT_MANAGER_PASSWORD"):
        monkeypatch.setenv(key, "1" if key == "SEED_DEFAULT_USERS" else "pw-123456789012")
    db._seed_default_users()
    assert sorted(u["username"] for u in inserted) == ["finance", "hr", "manager"]
