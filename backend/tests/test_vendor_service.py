from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import vendor_service


class VendorServiceTests(unittest.TestCase):
    def test_create_vendor_normalizes_email(self) -> None:
        with patch.object(vendor_service.db, "get_vendor_by_email", return_value=None), \
            patch.object(vendor_service.db, "create_vendor", return_value=7) as create_vendor, \
            patch.object(vendor_service.db, "get_vendor_by_id", return_value={"id": 7, "email": "Partner@Example.com"}):
            vendor = vendor_service.create_vendor(
                {
                    "vendor_name": "Partner",
                    "company_name": "Partner Co",
                    "email": " Partner@Example.com ",
                    "supported_categories": "Backend, QA",
                }
            )

        self.assertEqual(vendor["id"], 7)
        self.assertEqual(create_vendor.call_args.args[0]["email"], "Partner@Example.com")
        self.assertEqual(create_vendor.call_args.args[0]["email_normalized"], "partner@example.com")
        self.assertEqual(create_vendor.call_args.args[0]["supported_categories"], ["Backend", "QA"])

    def test_create_vendor_rejects_invalid_email(self) -> None:
        with self.assertRaises(vendor_service.VendorServiceError):
            vendor_service.create_vendor({"vendor_name": "Bad Vendor", "email": "not-an-email"})

    def test_create_vendor_rejects_duplicate_email(self) -> None:
        with patch.object(vendor_service.db, "get_vendor_by_email", return_value={"id": 1}):
            with self.assertRaises(vendor_service.VendorServiceError):
                vendor_service.create_vendor({"vendor_name": "Partner", "email": "partner@example.com"})

    def test_delete_vendor_uses_soft_delete(self) -> None:
        with patch.object(vendor_service.db, "soft_delete_vendor", return_value=True) as soft_delete:
            vendor_service.delete_vendor(12)
        soft_delete.assert_called_once_with(12)

    def test_assign_vendors_validates_active_vendors(self) -> None:
        with patch.object(vendor_service.db, "get_jd_by_id", return_value={"id": 3}), \
            patch.object(vendor_service.db, "get_vendor_by_id", side_effect=[
                {"id": 4, "status": "Active"},
                {"id": 5, "status": "Active"},
            ]), \
            patch.object(vendor_service.db, "assign_vendors_to_jd", return_value=[{"id": 4}, {"id": 5}]) as assign:
            result = vendor_service.assign_vendors(3, [4, 5, 5], {"id": 9, "username": "recruiter"})

        self.assertEqual(len(result), 2)
        assign.assert_called_once_with(3, [4, 5], assigned_by=9, assigned_by_username="recruiter")

    def test_assign_vendors_rejects_inactive_vendor(self) -> None:
        with patch.object(vendor_service.db, "get_jd_by_id", return_value={"id": 3}), \
            patch.object(vendor_service.db, "get_vendor_by_id", return_value={"id": 4, "status": "Inactive"}):
            with self.assertRaises(vendor_service.VendorServiceError):
                vendor_service.assign_vendors(3, [4], {"id": 9})

    def test_remove_assignment_raises_when_missing(self) -> None:
        with patch.object(vendor_service.db, "remove_vendor_assignment", return_value=False):
            with self.assertRaises(vendor_service.VendorServiceError):
                vendor_service.remove_assignment(3, 4)

    def test_vendor_jds_marks_assigned_jobs(self) -> None:
        with patch.object(vendor_service.db, "get_vendor_by_id", return_value={"id": 4, "status": "Active"}), \
            patch.object(vendor_service.db, "get_vendor_jd_assignments", return_value=[{"jd_id": 2}]), \
            patch.object(vendor_service.db, "get_all_jds", return_value=[
                {"id": 1, "title": "Python", "client_name": "Client A", "location": "Remote", "status": "Active"},
                {"id": 2, "title": "React", "client_name": "Client B", "location": "Hyd", "status": "Active"},
            ]):
            payload = vendor_service.vendor_jds(4)

        self.assertEqual(payload["assigned_jd_ids"], [2])
        self.assertFalse(payload["jobs"][0]["assigned"])
        self.assertTrue(payload["jobs"][1]["assigned"])

    def test_assign_jds_to_vendor_preserves_vendor_context(self) -> None:
        with patch.object(vendor_service.db, "get_vendor_by_id", return_value={"id": 4, "status": "Active"}), \
            patch.object(vendor_service.db, "get_jd_by_id", side_effect=[{"id": 1}, {"id": 2}]), \
            patch.object(vendor_service.db, "assign_jds_to_vendor", return_value=[] ) as assign, \
            patch.object(vendor_service, "vendor_jds", return_value={"vendor": {"id": 4}, "jobs": [], "assigned_jd_ids": [1, 2]}) as vendor_jds:
            payload = vendor_service.assign_jds_to_vendor(4, [1, 2, 2], {"id": 9, "username": "recruiter"})

        self.assertEqual(payload["assigned_jd_ids"], [1, 2])
        assign.assert_called_once_with(4, [1, 2], assigned_by=9, assigned_by_username="recruiter")
        vendor_jds.assert_called_once_with(4)

    def test_send_vendor_email_logs_failed_attempt(self) -> None:
        assignment = {"id": 20}
        with patch.object(vendor_service, "generate_vendor_email", return_value={
            "from_email": "hr@example.com",
            "to_email": "vendor@example.com",
            "subject": "JD Requirement: Role",
            "body": "Body",
        }), \
            patch.object(vendor_service.db, "get_active_jd_vendor_assignment", return_value=assignment), \
            patch.object(vendor_service.db, "count_vendor_email_attempts", return_value=2), \
            patch.object(vendor_service.db, "_now", return_value="now"), \
            patch.object(vendor_service, "send_email", side_effect=RuntimeError("SMTP missing")), \
            patch.object(vendor_service.db, "create_vendor_email_log", return_value=31) as create_log, \
            patch.object(vendor_service.db, "update_vendor_assignment_email_status") as update_status:
            with self.assertRaises(vendor_service.VendorServiceError):
                vendor_service.send_vendor_email(3, 4, {}, {"id": 9, "username": "recruiter"})

        self.assertEqual(create_log.call_args.args[0]["status"], "failed")
        self.assertEqual(create_log.call_args.args[0]["retry_count"], 2)
        update_status.assert_called_once_with(20, "failed", 31, "now")


if __name__ == "__main__":
    unittest.main()
