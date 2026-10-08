from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import hiring_process_service as hps


def _jd(steps=None, mappings=None):
    return {
        "id": 1,
        "title": "Backend Engineer",
        "hiring_process": {"steps": steps or [], "event_mappings": mappings or {}},
    }


def _candidate(**overrides):
    base = {"id": 10, "jd_id": 1, "stage_id": None, "on_hold": False, "automation_paused": False}
    base.update(overrides)
    return base


class BuildStepsTests(unittest.TestCase):
    def test_assigns_ids_and_preserves_existing_ones(self) -> None:
        steps, error = hps.build_steps([{"id": "abc123", "name": "Resume Review"}, {"name": "Tech Round"}])
        self.assertIsNone(error)
        self.assertEqual(steps[0]["id"], "abc123")
        self.assertEqual(steps[0]["name"], "Resume Review")
        self.assertTrue(steps[1]["id"])
        self.assertEqual(steps[1]["name"], "Tech Round")

    def test_rejects_empty_step_list(self) -> None:
        steps, error = hps.build_steps([])
        self.assertEqual(steps, [])
        self.assertIsNotNone(error)

    def test_rejects_blank_step_name(self) -> None:
        steps, error = hps.build_steps([{"name": "  "}])
        self.assertEqual(steps, [])
        self.assertIsNotNone(error)


class ValidateMappingsTests(unittest.TestCase):
    def test_accepts_null_and_valid_ids(self) -> None:
        steps = [{"id": "s1", "name": "Round 1"}]
        mappings, error = hps.validate_mappings(steps, {"scheduled": "s1", "cancelled": None})
        self.assertIsNone(error)
        self.assertEqual(mappings["scheduled"], "s1")
        self.assertIsNone(mappings["cancelled"])
        self.assertIsNone(mappings["rescheduled"])

    def test_rejects_mapping_to_unknown_step(self) -> None:
        steps = [{"id": "s1", "name": "Round 1"}]
        mappings, error = hps.validate_mappings(steps, {"scheduled": "does-not-exist"})
        self.assertEqual(mappings, {})
        self.assertIsNotNone(error)


class ValidateStepRemovalTests(unittest.TestCase):
    def test_allows_removal_when_unreferenced(self) -> None:
        previous = [{"id": "s1", "name": "Round 1"}, {"id": "s2", "name": "Round 2"}]
        new = [{"id": "s1", "name": "Round 1"}]
        with patch.object(hps.db, "get_all_candidates", return_value=[]):
            error = hps.validate_step_removal(1, previous, new, {"scheduled": "s1"})
        self.assertIsNone(error)

    def test_rejects_removal_referenced_by_mapping(self) -> None:
        previous = [{"id": "s1", "name": "Round 1"}, {"id": "s2", "name": "Round 2"}]
        new = [{"id": "s1", "name": "Round 1"}]
        error = hps.validate_step_removal(1, previous, new, {"scheduled": "s2"})
        self.assertIsNotNone(error)

    def test_rejects_removal_referenced_by_candidate(self) -> None:
        previous = [{"id": "s1", "name": "Round 1"}, {"id": "s2", "name": "Round 2"}]
        new = [{"id": "s1", "name": "Round 1"}]
        with patch.object(hps.db, "get_all_candidates", return_value=[{"id": 10, "stage_id": "s2"}]):
            error = hps.validate_step_removal(1, previous, new, {})
        self.assertIsNotNone(error)


class ComputeEffectiveStageTests(unittest.TestCase):
    def test_talent_candidate_without_job_inherits_own_client_stages(self) -> None:
        steps = [{"id": "s1", "name": "Screening"},
                 {"id": "s2", "name": "Technical"},
                 {"id": "s3", "name": "HR"}, {"id": "s4", "name": "Offer"}]
        with patch.object(hps.db, "get_client_by_id", return_value={"hiring_stages": steps}) as lookup:
            result = hps.compute_effective_stage(_candidate(jd_id=None, client_id=7, status="Selected"), None)
        lookup.assert_called_once_with(7)
        self.assertEqual(result["steps"], steps)
        self.assertEqual(result["stage_name"], "Screening")

    def test_job_missing_client_uses_candidate_client(self) -> None:
        steps = [{"id": "s1", "name": "HR"}]
        with patch.object(hps.db, "get_client_by_id", return_value={"hiring_stages": steps}):
            result = hps.compute_effective_stage(_candidate(client_id=7, stage_id="s1"), _jd())
        self.assertEqual(result["stage_name"], "HR")

    def test_legacy_candidate_client_account_resolves_stages(self) -> None:
        steps = [{"id": "s1", "name": "HR"}]
        with patch.object(hps.db, "get_client_by_account_id", return_value={"hiring_stages": steps}) as lookup:
            result = hps.compute_effective_stage(_candidate(jd_id=None, client_account_id="KORE"), None)
        lookup.assert_called_once_with("KORE")
        self.assertEqual(result["steps"], steps)

    def test_inherits_all_client_stages_for_existing_screened_candidate(self) -> None:
        steps = [{"id": "s1", "name": "Screening"},
                 {"id": "s2", "name": "Technical Round"},
                 {"id": "s3", "name": "Offer"}, {"id": "s4", "name": "Hired"}]
        jd = {**_jd(), "client_id": 7}
        client = {"hiring_pipelines": [{"is_default": True, "stages": steps}]}
        with patch.object(hps.db, "get_client_by_id", return_value=client):
            result = hps.compute_effective_stage(_candidate(status="Selected"), jd)
            manual = hps.compute_effective_stage(_candidate(stage_id="s3"), jd)
        self.assertEqual(result["steps"], steps)
        self.assertEqual(result["stage_name"], "Screening")
        self.assertEqual(manual["stage_name"], "Offer")

    def test_job_override_takes_precedence_over_client_pipeline(self) -> None:
        steps = [{"id": "custom", "name": "Assessment"}]
        with patch.object(hps.db, "get_client_by_id") as get_client:
            result = hps.resolve_process({**_jd(steps=steps), "client_id": 7})
        self.assertEqual(result["steps"], steps)
        get_client.assert_not_called()

    def test_inherited_stages_are_available_in_stage_filter(self) -> None:
        steps = [{"id": "offer", "name": "Offer"}]
        with patch.object(hps.db, "get_all_jds", return_value=[{**_jd(), "client_id": 7}]), \
             patch.object(hps.db, "get_client_by_id", return_value={"hiring_stages": steps}):
            groups = hps.get_stage_options()
        self.assertEqual(groups[0]["steps"], steps)

    def test_unconfigured_jd_reports_not_configured(self) -> None:
        result = hps.compute_effective_stage(_candidate(), _jd(steps=[]))
        self.assertFalse(result["configured"])

    def test_configured_jd_with_no_stage_yet_is_not_started(self) -> None:
        steps = [{"id": "s1", "name": "Round 1"}]
        result = hps.compute_effective_stage(_candidate(), _jd(steps=steps))
        self.assertTrue(result["configured"])
        self.assertEqual(result["stage_name"], "Not Started")

    def test_configured_jd_resolves_stage_name(self) -> None:
        steps = [{"id": "s1", "name": "Round 1"}, {"id": "s2", "name": "Round 2"}]
        result = hps.compute_effective_stage(_candidate(stage_id="s2"), _jd(steps=steps))
        self.assertEqual(result["stage_name"], "Round 2")


class ApplyHiringEventTests(unittest.TestCase):
    def test_assessment_pass_advances_to_next_configured_round(self) -> None:
        steps = [{"id": "s1", "name": "Screening"}, {"id": "s2", "name": "Assessment"},
                 {"id": "s3", "name": "Technical Round"}, {"id": "s4", "name": "Offer"}]
        with patch.object(hps.db, "get_candidate_by_id", return_value=_candidate(stage_id="s2")), \
             patch.object(hps.db, "get_jd_by_id", return_value=_jd(steps)), \
             patch.object(hps.db, "update_candidate", return_value=True) as update:
            self.assertTrue(hps.advance_after_assessment(10, 1))
        update.assert_called_once_with(10, {"stage_id": "s3"})

    def test_assessment_does_not_override_hold_or_later_stage(self) -> None:
        steps = [{"id": "s1", "name": "Assessment"}, {"id": "s2", "name": "Interview"},
                 {"id": "s3", "name": "Offer"}]
        for candidate in (_candidate(on_hold=True), _candidate(automation_paused=True), _candidate(stage_id="s3")):
            with patch.object(hps.db, "get_candidate_by_id", return_value=candidate), \
                 patch.object(hps.db, "get_jd_by_id", return_value=_jd(steps)), \
                 patch.object(hps.db, "update_candidate") as update:
                self.assertFalse(hps.advance_after_assessment(10, 1))
            update.assert_not_called()

    def _run(self, candidate, jd, event_key):
        with patch.object(hps.db, "get_candidate_by_id", return_value=candidate), \
            patch.object(hps.db, "get_jd_by_id", return_value=jd), \
            patch.object(hps.db, "update_candidate") as update_candidate:
            applied = hps.apply_hiring_event(candidate["id"], jd["id"], event_key)
        return applied, update_candidate

    def test_moves_stage_per_mapping(self) -> None:
        steps = [{"id": "s1", "name": "Round 1"}, {"id": "s2", "name": "Round 2"}]
        jd = _jd(steps=steps, mappings={"scheduled": "s1"})
        applied, update_candidate = self._run(_candidate(), jd, "scheduled")
        self.assertTrue(applied)
        update_candidate.assert_called_once_with(10, {"stage_id": "s1"})

    def test_unmapped_event_leaves_stage_unchanged(self) -> None:
        steps = [{"id": "s1", "name": "Round 1"}]
        jd = _jd(steps=steps, mappings={})
        applied, update_candidate = self._run(_candidate(), jd, "scheduled")
        self.assertFalse(applied)
        update_candidate.assert_not_called()

    def test_on_hold_blocks_movement(self) -> None:
        steps = [{"id": "s1", "name": "Round 1"}]
        jd = _jd(steps=steps, mappings={"scheduled": "s1"})
        applied, update_candidate = self._run(_candidate(on_hold=True), jd, "scheduled")
        self.assertFalse(applied)
        update_candidate.assert_not_called()

    def test_automation_paused_blocks_movement(self) -> None:
        steps = [{"id": "s1", "name": "Round 1"}]
        jd = _jd(steps=steps, mappings={"scheduled": "s1"})
        applied, update_candidate = self._run(_candidate(automation_paused=True), jd, "scheduled")
        self.assertFalse(applied)
        update_candidate.assert_not_called()

    def test_legacy_jd_without_process_is_untouched(self) -> None:
        jd = _jd(steps=[], mappings={})
        applied, update_candidate = self._run(_candidate(), jd, "scheduled")
        self.assertFalse(applied)
        update_candidate.assert_not_called()

    def test_repeated_events_are_harmless(self) -> None:
        steps = [{"id": "s1", "name": "Round 1"}]
        jd = _jd(steps=steps, mappings={"scheduled": "s1"})
        candidate = _candidate(stage_id="s1")
        applied, update_candidate = self._run(candidate, jd, "scheduled")
        self.assertTrue(applied)
        update_candidate.assert_called_once_with(10, {"stage_id": "s1"})


if __name__ == "__main__":
    unittest.main()
