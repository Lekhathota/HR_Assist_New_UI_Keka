from contextlib import ExitStack
from datetime import timedelta
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, MagicMock

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import assessment_service as service
from assessment import proctoring_media, repository
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
                 patch.object(proctoring_media, "has_verified_reference", return_value=True), \
                 patch.object(repository, "begin_candidate_attempt", return_value=attempt(proctoring_violation_count=1)) as begin, \
                 patch.object(repository, "update_assessment", return_value=True) as update:
                result = service.start_candidate_assessment("test-token", accepted_terms=True, recording_consent=True)
            self.assertEqual(begin.called, status == "SENT")
            self.assertEqual(result["assessment"]["proctoring_violation_count"], 1)
            self.assertGreater(result["assessment"]["remaining_seconds"], 0)
            self.assertEqual(update.call_args.args[1]["terms_version"], "assessment-proctoring-v2")
            self.assertIn("recording_consent_at", update.call_args.args[1])

    def test_start_requires_recording_consent_and_a_verified_face_photo(self):
        for consent, reference, code in [(False, True, 400), (True, False, 409)]:
            with patch.object(repository, "get_assessment_by_token", return_value=attempt(status="SENT")), \
                 patch.object(proctoring_media, "has_verified_reference", return_value=reference), \
                 patch.object(repository, "begin_candidate_attempt") as begin:
                with self.assertRaises(service.AssessmentServiceError) as error:
                    service.start_candidate_assessment("test-token", accepted_terms=True, recording_consent=consent)
            self.assertEqual(error.exception.status_code, code)
            begin.assert_not_called()

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


class FaceProctoringTests(unittest.TestCase):
    def snapshot(self, snapshot_id, face_ok, kind="periodic"):
        return service.store_face_snapshot("test-token", snapshot_id=snapshot_id, kind=kind, image=b"jpeg",
                                           mime_type="image/jpeg", face_count=int(face_ok), face_ok=face_ok,
                                           issue="" if face_ok else "no_face")

    def test_second_missing_face_terminates_without_scoring(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(repository, "get_assessment_by_token", return_value=attempt()))
            stack.enter_context(patch.object(proctoring_media, "find_snapshot", return_value=None))
            insert = stack.enter_context(patch.object(proctoring_media, "insert_snapshot", return_value=True))
            record = stack.enter_context(patch.object(proctoring_media, "record_face_violation", side_effect=[
                attempt(face_violation_count=1),
                attempt(status="TERMINATED", face_violation_count=2, termination_reason="Face not detected on camera twice"),
            ]))
            finalize = stack.enter_context(patch.object(repository, "mark_answers_final"))
            stack.enter_context(patch.object(service.db, "log_audit"))
            score = stack.enter_context(patch.object(service, "evaluate_assessment"))
            first = self.snapshot("snap-1", False)
            second = self.snapshot("snap-2", False)
        self.assertEqual(first["face_violation_count"], 1)
        self.assertFalse(first["terminated"])
        self.assertTrue(second["terminated"])
        self.assertEqual(insert.call_count, 2)
        self.assertEqual(record.call_count, 2)
        finalize.assert_called_once_with(1)
        score.assert_not_called()

    def test_visible_face_is_stored_without_a_violation(self):
        with patch.object(repository, "get_assessment_by_token", return_value=attempt()), \
             patch.object(proctoring_media, "find_snapshot", return_value=None), \
             patch.object(proctoring_media, "insert_snapshot", return_value=True) as insert, \
             patch.object(proctoring_media, "record_face_violation") as record:
            result = self.snapshot("snap-1", True)
        self.assertTrue(result["face_ok"])
        self.assertTrue(insert.call_args.kwargs["face_ok"])
        record.assert_not_called()

    def test_retried_snapshot_is_not_counted_twice(self):
        with patch.object(repository, "get_assessment_by_token", return_value=attempt(face_violation_count=1)), \
             patch.object(proctoring_media, "find_snapshot", return_value={"snapshot_id": "snap-1"}), \
             patch.object(proctoring_media, "insert_snapshot") as insert, \
             patch.object(proctoring_media, "record_face_violation") as record:
            result = self.snapshot("snap-1", False)
        self.assertEqual(result["face_violation_count"], 1)
        insert.assert_not_called()
        record.assert_not_called()

    def test_reference_photo_allowed_before_start_but_exam_photos_are_not(self):
        with patch.object(repository, "get_assessment_by_token", return_value=attempt(status="SENT", started_at=None)), \
             patch.object(proctoring_media, "find_snapshot", return_value=None), \
             patch.object(proctoring_media, "insert_snapshot", return_value=True) as insert, \
             patch.object(proctoring_media, "record_face_violation") as record:
            self.assertTrue(self.snapshot("ref-1", True, kind="reference")["face_ok"])
            with self.assertRaises(service.AssessmentServiceError) as error:
                self.snapshot("snap-1", False)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(insert.call_count, 1)
        record.assert_not_called()

    def test_recording_chunks_accepted_during_attempt_and_shortly_after_it_closes(self):
        now = utc_now()
        cases = [
            (attempt(), True),
            (attempt(status="TERMINATED", completed_at=now - timedelta(minutes=2)), True),
            (attempt(status="COMPLETED", completed_at=now - timedelta(hours=1)), False),
            (attempt(status="SENT", started_at=None), False),
        ]
        for row, accepted in cases:
            with patch.object(repository, "get_assessment_by_token", return_value=row), \
                 patch.object(proctoring_media, "store_recording_chunk", return_value=True) as store:
                if accepted:
                    service.store_recording_chunk("test-token", stream="camera", session_id="s-1", sequence=0,
                                                  data=b"webm", mime_type="video/webm")
                    store.assert_called_once()
                else:
                    with self.assertRaises(service.AssessmentServiceError):
                        service.store_recording_chunk("test-token", stream="camera", session_id="s-1", sequence=0,
                                                      data=b"webm", mime_type="video/webm")
                    store.assert_not_called()

    def test_atomic_face_violation_counts_each_snapshot_once(self):
        mongo = MagicMock()
        mongo.assessments.find_one_and_update.return_value = attempt(face_violation_count=1)
        with patch.object(proctoring_media, "_database", return_value=mongo):
            proctoring_media.record_face_violation(1, "snap-1", "no_face")
        query, pipeline = mongo.assessments.find_one_and_update.call_args.args
        self.assertEqual(query["status"], "IN_PROGRESS")
        self.assertEqual(query["face_violations.snapshot_id"], {"$ne": "snap-1"})
        self.assertIn("face_violation_count", pipeline[0]["$set"])
        self.assertIn("status", pipeline[-1]["$set"])


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

    def test_snapshot_route_trusts_face_ok_only_with_a_detected_face(self):
        with patch.object(assessment_routes, "store_face_snapshot", return_value={"success": True}) as store:
            response = self.client.post("/api/assessment/proctoring/snapshot", data={
                "token": "test-token", "snapshot_id": "snap-1", "kind": "periodic", "face_ok": "true",
                "face_count": "0", "image": (BytesIO(b"jpeg"), "s.jpg", "image/jpeg")})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(store.call_args.kwargs["face_ok"])
        self.assertEqual(store.call_args.kwargs["issue"], "no_face")

    def test_invalid_snapshots_and_chunks_never_reach_persistence(self):
        big = b"x" * (assessment_routes.MAX_SNAPSHOT_BYTES + 1)
        with patch.object(assessment_routes, "store_face_snapshot") as store, \
             patch.object(assessment_routes, "store_recording_chunk") as chunk:
            for data in [
                {"snapshot_id": "$bad", "kind": "periodic", "image": (BytesIO(b"j"), "s.jpg", "image/jpeg")},
                {"snapshot_id": "s-1", "kind": "invented", "image": (BytesIO(b"j"), "s.jpg", "image/jpeg")},
                {"snapshot_id": "s-1", "kind": "periodic", "image": (BytesIO(b"j"), "s.txt", "text/plain")},
                {"snapshot_id": "s-1", "kind": "periodic", "image": (BytesIO(big), "s.jpg", "image/jpeg")},
                {"snapshot_id": "s-1", "kind": "periodic"},
            ]:
                self.assertEqual(self.client.post("/api/assessment/proctoring/snapshot", data=data).status_code, 400)
            for data in [
                {"stream": "audio", "session_id": "s-1", "sequence": "0", "chunk": (BytesIO(b"w"), "c.webm", "video/webm")},
                {"stream": "camera", "session_id": "s-1", "sequence": "-1", "chunk": (BytesIO(b"w"), "c.webm", "video/webm")},
                {"stream": "screen", "session_id": "s-1", "sequence": "0", "chunk": (BytesIO(b"w"), "c.exe", "application/x-msdownload")},
            ]:
                self.assertEqual(self.client.post("/api/assessment/proctoring/recording", data=data).status_code, 400)
        store.assert_not_called()
        chunk.assert_not_called()

    def test_recording_route_forwards_valid_chunk(self):
        with patch.object(assessment_routes, "store_recording_chunk", return_value={"success": True, "stored": True}) as store:
            response = self.client.post("/api/assessment/proctoring/recording", data={
                "token": "test-token", "stream": "screen", "session_id": "s-1", "sequence": "3",
                "chunk": (BytesIO(b"webm"), "c.webm", "video/webm;codecs=vp8")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(store.call_args.kwargs["sequence"], 3)
        self.assertEqual(store.call_args.kwargs["mime_type"], "video/webm")
        self.assertEqual(store.call_args.kwargs["data"], b"webm")


if __name__ == "__main__":
    unittest.main()
