"""Interview status dropdown: outcome endpoint and recruiter-set candidate statuses.

Runs the real route and database.update_interview against an in-memory interviews collection.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask

import database as db
from routes import interview_routes as routes


class FakeInterviews:
    def __init__(self, rows):
        self.rows = {row["id"]: row for row in rows}

    def find_one(self, query, projection=None):
        row = self.rows.get(query["id"])
        return copy.deepcopy(row) if row else None

    def update_one(self, query, update):
        row = self.rows.get(query["id"])
        if not row:
            return SimpleNamespace(matched_count=0, modified_count=0)
        changed = any(row.get(key) != value for key, value in update["$set"].items())
        row.update(update["$set"])
        return SimpleNamespace(matched_count=1, modified_count=int(changed))


def interview(**overrides):
    return {
        "id": 1, "recruiter_id": 7, "candidate_id": 3, "candidate_phone": "+10000000000", "jd_id": 5,
        "candidate_name": "Asha Rao", "status": "No Show", "attendance_status": "no_show", **overrides,
    }


class InterviewStatusRouteTests(unittest.TestCase):
    def setUp(self):
        self.collection = FakeInterviews([interview()])
        app = Flask(__name__)
        app.register_blueprint(routes.interview_bp)
        self.client = app.test_client()
        self.stopped = []
        self.stage_events = []
        self.patches = [
            patch.object(db, "_database", return_value=SimpleNamespace(interviews=self.collection)),
            patch.object(db, "refresh_dashboard_metrics"),
            patch.object(db.activity_feed, "emit"),
            patch.object(db, "log_audit"),
            patch.object(db, "update_candidate"),
            patch("services.auth_service.effective_user_id", return_value=7),
            patch.object(routes, "current_user", return_value={"id": 7, "username": "rec"}),
            patch.object(routes, "_stop_interview_recovery", side_effect=lambda i, o: self.stopped.append((i, o))),
            patch.object(routes, "_apply_stage_event", side_effect=lambda c, j, e: self.stage_events.append(e)),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def post(self, outcome, path="/api/interviews/1/outcome", **extra):
        return self.client.post(path, json={"outcome": outcome, **extra})

    @property
    def row(self):
        return self.collection.rows[1]

    def test_candidate_statuses_are_saved_without_touching_status_or_recovery(self):
        for value in ("interested", "not_interested", "follow_up", "awaiting_reply", "pending_review"):
            with self.subTest(value=value):
                response = self.post(value)
                self.assertEqual(response.status_code, 200, response.get_json())
                body = response.get_json()
                self.assertEqual(body["interview"]["candidate_status"], value)
                self.assertEqual(self.row["candidate_status"], value)
                self.assertEqual(self.row["candidate_status_updated_by"], "rec")
                self.assertEqual(self.row["status"], "No Show")
                self.assertEqual(self.row["attendance_status"], "no_show")
        # No recovery case was closed and no hiring stage moved.
        self.assertEqual(self.stopped, [])
        self.assertEqual(self.stage_events, [])
        db.update_candidate.assert_not_called()

    def test_fallback_endpoint_accepts_candidate_statuses(self):
        response = self.post("interested", path="/api/interviews/outcome", interview_id=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.row["candidate_status"], "interested")

    def test_selected_and_rejected_keep_existing_behaviour_and_clear_the_label(self):
        for outcome, status, event in (
            ("selected", "Client Interview Pending", "selected_after_interview"),
            ("rejected", "Rejected After Interview", "rejected_after_interview"),
        ):
            with self.subTest(outcome=outcome):
                self.collection.rows[1] = interview(candidate_status="interested")
                self.stopped.clear()
                response = self.post(outcome)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.row["status"], status)
                self.assertIsNone(self.row["candidate_status"])
                self.assertEqual(self.stopped, [(1, "interview_completed")])
                self.assertEqual(self.stage_events[-1], event)

    def test_candidate_status_is_rejected_once_the_interview_is_final(self):
        for status in ("Cancelled", "Client Interview Pending", "Rejected After Interview"):
            with self.subTest(status=status):
                self.collection.rows[1] = interview(status=status)
                response = self.post("interested")
                self.assertEqual(response.status_code, 409)
                self.assertNotIn("candidate_status", self.row)

    def test_invalid_outcome_and_other_recruiter_are_refused(self):
        self.assertEqual(self.post("hired").status_code, 400)
        self.assertEqual(self.post("").status_code, 400)
        with patch.object(routes, "current_user", return_value={"id": 99, "username": "other"}):
            self.assertEqual(self.post("interested").status_code, 404)
        self.assertNotIn("candidate_status", self.row)

    def test_workflow_status_change_clears_the_label(self):
        self.collection.rows[1] = interview(status="Scheduled", candidate_status="interested")
        db.update_interview(1, {"status": "Rescheduled"})
        self.assertIsNone(self.row["candidate_status"])

    def test_non_status_updates_keep_the_label(self):
        self.collection.rows[1] = interview(candidate_status="follow_up")
        db.update_interview(1, {"followup_status": "sent"})
        self.assertEqual(self.row["candidate_status"], "follow_up")


if __name__ == "__main__":
    unittest.main()
