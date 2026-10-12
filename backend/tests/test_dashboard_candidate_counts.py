from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.report_service import _metrics_with_normalized_candidates


class DashboardCandidateCountsTests(unittest.TestCase):
    def test_repeated_job_submissions_count_people_instead_of_applications(self):
        rows = []
        for index in range(5):
            rows.extend([
                {"id": index * 2, "email": f"Person{index}@example.com ", "status": "Rejected"},
                {"id": index * 2 + 1, "email": f"person{index}@example.com", "status": "Selected"},
            ])
        metrics = _metrics_with_normalized_candidates(
            {"selected_candidates": 10, "rejected_candidates": 10}, rows
        )
        self.assertEqual(metrics["total_candidates"], 5)
        self.assertEqual(metrics["screened_candidates"], 5)
        self.assertEqual(metrics["selected_candidates"], 5)
        self.assertEqual(metrics["rejected_candidates"], 0)
        self.assertEqual(metrics["pending_candidates"], 0)

    def test_pending_people_and_missing_contacts_are_not_screening_decisions(self):
        rows = [
            {"id": 1, "phone": "123", "status": "Pending"},
            {"id": 2, "phone": "123", "status": "Rejected"},
            {"id": 3, "name": "Alex", "status": "Pending"},
            {"id": 4, "name": "Alex", "status": "Pending"},
            {"id": 5, "structured_data": {"email": "person@example.com"}, "status": "Pending",
             "_screening_comparison": {"selection_status": "accepted_vendor"}},
        ]
        metrics = _metrics_with_normalized_candidates({}, rows)
        self.assertEqual(metrics["total_candidates"], 4)
        self.assertEqual(metrics["screened_candidates"], 2)
        self.assertEqual(metrics["pending_candidates"], 2)

    def test_empty_pool_overrides_old_operational_totals(self):
        metrics = _metrics_with_normalized_candidates({"selected_candidates": 10}, [])
        self.assertEqual(metrics["total_candidates"], 0)
        self.assertEqual(metrics["screened_candidates"], 0)
        self.assertEqual(metrics["selection_rate"], 0)


if __name__ == "__main__":
    unittest.main()
