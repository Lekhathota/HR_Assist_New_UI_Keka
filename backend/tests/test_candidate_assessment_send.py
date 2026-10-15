"""Send Assessment from Talent / All Details, including candidates rejected at screening.

Runs the real workflow (candidate_assessment_service) and the real send preparation,
link building and invite template against an in-memory assessment repository.
AI generation and SMTP are fakes: nothing is generated or emailed.
"""
from __future__ import annotations

import copy
import sys
import unittest
import uuid
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask

from assessment.models import AssessmentStatus as S
from assessment.utilities import utc_now
from services import assessment_service
from services import candidate_assessment_service as workflow
from services.candidate_assessment_service import AssessmentWorkflowError
from services.interview_service import EmailDeliveryUnknown

RECRUITER = {"id": 7, "username": "rec", "role": "recruiter", "email": "rec@example.com"}
ENV = {"SMTP_USER": "hr@example.com", "SMTP_PASS": "secret", "CANDIDATE_TEST_BASE_URL": "https://hr.example.com"}


def question(i, **overrides):
    return {"id": 100 + i, "question_text": f"Question {i}", "question_type": "mcq", "options": ["A", "B", "C", "D"],
            "correct_answer": "A", "points": 5, **overrides}


def stored(value):
    """Mongo persists the str value of AssessmentStatus members."""
    return getattr(value, "value", value)


class FakeRepo:
    """In-memory twin of the assessment repository functions the workflow uses."""

    def __init__(self):
        self.assessments: dict[int, dict] = {}
        self.questions: dict[int, list] = {}
        self.results: dict[int, dict] = {}
        self.requests: dict[tuple, dict] = {}
        self.deleted: list[int] = []
        self.clock = utc_now()

    def add(self, **row):
        assessment_id = len(self.assessments) + 1
        self.clock += timedelta(seconds=1)
        self.assessments[assessment_id] = {"id": assessment_id, "candidate_id": 10, "jd_id": 20, "recruiter_id": 7,
                                           "status": S.DRAFT, "title": "QA Assessment", "candidate_name": "Asha Rao",
                                           "job_role": "QA Engineer", "passing_score": 70, "time_limit_minutes": 90,
                                           "created_at": self.clock, **row}
        self.assessments[assessment_id]["status"] = stored(self.assessments[assessment_id]["status"])
        self.questions[assessment_id] = [question(i) for i in range(3)]
        return assessment_id

    def _for(self, candidate_id, jd_id):
        rows = [r for r in self.assessments.values() if r["candidate_id"] == candidate_id and r["jd_id"] == jd_id]
        return sorted(rows, key=lambda r: r["created_at"], reverse=True)

    def get_assessment_by_id(self, assessment_id):
        row = self.assessments.get(int(assessment_id))
        return copy.deepcopy(row) if row else None

    def get_latest_assessment_for_candidate_jd(self, candidate_id, jd_id):
        rows = self._for(candidate_id, jd_id)
        return copy.deepcopy(rows[0]) if rows else None

    def get_active_assessment_for_candidate_jd(self, candidate_id, jd_id):
        rows = [r for r in self._for(candidate_id, jd_id) if r["status"] not in S.terminal_states()]
        return copy.deepcopy(rows[0]) if rows else None

    def get_assessments_for_candidate(self, candidate_id):
        rows = [r for r in self.assessments.values() if r["candidate_id"] == candidate_id]
        return copy.deepcopy(sorted(rows, key=lambda r: r["created_at"], reverse=True))

    def get_questions_for_assessment(self, assessment_id):
        return copy.deepcopy(self.questions.get(int(assessment_id), []))

    def get_result_by_assessment_id(self, assessment_id):
        return self.results.get(int(assessment_id))

    def update_assessment(self, assessment_id, patch_doc):
        row = self.assessments[int(assessment_id)]
        for key, value in patch_doc.items():
            if key == "access_token" and not value:
                row.pop("access_token", None)
            else:
                row[key] = stored(value)
        return True

    def push_delivery_event(self, assessment_id, event):
        self.assessments[int(assessment_id)].setdefault("delivery_history", []).append(dict(event))

    def delete_assessment_cascade(self, assessment_id):
        self.deleted.append(assessment_id)
        self.assessments.pop(int(assessment_id), None)

    def claim_send_request(self, candidate_id, jd_id, request_id, lease_seconds):
        key = (candidate_id, jd_id)
        current = self.requests.get(key)
        if current and current["lease_until"] > utc_now():
            return None
        self.requests[key] = {"candidate_id": candidate_id, "jd_id": jd_id, "request_id": request_id,
                              "state": "processing", "lease_until": utc_now() + timedelta(seconds=lease_seconds)}
        return self.requests[key]

    def finish_send_request(self, candidate_id, jd_id, request_id, *, state, error="", assessment_id=None):
        row = self.requests.get((candidate_id, jd_id))
        if row and row["request_id"] == request_id:
            self.clock += timedelta(seconds=1)
            row.update(state=state, last_error=error, assessment_id=assessment_id, lease_until=utc_now(), updated_at=self.clock)

    def get_send_requests_for_candidate(self, candidate_id):
        return [copy.deepcopy(r) for r in self.requests.values() if r["candidate_id"] == candidate_id]


class WorkflowTestBase(unittest.TestCase):
    candidate = {"id": 10, "name": "Asha Rao", "email": "asha@example.com", "status": "Rejected"}
    jd = {"id": 20, "title": "QA Engineer", "client_name": "Acme", "status": "Active"}
    selected = False

    def setUp(self):
        self.repo = FakeRepo()
        self.sent: list[dict] = []
        self.send_effects: list = []
        self.generate_calls: list[dict] = []
        self.generate_effect = None
        self.candidates = {10: dict(self.candidate)}
        self.jds = {20: dict(self.jd)}
        self.stack = ExitStack()
        self.stack.enter_context(patch.dict("os.environ", ENV))
        for name in ("get_assessment_by_id", "get_latest_assessment_for_candidate_jd", "get_active_assessment_for_candidate_jd",
                     "get_assessments_for_candidate", "get_questions_for_assessment", "get_result_by_assessment_id",
                     "update_assessment", "push_delivery_event", "delete_assessment_cascade", "claim_send_request",
                     "finish_send_request", "get_send_requests_for_candidate"):
            self.stack.enter_context(patch.object(workflow.assessment_repo, name, side_effect=getattr(self.repo, name)))
        self.stack.enter_context(patch.object(workflow.db, "get_candidate_by_id", side_effect=lambda i: copy.deepcopy(self.candidates.get(int(i)))))
        self.stack.enter_context(patch.object(workflow.db, "get_jd_by_id", side_effect=lambda i, include_raw_text=False: copy.deepcopy(self.jds.get(int(i)))))
        self.audit = self.stack.enter_context(patch.object(workflow.db, "log_audit"))
        self.update_candidate = self.stack.enter_context(patch.object(workflow.db, "update_candidate"))
        self.stack.enter_context(patch.object(workflow, "_candidate_selected_for_jd", side_effect=lambda c, j: self.selected))
        self.stack.enter_context(patch.object(workflow, "generate_assessment", side_effect=self.fake_generate))
        self.stack.enter_context(patch.object(workflow, "send_email", side_effect=self.fake_send))

    def tearDown(self):
        self.stack.close()

    def fake_generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        if self.generate_effect:
            effect = self.generate_effect
            if isinstance(effect, Exception):
                raise effect
            return effect(kwargs)
        candidate = self.candidates[kwargs["candidate_id"]]
        assessment_id = self.repo.add(candidate_email=candidate.get("email") or "", passing_score=kwargs["passing_score"],
                                      time_limit_minutes=kwargs["time_limit_minutes"], **kwargs["provenance"])
        row = self.repo.assessments[assessment_id]
        return {"assessment": dict(row), "questions": self.repo.get_questions_for_assessment(assessment_id)}

    def fake_send(self, to_email, subject, body, from_email, primary_link=""):
        if self.send_effects:
            effect = self.send_effects.pop(0)
            if effect is not None:
                raise effect
        self.sent.append({"to": to_email, "subject": subject, "body": body, "link": primary_link})

    def send(self, **kwargs):
        kwargs.setdefault("jd_id", 20)
        kwargs.setdefault("request_id", str(uuid.uuid4()))
        return workflow.send_assessment_to_candidate(10, recruiter=RECRUITER, **kwargs)

    def assert_error(self, code, status, **kwargs):
        with self.assertRaises(AssessmentWorkflowError) as ctx:
            self.send(**kwargs)
        self.assertEqual((ctx.exception.code, ctx.exception.status_code), (code, status), str(ctx.exception))
        return ctx.exception

    @property
    def only(self):
        self.assertEqual(len(self.repo.assessments), 1)
        return next(iter(self.repo.assessments.values()))


class RejectedCandidateTests(WorkflowTestBase):
    def test_rejected_candidate_gets_a_generated_assessment_and_one_email(self):
        result = self.send()
        self.assertEqual(result["code"], "sent")
        self.assertEqual(len(self.generate_calls), 1)
        call = self.generate_calls[0]
        self.assertFalse(call["require_selected"])
        self.assertEqual((call["candidate_id"], call["jd_id"], call["recruiter_id"]), (10, 20, 7))
        self.assertTrue(call["provenance"]["screening_override"])
        self.assertEqual(call["provenance"]["initiated_by"], "rec")

        row = self.only
        self.assertEqual(row["status"], S.SENT)
        self.assertEqual(row["email_delivery_status"], "sent")
        self.assertEqual([e["status"] for e in row["delivery_history"]], ["sent"])
        link = f"https://hr.example.com/assessment/{row['access_token']}"
        self.assertEqual(len(self.sent), 1)
        email = self.sent[0]
        self.assertEqual(email["to"], "asha@example.com")
        self.assertEqual(email["link"], link)
        self.assertIn(link, email["body"])
        self.assertIn("QA Engineer", email["body"])
        self.assertIn("Complete by:", email["body"])
        self.assertIn("Instructions:", email["body"])
        self.assertIn("Time limit: 90 minutes", email["body"])

        view = result["assessment"]
        self.assertEqual(view["lifecycle"], "awaiting_response")
        self.assertEqual(view["assessment_link"], link)
        self.assertEqual((view["jd_title"], view["client_name"]), ("QA Engineer", "Acme"))
        # The link carries only the random token: no candidate data, ids or secrets.
        self.assertNotIn("asha", link)
        self.assertNotIn("secret", link)
        # Generating or sending never moves the hiring stage.
        self.update_candidate.assert_not_called()

    def test_selected_candidate_is_not_flagged_as_override(self):
        self.selected = True
        self.send()
        self.assertFalse(self.generate_calls[0]["provenance"]["screening_override"])


class EmailValidationTests(WorkflowTestBase):
    def test_missing_email_asks_the_recruiter_and_sends_nothing(self):
        self.candidates[10]["email"] = ""
        self.assert_error("email_missing", 422)
        self.assertEqual((self.generate_calls, self.sent), ([], []))

    def test_invalid_email_is_rejected_without_fallback(self):
        self.candidates[10]["email"] = "asha@example"
        error = self.assert_error("email_invalid", 422)
        self.assertEqual(error.extra["email"], "asha@example")
        self.assert_error("email_invalid", 422, to_email="still wrong")
        self.assertEqual((self.generate_calls, self.sent), ([], []))

    def test_recruiter_corrected_email_is_used_for_this_assessment_only(self):
        self.candidates[10]["email"] = ""
        self.send(to_email="  asha.rao@example.com ")
        self.assertEqual(self.sent[0]["to"], "asha.rao@example.com")
        self.assertEqual(self.only["candidate_email"], "asha.rao@example.com")
        self.update_candidate.assert_not_called()


class JdValidationTests(WorkflowTestBase):
    def test_unknown_jd(self):
        self.assert_error("invalid_jd", 404, jd_id=999)

    def test_closed_jd(self):
        self.jds[20]["status"] = "Closed"
        self.assert_error("jd_closed", 409)
        self.assertEqual(self.generate_calls, [])

    def test_missing_server_configuration_fails_before_generation(self):
        with patch.dict("os.environ", {"SMTP_PASS": ""}):
            self.assert_error("email_not_configured", 503)
        with patch.dict("os.environ", {"CANDIDATE_TEST_BASE_URL": "http://localhost:3000"}):
            self.assert_error("link_not_configured", 503)
        self.assertEqual(self.generate_calls, [])


class GenerationFailureTests(WorkflowTestBase):
    def test_generation_failure_sends_nothing_and_can_be_retried(self):
        self.generate_effect = assessment_service.AssessmentServiceError("AI assessment generation failed.")
        error = self.assert_error("generation_failed", 502)
        self.assertIn("AI assessment generation failed", str(error))
        self.assertEqual((self.repo.assessments, self.sent), ({}, []))
        failures = workflow.list_candidate_assessments(10)["generation_failures"]
        self.assertEqual([f["jd_title"] for f in failures], ["QA Engineer"])

        self.generate_effect = None
        self.assertEqual(self.send()["code"], "sent")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(workflow.list_candidate_assessments(10)["generation_failures"], [])

    def test_incomplete_assessment_is_discarded(self):
        def incomplete(kwargs):
            assessment_id = self.repo.add(**kwargs["provenance"])
            self.repo.questions[assessment_id] = [question(0, options=["A"])]
            return {"assessment": dict(self.repo.assessments[assessment_id]), "questions": self.repo.questions[assessment_id]}
        self.generate_effect = incomplete
        self.assert_error("generation_failed", 502)
        self.assertEqual(self.repo.deleted, [1])
        self.assertEqual(self.sent, [])


class DeliveryTests(WorkflowTestBase):
    def test_email_failure_keeps_the_attempt_and_retry_does_not_regenerate(self):
        self.send_effects = [RuntimeError("SMTP authentication failed.")]
        error = self.assert_error("delivery_failed", 502)
        self.assertEqual(error.extra["assessment_id"], 1)
        row = self.only
        self.assertEqual(row["status"], S.DRAFT)
        self.assertNotIn("access_token", row)
        self.assertEqual(row["email_delivery_status"], "failed")
        self.assertEqual(workflow.list_candidate_assessments(10)["assessments"][0]["lifecycle"], "delivery_failed")

        self.send()
        self.assertEqual(len(self.generate_calls), 1)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.only["status"], S.SENT)
        self.assertEqual([e["status"] for e in self.only["delivery_history"]], ["failed", "sent"])

    def test_uncertain_delivery_is_never_resent_without_confirmation(self):
        self.send_effects = [EmailDeliveryUnknown("connection lost after DATA")]
        result = self.send()
        self.assertEqual(result["code"], "delivery_unknown")
        self.assertEqual(result["assessment"]["lifecycle"], "delivery_unknown")
        token = self.only["access_token"]
        self.assertEqual(self.only["status"], S.SENT)

        error = self.assert_error("already_sent", 409)
        self.assertEqual(error.extra["assessment"]["lifecycle"], "delivery_unknown")
        self.assertEqual(self.sent, [])

        self.send(resend=True)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.only["access_token"], token)
        self.assertEqual(len(self.generate_calls), 1)

    def test_retried_request_returns_the_first_outcome(self):
        request_id = str(uuid.uuid4())
        self.send(request_id=request_id)
        replay = self.send(request_id=request_id)
        self.assertEqual(replay["code"], "replayed")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(self.generate_calls), 1)

    def test_concurrent_request_is_refused_while_one_is_generating(self):
        self.repo.claim_send_request(10, 20, "other-request-0001", 600)
        self.assert_error("request_in_progress", 409)
        self.assertEqual((self.generate_calls, self.sent), ([], []))

    def test_already_sent_requires_explicit_resend_of_the_same_link(self):
        self.send()
        token = self.only["access_token"]
        self.assert_error("already_sent", 409)
        self.assertEqual(len(self.sent), 1)
        self.send(resend=True)
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.sent[0]["link"], self.sent[1]["link"])
        self.assertEqual(self.only["access_token"], token)

    def test_expired_link_is_reported_and_resend_reactivates_it(self):
        self.send()
        self.only["token_expires_at"] = utc_now() - timedelta(minutes=1)
        error = self.assert_error("already_sent", 409)
        self.assertEqual(error.extra["assessment"]["lifecycle"], "expired")
        self.send(resend=True)
        self.assertGreater(self.only["token_expires_at"], utc_now())

    def test_started_or_submitted_attempts_cannot_be_replaced(self):
        self.send()
        for status, code in ((S.IN_PROGRESS, "attempt_in_progress"), (S.COMPLETED, "attempt_submitted")):
            self.only["status"] = stored(status)
            self.assert_error(code, 409, resend=True)
        self.assertEqual(len(self.sent), 1)

    def test_a_finished_attempt_allows_a_new_one(self):
        self.send()
        self.only["status"] = stored(S.FAILED)
        self.send()
        self.assertEqual(len(self.repo.assessments), 2)
        self.assertEqual(len(self.sent), 2)


class LifecycleTests(WorkflowTestBase):
    def test_lifecycle_and_results_are_listed_for_the_recruiter(self):
        self.send()
        listing = workflow.list_candidate_assessments(10)
        view = listing["assessments"][0]
        self.assertEqual(view["lifecycle_label"], "Email sent · awaiting candidate")
        self.assertTrue(view["screening_override"])
        self.assertTrue(view["assessment_link"])
        for status, lifecycle in ((S.IN_PROGRESS, "in_progress"), (S.COMPLETED, "submitted"),
                                  (S.PASSED, "evaluated"), (S.FAILED, "evaluated"), (S.TERMINATED, "terminated")):
            self.only["status"] = stored(status)
            self.assertEqual(workflow.list_candidate_assessments(10)["assessments"][0]["lifecycle"], lifecycle)
        self.repo.results[1] = {"assessment_id": 1, "percentage": 82.5, "passed": True, "status": "PASSED", "summary": "Strong"}
        view = workflow.list_candidate_assessments(10)["assessments"][0]
        self.assertEqual((view["result"]["percentage"], view["result"]["passed"]), (82.5, True))
        self.assertEqual(view["assessment_link"], "")  # finished attempts no longer expose a live link

    def test_completed_override_assessment_does_not_change_the_hiring_stage(self):
        with patch.object(assessment_service.db, "update_candidate") as update, \
             patch.object(assessment_service.db, "log_audit"), \
             patch("services.hiring_process_service.advance_after_assessment") as advance:
            assessment_service.record_candidate_outcome({"id": 1, "candidate_id": 10, "jd_id": 20, "screening_override": True}, S.PASSED)
            update.assert_not_called()
            advance.assert_not_called()
            # Normal screening flow is unchanged.
            assessment_service.record_candidate_outcome({"id": 2, "candidate_id": 10, "jd_id": 20}, S.PASSED)
            update.assert_called_once()
            advance.assert_called_once_with(10, 20)


class RouteTests(WorkflowTestBase):
    def setUp(self):
        super().setUp()
        from routes import assessment_routes as routes

        app = Flask(__name__)
        app.register_blueprint(routes.assessment_bp)
        self.client = app.test_client()
        self.user = dict(RECRUITER)
        self.stack.enter_context(patch("services.auth_service.effective_user_id", return_value=7))
        self.stack.enter_context(patch("services.auth_service.current_user", side_effect=lambda: self.user))
        self.stack.enter_context(patch.object(routes, "current_user", side_effect=lambda: self.user))

    def post(self, **body):
        body.setdefault("jd_id", 20)
        body.setdefault("request_id", str(uuid.uuid4()))
        return self.client.post("/api/candidates/10/assessments/send", json=body)

    def test_recruiter_can_send_and_list(self):
        response = self.post()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["code"], "sent")
        listing = self.client.get("/api/candidates/10/assessments").get_json()
        self.assertEqual(len(listing["assessments"]), 1)

    def test_other_roles_are_forbidden(self):
        self.user = {**RECRUITER, "role": "finance"}
        self.assertEqual(self.post().status_code, 403)
        self.assertEqual(self.client.get("/api/candidates/10/assessments").status_code, 403)
        self.assertEqual(self.sent, [])

    def test_admin_is_allowed(self):
        self.user = {**RECRUITER, "role": "admin"}
        self.assertEqual(self.post().status_code, 200)

    def test_error_codes_reach_the_client(self):
        self.assertEqual(self.post(jd_id=None).get_json()["code"], "invalid_jd")
        self.candidates[10]["email"] = ""
        response = self.post()
        self.assertEqual((response.status_code, response.get_json()["code"]), (422, "email_missing"))
        self.assertEqual(self.client.get("/api/candidates/999/assessments").status_code, 404)

    def test_uncertain_delivery_returns_202(self):
        self.send_effects = [EmailDeliveryUnknown("lost")]
        response = self.post()
        self.assertEqual((response.status_code, response.get_json()["code"]), (202, "delivery_unknown"))


if __name__ == "__main__":
    unittest.main()
