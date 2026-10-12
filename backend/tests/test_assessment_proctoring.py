from contextlib import ExitStack
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, MagicMock

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import assessment_service as service
from assessment import repository
from assessment.models import AssessmentStatus
from assessment.utilities import utc_now, assert_status_transition, compute_link_status
from routes import assessment_routes


def attempt(**patches):
    return {"id": 1, "candidate_id": 10, "jd_id": 20, "access_token": "test-token",
            "status": "IN_PROGRESS", "started_at": utc_now(), "time_limit_minutes": 60, **patches}


class AssessmentProctoringTests(unittest.TestCase):
    def test_viewing_instructions_does_not_start_the_clock(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(repository, "get_assessment_by_token", return_value=attempt(status="SENT", started_at=None)))
            stack.enter_context(patch.object(repository, "get_questions_for_assessment", return_value=[]))
            stack.enter_context(patch.object(repository, "get_answers_for_assessment", return_value=[]))
            begin = stack.enter_context(patch.object(repository, "begin_candidate_attempt"))
            data = service.get_assessment_by_token("test-token")
        self.assertIsNone(data["assessment"]["started_at"])
        self.assertIsNone(data["assessment"]["remaining_seconds"])
        begin.assert_not_called()

    def test_start_sets_timer_but_resume_does_not_reset_it_or_violations(self):
        for status in ["SENT", "IN_PROGRESS"]:
            row = attempt(status=status, proctoring_violation_count=1)
            with patch.object(repository, "get_assessment_by_token", return_value=row), \
                 patch.object(repository, "begin_candidate_attempt", return_value=attempt(proctoring_violation_count=1)) as begin, \
                 patch.object(repository, "update_assessment", return_value=True) as update:
                result = service.start_candidate_assessment("test-token", accepted_terms=True)
            self.assertEqual(begin.called, status == "SENT")
            self.assertEqual(result["assessment"]["proctoring_violation_count"], 1)
            self.assertGreater(result["assessment"]["remaining_seconds"], 0)
            self.assertEqual(update.call_args.args[1]["terms_version"], "assessment-rules-v1")

    def test_missing_consent_cannot_start_the_timer(self):
        with patch.object(repository, "get_assessment_by_token", return_value=attempt(status="SENT")), \
             patch.object(repository, "begin_candidate_attempt") as begin:
            with self.assertRaises(service.AssessmentServiceError) as error:
                service.start_candidate_assessment("test-token")
        self.assertEqual(error.exception.status_code, 400)
        begin.assert_not_called()

    def test_first_violation_warns_second_closes_without_scoring_or_advancing(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(repository, "get_assessment_by_token", return_value=attempt()))
            record = stack.enter_context(patch.object(repository, "record_proctoring_violation", side_effect=[
                attempt(proctoring_violation_count=1),
                attempt(status="TERMINATED", proctoring_violation_count=2),
            ]))
            finalize = stack.enter_context(patch.object(repository, "mark_answers_final"))
            stack.enter_context(patch.object(service.db, "log_audit"))
            score = stack.enter_context(patch.object(service, "evaluate_assessment"))
            advance = stack.enter_context(patch("services.hiring_process_service.advance_after_assessment"))
            first = service.report_proctoring_violation("test-token", "incident-1", "tab_hidden")
            second = service.report_proctoring_violation("test-token", "incident-2", "back_navigation")
        self.assertEqual(first["violation_count"], 1)
        self.assertFalse(first["terminated"])
        self.assertEqual(second["status"], "TERMINATED")
        self.assertTrue(second["terminated"])
        self.assertEqual(record.call_count, 2)
        finalize.assert_called_once_with(1)
        score.assert_not_called()
        advance.assert_not_called()

    def test_terminated_attempt_cannot_load_start_save_or_submit_even_after_reload(self):
        with patch.object(repository, "get_assessment_by_token", return_value=attempt(status="TERMINATED", proctoring_violation_count=2)):
            for call in [lambda: service.get_assessment_by_token("test-token"),
                         lambda: service.start_candidate_assessment("test-token"),
                         lambda: service.save_answer("test-token", 2, "A"),
                         lambda: service.submit_assessment("test-token", [])]:
                with self.assertRaises(service.AssessmentServiceError) as error:
                    call()
                self.assertEqual(error.exception.status_code, 409)
                self.assertIn("terminated", str(error.exception))

    def test_retry_after_termination_is_idempotent(self):
        with patch.object(repository, "get_assessment_by_token", return_value=attempt(status="TERMINATED", proctoring_violation_count=2)), \
             patch.object(repository, "record_proctoring_violation") as record:
            result = service.report_proctoring_violation("test-token", "same-event", "tab_hidden")
        self.assertEqual(result["violation_count"], 2)
        record.assert_not_called()

    def test_completed_submission_rejects_late_events(self):
        with patch.object(repository, "get_assessment_by_token", return_value=attempt(status="PASSED")), \
             patch.object(repository, "record_proctoring_violation") as record:
            with self.assertRaises(service.AssessmentServiceError):
                service.report_proctoring_violation("test-token", "late-event", "tab_hidden")
        record.assert_not_called()

    def test_violation_winning_submission_race_cannot_award_a_pass(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(repository, "get_assessment_by_token", return_value=attempt()))
            stack.enter_context(patch.object(repository, "get_questions_for_assessment", return_value=[
                {"id": 2, "question_type": "mcq", "correct_answer": "A", "points": 10}]))
            stack.enter_context(patch.object(repository, "upsert_candidate_answer"))
            stack.enter_context(patch.object(repository, "complete_candidate_attempt", return_value=False))
            result = stack.enter_context(patch.object(repository, "upsert_assessment_result"))
            update = stack.enter_context(patch.object(service.db, "update_candidate"))
            with self.assertRaises(service.AssessmentServiceError):
                service.submit_assessment("test-token", [{"question_id": 2, "answer": "A"}])
        result.assert_not_called()
        update.assert_not_called()

    def test_terminated_state_is_terminal_and_link_is_closed(self):
        assert_status_transition("IN_PROGRESS", "TERMINATED")
        self.assertIn("TERMINATED", AssessmentStatus.terminal_states())
        self.assertIn("TERMINATED", AssessmentStatus.submitted_states())
        self.assertEqual(compute_link_status(attempt(status="TERMINATED")), "Terminated")

    def test_atomic_repository_counts_only_new_events_on_active_attempts(self):
        mongo = MagicMock()
        mongo.assessments.find_one_and_update.return_value = attempt(proctoring_violation_count=1)
        with patch.object(repository, "_database", return_value=mongo):
            repository.record_proctoring_violation(1, "event-1", "tab_hidden")
        query, pipeline = mongo.assessments.find_one_and_update.call_args.args
        self.assertEqual(query["status"], "IN_PROGRESS")
        self.assertEqual(query["proctoring_events.event_id"], {"$ne": "event-1"})
        self.assertIsInstance(pipeline, list)
        self.assertIn("status", pipeline[-1]["$set"])
        self.assertIn("proctoring_violation_count", pipeline[0]["$set"])


class ProctoringRouteTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(assessment_routes.assessment_bp)
        self.client = app.test_client()

    def test_public_route_validates_and_forwards_incident(self):
        with patch.object(assessment_routes, "report_proctoring_violation", return_value={"success": True, "violation_count": 1}) as report:
            response = self.client.post("/api/assessment/proctoring-event", json={
                "token": "test-token", "event_id": "event-1", "reason": "tab_hidden"})
        self.assertEqual(response.status_code, 200)
        report.assert_called_once_with("test-token", "event-1", "tab_hidden")

    def test_invalid_events_never_reach_persistence(self):
        with patch.object(assessment_routes, "report_proctoring_violation") as report:
            for payload in [{}, {"event_id": "event-1", "reason": []}, ["invalid"],
                            {"event_id": "$invalid", "reason": "tab_hidden"},
                            {"event_id": "event-1", "reason": "invented"}]:
                response = self.client.post("/api/assessment/proctoring-event", json=payload)
                self.assertEqual(response.status_code, 400)
        report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
