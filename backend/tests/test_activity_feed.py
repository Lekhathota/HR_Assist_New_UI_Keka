import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask

import activity_feed
import database as db

TITLES = {1: "Data Engineer", 2: "QA Lead"}


def build(events, actor="lekha"):
    return activity_feed.build_notifications(events, actor, TITLES)


def test_jd_lifecycle_messages_and_dedupe():
    notes = build([
        {"kind": "jd_created", "jd_id": 1},
        {"kind": "jd_updated", "jd_id": 1},          # categorisation right after upload: suppressed
        {"kind": "jd_status", "jd_id": 2, "old": "Active", "new": "On Hold"},
        {"kind": "jd_updated", "jd_id": 2},          # covered by the status message
        {"kind": "jd_deleted", "jd_id": 9, "jd_title": "Old Role"},
    ])
    assert [(n["type"], n["message"]) for n in notes] == [
        ("jd_created", "Data Engineer was added to Jobs by lekha."),
        ("jd_status", "QA Lead moved from Active to On Hold by lekha."),
        ("jd_deleted", "Old Role was deleted by lekha."),
    ]
    assert notes[0]["link"] == "/jobs/1" and notes[2]["jd_id"] is None


def test_bulk_resume_upload_and_screening_are_grouped():
    notes = build([
        {"kind": "resume_uploaded", "candidate_id": 10, "jd_id": 1, "name": "Aarav"},
        {"kind": "resume_uploaded", "candidate_id": 11, "jd_id": 1, "name": "Priya"},
        {"kind": "resume_uploaded", "candidate_id": 12, "jd_id": 1, "name": "Rahul"},
        {"kind": "screening", "jd_id": 1, "candidate_id": 10, "status": "Selected"},
        {"kind": "screening", "jd_id": 1, "candidate_id": 11, "status": "Rejected"},
        {"kind": "screening", "jd_id": 1, "candidate_id": 12, "status": "Selected"},
        {"kind": "candidate_status", "candidate_id": 10, "jd_id": 1, "name": "Aarav", "new": "Selected"},
    ])
    assert [n["title"] for n in notes] == ["3 resumes uploaded", "Screening completed"]
    assert notes[0]["message"] == "3 candidates added to Talent for Data Engineer by lekha."
    assert notes[1]["message"] == "3 candidates analysed for Data Engineer: 2 selected, 1 rejected."


def test_single_resume_links_to_the_candidate():
    [note] = build([{"kind": "resume_uploaded", "candidate_id": 7, "jd_id": None, "name": "Sneha"}], actor="")
    assert note["title"] == "Resume uploaded"
    assert note["message"] == "Sneha was added to Talent."
    assert note["link"] == "/talent/7"


def test_pipeline_interview_and_assessment_messages():
    notes = build([
        {"kind": "candidate_stage", "candidate_id": 5, "jd_id": 2, "name": "Kiran", "stage": "Technical Round"},
        {"kind": "candidate_hold", "candidate_id": 6, "jd_id": 2, "name": "Meera", "on_hold": True},
        {"kind": "interview", "candidate_id": 5, "jd_id": 2, "name": "Kiran", "status": "Scheduled", "when": "07 Oct 2026, 10:00"},
        {"kind": "assessment", "assessment_id": 3, "jd_id": 2, "name": "Kiran", "status": "SENT"},
        {"kind": "assessment", "assessment_id": 4, "jd_id": 2, "name": "Meera", "status": "DRAFT"},  # not user-facing
    ])
    assert [n["message"] for n in notes] == [
        "Kiran moved to Technical Round for QA Lead by lekha.",
        "Meera was put on hold for QA Lead by lekha.",
        "Interview with Kiran for QA Lead scheduled for 07 Oct 2026, 10:00 by lekha.",
        "The assessment was sent to Kiran for QA Lead by lekha.",
    ]
    assert notes[2]["title"] == "Interview scheduled"
    [cancelled] = build([{"kind": "interview", "candidate_id": 5, "jd_id": 2, "name": "Kiran", "status": "Cancelled"}])
    assert cancelled["title"] == "Interview cancelled"
    assert cancelled["message"] == "Interview with Kiran for QA Lead marked cancelled by lekha."


def test_events_are_buffered_per_request_and_flushed_with_the_actor(monkeypatch):
    created = []
    monkeypatch.setattr(db, "create_notification", lambda *args, **kwargs: created.append((args, kwargs)))
    monkeypatch.setattr(activity_feed, "_jd_titles", lambda _db, _events: TITLES)

    activity_feed.emit("jd_created", jd_id=1)  # outside a request (seed scripts): ignored
    app = Flask(__name__)
    with app.test_request_context("/api/jds/create", method="POST"):
        activity_feed.emit("jd_created", jd_id=1)
        assert activity_feed.flush({"username": "lekha"}) == 1
        assert activity_feed.pending() == []
    (args, kwargs) = created[0]
    assert args == ("jd_created", "New JD uploaded", "Data Engineer was added to Jobs by lekha.")
    assert kwargs == {"jd_id": 1, "link": "/jobs/1", "actor": "lekha"}

    with app.test_request_context("/api/jds/create", method="POST"):
        activity_feed.emit("jd_created", jd_id=2)
        activity_feed.discard()  # failed request
        assert activity_feed.flush({"username": "lekha"}) == 0
    assert len(created) == 1


class _Candidates:
    def __init__(self):
        self.doc = {"id": 5, "name": "Kiran", "jd_id": 2, "status": "Screened", "stage_id": "s1", "on_hold": False}

    def find_one(self, query, projection=None):
        return dict(self.doc)

    def update_one(self, query, update):
        self.doc.update(update["$set"])
        return type("R", (), {"modified_count": 1})()


class _Jds:
    def find_one(self, query, projection=None):
        return {"hiring_process": {"steps": [{"id": "s1", "name": "Screening"}, {"id": "s2", "name": "Technical Round"}]}}


class _Db:
    candidates = _Candidates()
    job_descriptions = _Jds()


def test_update_candidate_reports_stage_moves_by_name(monkeypatch):
    fake = _Db()
    monkeypatch.setattr(db, "_database", lambda: fake)
    monkeypatch.setattr(db, "refresh_dashboard_metrics", lambda: None)
    app = Flask(__name__)
    with app.test_request_context("/api/candidates/5", method="POST"):
        assert db.update_candidate(5, {"stage_id": "s2", "match_score": 80})
        assert activity_feed.pending() == [
            {"kind": "candidate_stage", "candidate_id": 5, "jd_id": 2, "name": "Kiran", "stage": "Technical Round"}
        ]
