from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import candidate_service


class ParseCalendarBoundTests(unittest.TestCase):
    def test_missing_date_returns_none(self) -> None:
        self.assertIsNone(candidate_service.parse_calendar_bound("", "UTC", end_of_day=False))
        self.assertIsNone(candidate_service.parse_calendar_bound(None, "UTC", end_of_day=False))

    def test_invalid_date_returns_none(self) -> None:
        self.assertIsNone(candidate_service.parse_calendar_bound("not-a-date", "UTC", end_of_day=False))

    def test_start_and_end_of_day_bracket_the_calendar_day(self) -> None:
        start = candidate_service.parse_calendar_bound("2026-01-15", "UTC", end_of_day=False)
        end = candidate_service.parse_calendar_bound("2026-01-15", "UTC", end_of_day=True)
        self.assertEqual(start, datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc))
        self.assertTrue(end > start)
        self.assertEqual(end.date(), start.date())

    def test_unknown_timezone_falls_back_to_utc(self) -> None:
        bound = candidate_service.parse_calendar_bound("2026-01-15", "Not/A_Zone", end_of_day=False)
        self.assertEqual(bound, datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc))

    def test_timezone_shifts_the_utc_boundary(self) -> None:
        # Local midnight in a positive-offset zone is earlier the same UTC day.
        bound = candidate_service.parse_calendar_bound("2026-06-01", "Asia/Kolkata", end_of_day=False)
        self.assertEqual(bound.astimezone(timezone.utc).date().isoformat(), "2026-05-31")


class CandidateIdsWithInterviewInRangeTests(unittest.TestCase):
    def test_returns_none_when_no_bounds_given(self) -> None:
        self.assertIsNone(candidate_service.candidate_ids_with_interview_in_range(None, None))

    def test_queries_interviews_excluding_cancelled_and_collects_distinct_ids(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 31, tzinfo=timezone.utc)
        with patch.object(
            candidate_service.db,
            "get_interviews",
            return_value=[{"candidate_id": 1}, {"candidate_id": 2}, {"candidate_id": 1}],
        ) as get_interviews:
            ids = candidate_service.candidate_ids_with_interview_in_range(start, end)
        get_interviews.assert_called_once_with({"exclude_cancelled": True, "range_start": start, "range_end": end})
        self.assertEqual(sorted(ids), [1, 2])


class CandidatesPayloadStatusFilterTests(unittest.TestCase):
    """Exercise the on_hold-aware status filter without fighting normalize_candidate_record's
    own dependencies (categorization, interview lookups, etc.) — those are covered elsewhere;
    here we only need normalize_candidate_record to be a passthrough."""

    def _rows(self):
        return [
            {"id": 1, "name": "On Hold Candidate", "status": "Selected", "on_hold": True},
            {"id": 2, "name": "Active Candidate", "status": "Selected", "on_hold": False},
            {"id": 3, "name": "Rejected Candidate", "status": "Rejected", "on_hold": False},
        ]

    def test_on_hold_filters_by_flag_not_status_string(self) -> None:
        with patch.object(candidate_service.db, "get_all_candidates", return_value=self._rows()), \
            patch.object(candidate_service, "normalize_candidate_record", side_effect=lambda row, **_: row):
            rows = candidate_service.candidates_payload({"status": "on hold"})
        self.assertEqual([row["id"] for row in rows], [1])

    def test_selected_status_still_matches_literally(self) -> None:
        with patch.object(candidate_service.db, "get_all_candidates", return_value=self._rows()), \
            patch.object(candidate_service, "normalize_candidate_record", side_effect=lambda row, **_: row):
            rows = candidate_service.candidates_payload({"status": "selected"})
        self.assertEqual(sorted(row["id"] for row in rows), [1, 2])


class DeriveScreeningStatusTests(unittest.TestCase):
    def test_comparison_status_and_waitlist_precedence(self) -> None:
        candidate = {"status": "Rejected"}
        self.assertEqual(candidate_service.derive_screening_status(candidate, {"status": "sElEcTeD"}), "accepted")
        self.assertEqual(candidate_service.derive_screening_status(candidate, {"status": "rejected"}), "rejected")
        self.assertEqual(
            candidate_service.derive_screening_status(
                candidate,
                {"status": "Selected", "selection_status": "waitlisted_bench"},
            ),
            "waitlisted",
        )

    def test_candidate_status_fallback_only_without_comparison(self) -> None:
        self.assertEqual(candidate_service.derive_screening_status({"status": "Selected"}, None), "accepted")
        self.assertEqual(candidate_service.derive_screening_status({"status": "Rejected"}, None), "rejected")
        self.assertIsNone(candidate_service.derive_screening_status({"status": "Selected"}, {}))
        self.assertIsNone(candidate_service.derive_screening_status({"status": "Pending"}, None))


if __name__ == "__main__":
    unittest.main()
