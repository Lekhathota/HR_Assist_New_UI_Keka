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
