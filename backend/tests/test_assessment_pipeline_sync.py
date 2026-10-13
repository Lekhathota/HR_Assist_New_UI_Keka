"""Assessment outcomes must reach the candidate's hiring stage on every path."""
from contextlib import ExitStack
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import assessment_service as service
from services import candidate_service
from services import hiring_process_service
from assessment import proctoring_media, repository
from assessment.utilities import utc_now


def attempt(**patches):
    return {"id": 1, "candidate_id": 10, "jd_id": 20, "access_token": "test-token",
            "status": "IN_PROGRESS", "started_at": utc_now(), "time_limit_minutes": 60, **patches}


class OutcomePropagationTests(unittest.TestCase):
    def common(self, stack):
        stack.enter_context(patch.object(repository, "mark_answers_final"))
        stack.enter_context(patch.object(service.db, "log_audit"))
        advance = stack.enter_context(patch("services.hiring_process_service.advance_after_assessment"))
        update = stack.enter_context(patch.object(service.db, "update_candidate"))
        return update, advance

    def test_focus_violation_termination_updates_candidate_stage(self):
        with ExitStack() as stack:
            update, advance = self.common(stack)
            stack.enter_context(patch.object(repository, "get_assessment_by_token", return_value=attempt()))
            stack.enter_context(patch.object(repository, "record_proctoring_violation",
                                             return_value=attempt(status="TERMINATED", proctoring_violation_count=2)))
            service.report_proctoring_violation("test-token", "event-2", "tab_hidden")
        update.assert_called_once_with(10, {"hiring_stage": "Assessment Terminated"})
        advance.assert_not_called()

    def test_face_termination_updates_candidate_stage(self):
        with ExitStack() as stack:
            update, advance = self.common(stack)
            stack.enter_context(patch.object(repository, "get_assessment_by_token", return_value=attempt()))
            stack.enter_context(patch.object(proctoring_media, "find_snapshot", return_value=None))
            stack.enter_context(patch.object(proctoring_media, "insert_snapshot", return_value=True))
            stack.enter_context(patch.object(proctoring_media, "record_face_violation",
                                             return_value=attempt(status="TERMINATED", face_violation_count=2)))
            service.store_face_snapshot("test-token", snapshot_id="s-2", kind="periodic", image=b"j",
                                        mime_type="image/jpeg", face_count=0, face_ok=False, issue="no_face")
        update.assert_called_once_with(10, {"hiring_stage": "Assessment Terminated"})
        advance.assert_not_called()

    def test_first_warning_does_not_touch_the_candidate(self):
        with ExitStack() as stack:
            update, _ = self.common(stack)
            stack.enter_context(patch.object(repository, "get_assessment_by_token", return_value=attempt()))
            stack.enter_context(patch.object(repository, "record_proctoring_violation",
                                             return_value=attempt(proctoring_violation_count=1)))
            service.report_proctoring_violation("test-token", "event-1", "tab_hidden")
        update.assert_not_called()

    def test_only_a_pass_advances_the_hiring_process(self):
        for status, stage, advanced in [("PASSED", "Assessment Passed", True), ("FAILED", "Assessment Failed", False)]:
            with patch.object(service.db, "update_candidate") as update, \
                 patch("services.hiring_process_service.advance_after_assessment") as advance:
                service.record_candidate_outcome(attempt(), status)
            update.assert_called_once_with(10, {"hiring_stage": stage})
            self.assertEqual(advance.called, advanced)


class TalentStageTests(unittest.TestCase):
    def stage(self, candidate, assessment, interview=""):
        mongo = MagicMock()
        mongo.assessments.find_one.return_value = assessment
        with patch.object(candidate_service.db, "_database", return_value=mongo), \
             patch.object(candidate_service, "_interview_stage", return_value=interview):
            return candidate_service._apply_current_hiring_stage(dict(candidate))

    def test_latest_assessment_drives_the_talent_stage(self):
        for status, label in [("SENT", "Assessment Sent"), ("IN_PROGRESS", "Assessment In Progress"),
                              ("PASSED", "Assessment Passed"), ("FAILED", "Assessment Failed"),
                              ("TERMINATED", "Assessment Terminated")]:
            row = self.stage({"id": 10, "jd_id": 20, "status": "Selected", "hiring_stage": "Screening"},
                             {"id": 1, "status": status, "termination_reason": ""})
            self.assertEqual(row["hiring_stage"], label)
            self.assertEqual(row["assessment_status"], status)

    def test_interview_progress_and_rejection_take_precedence(self):
        row = self.stage({"id": 10, "status": "Selected"}, {"id": 1, "status": "PASSED"}, interview="Interview Scheduled")
        self.assertEqual(row["hiring_stage"], "Interview Scheduled")
        row = self.stage({"id": 10, "status": "Rejected"}, {"id": 1, "status": "PASSED"})
        self.assertEqual(row["hiring_stage"], "Rejected")
        self.assertEqual(row["assessment_status"], "PASSED")

    def test_without_an_assessment_the_screening_stage_is_kept(self):
        row = self.stage({"id": 10, "status": "Selected", "hiring_stage": "Screening"}, None)
        self.assertEqual(row["hiring_stage"], "Screening")
        self.assertNotIn("assessment_status", row)

    def test_inherited_pipeline_places_candidate_on_the_assessment_step(self):
        steps = [{"id": "a", "name": "Screening"}, {"id": "b", "name": "Online Assessment"}, {"id": "c", "name": "Interview"}]
        with patch.object(hiring_process_service, "resolve_process", return_value={"steps": steps, "event_mappings": {}}):
            effective = hiring_process_service.compute_effective_stage(
                {"status": "Selected", "hiring_stage": "Assessment Terminated"}, {"hiring_process": None})
        self.assertEqual(effective["stage_id"], "b")


if __name__ == "__main__":
    unittest.main()
