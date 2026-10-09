"""Automated interview reschedule and no-show recovery.

Runs the real RecoveryService against an in-memory repository that mirrors
the Mongo repository's atomic claim / lease / unique-open-case semantics.
Calendar, messaging and record side effects are fakes: nothing is sent or booked.
"""
from __future__ import annotations

import copy
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask

from interview_recovery.config import RecoveryConfig, RecoveryConfigError, load_config
from interview_recovery.models import RecoveryStatus as S, RecoveryType
from interview_recovery.providers import DeliveryResult, MessageOutcome
from interview_recovery.service import NO_SHOW_STATUS, RecoveryConflict, RecoveryService
from interview_recovery.slots import find_slots

UTC = timezone.utc
# Thursday 2026-10-08 08:00 UTC; INTERVIEW_TIMEZONE=UTC keeps local == UTC.
T0 = datetime(2026, 10, 8, 8, 0, tzinfo=UTC)
CONFIG = RecoveryConfig(max_attempts=3, response_timeout_minutes=60, retry_delay_minutes=30,
                        max_delivery_failures=3, slot_count=3, min_notice_hours=12, no_show_grace_minutes=15)


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


class FakeRepo:
    """In-memory twin of interview_recovery.repository."""

    def __init__(self, interviews):
        self.interviews = {i["id"]: i for i in interviews}
        self.cases: dict[int, dict] = {}
        self.attempts: list[dict] = []
        self.locks: dict[str, tuple[str, datetime]] = {}

    def create_case(self, doc):
        for case in self.cases.values():
            if case["is_open"] and case["interview_id"] == doc["interview_id"] and case["recovery_type"] == doc["recovery_type"]:
                return copy.deepcopy(case), False
        case = {**copy.deepcopy(doc), "id": len(self.cases) + 1, "is_open": True}
        self.cases[case["id"]] = case
        return copy.deepcopy(case), True

    def get_case(self, case_id):
        return copy.deepcopy(self.cases.get(int(case_id)))

    def get_open_case(self, interview_id, recovery_type=None):
        rows = [c for c in self.cases.values() if c["interview_id"] == interview_id and c["is_open"]
                and (recovery_type is None or c["recovery_type"] == recovery_type)]
        return copy.deepcopy(rows[-1]) if rows else None

    def case_exists_for_occurrence(self, interview_id, recovery_type, start):
        return any(c["interview_id"] == interview_id and c["recovery_type"] == recovery_type
                   and c["original_interview_start"] == start for c in self.cases.values())

    def latest_cases_for_interviews(self, ids):
        out = {}
        for case in self.cases.values():
            if case["interview_id"] in ids:
                out[case["interview_id"]] = copy.deepcopy(case)
        return out

    def list_cases(self, *, recruiter_id=None, statuses=None, limit=100):
        return [copy.deepcopy(c) for c in self.cases.values()
                if (recruiter_id is None or c["recruiter_id"] == recruiter_id) and (not statuses or c["status"] in statuses)]

    def update_case(self, case_id, patch, *, expected_status=None):
        case = self.cases.get(int(case_id))
        if not case or (expected_status and case["status"] != expected_status):
            return False
        case.update(copy.deepcopy(patch))
        if "status" in patch:
            case["is_open"] = patch["status"] in S.OPEN
        return True

    def _claim(self, case, now, lease):
        case["resume_from"] = case.get("resume_from") if case["status"] == S.PROCESSING else case["status"]
        case["status"] = S.PROCESSING
        case["is_open"] = True
        case["lease_until"] = now + timedelta(seconds=lease)
        return copy.deepcopy(case)

    def claim_case(self, case_id, from_statuses, now, lease):
        case = self.cases.get(int(case_id))
        if not case or case["status"] not in from_statuses:
            return None
        return self._claim(case, now, lease)

    def claim_next_due_case(self, now, lease):
        for case in sorted(self.cases.values(), key=lambda c: c["id"]):
            st = case["status"]
            if ((st in {S.PENDING, S.RETRY_SCHEDULED} and case.get("next_action_at") and case["next_action_at"] <= now)
                    or (st in {S.AWAITING_RESPONSE, S.SLOT_PROPOSED} and case.get("response_deadline") and case["response_deadline"] <= now)
                    or (st == S.PROCESSING and case.get("lease_until") and case["lease_until"] <= now)):
                return self._claim(case, now, lease)
        return None

    def mark_escalated(self, case_id, now, reason, action):
        case = self.cases[int(case_id)]
        if case.get("escalated_at") is not None:
            return False
        case.update(status=S.ESCALATED, is_open=True, escalated_at=now, escalation_reason=reason,
                    recommended_action=action, next_action_at=None, response_deadline=None, lease_until=None)
        return True

    def add_attempt(self, doc):
        self.attempts.append({**copy.deepcopy(doc), "id": len(self.attempts) + 1, "created_at": T0})
        return len(self.attempts)

    def list_attempts(self, case_id):
        return [copy.deepcopy(a) for a in self.attempts if a["case_id"] == case_id]

    def set_interview_fields(self, interview_id, fields):
        self.interviews[interview_id].update(fields)
        return True

    def find_interview_by_token(self, token):
        return next((copy.deepcopy(i) for i in self.interviews.values() if i.get("candidate_access_token") == token), None)

    def raw_interview(self, interview_id):
        return copy.deepcopy(self.interviews.get(interview_id))

    def interviews_due_for_no_show_check(self, start, end, statuses):
        return [copy.deepcopy(i) for i in self.interviews.values()
                if i["status"] in statuses and start <= i["interview_start"] <= end and i.get("attendance_status") != "attended"]

    def acquire_lock(self, key, owner, now, seconds):
        held = self.locks.get(key)
        if held and held[1] > now and held[0] != owner:
            return False
        self.locks[key] = (owner, now + timedelta(seconds=seconds))
        return True

    def release_lock(self, key, owner):
        if self.locks.get(key, (None,))[0] == owner:
            del self.locks[key]


class FakeCalendar:
    name = "fake"

    def __init__(self, repo):
        self.repo = repo
        self.extra_busy: list[tuple[datetime, datetime]] = []
        self.updated = []

    def busy_intervals(self, recruiter_id, start, end, exclude_interview_id=None):
        busy = [(i["interview_start"], i["interview_end"]) for i in self.repo.interviews.values()
                if i["recruiter_id"] == recruiter_id and i["id"] != exclude_interview_id
                and i["status"] in {"Scheduled", "Rescheduled"}]
        return busy + list(self.extra_busy)

    def update_event(self, interview, start, end):
        self.updated.append((interview["id"], start))
        return {"status": "not_configured"}


class FakeMessenger:
    def __init__(self):
        self.candidate: list[dict] = []
        self.recruiter: list[dict] = []
        self.fail_with: DeliveryResult | None = None

    def send_candidate(self, interview, subject, body, sms_body=""):
        self.candidate.append({"subject": subject, "body": body})
        if self.fail_with:
            return MessageOutcome([self.fail_with])
        return MessageOutcome([DeliveryResult("email", "sent")])

    def send_recruiter(self, interview, subject, body):
        self.recruiter.append({"subject": subject, "body": body})
        return MessageOutcome([DeliveryResult("email", "sent")])


class FakeGateway:
    def __init__(self, repo):
        self.repo = repo
        self.notifications: list[str] = []

    def slot_available(self, recruiter_id, start, end, exclude_interview_id):
        return not any(i["recruiter_id"] == recruiter_id and i["id"] != exclude_interview_id
                       and i["status"] in {"Scheduled", "Rescheduled"} and start < i["interview_end"] and end > i["interview_start"]
                       for i in self.repo.interviews.values())

    def candidate_busy(self, candidate_id, start, end, exclude_interview_id):
        return []

    def reschedule(self, interview, start, end):
        self.repo.interviews[interview["id"]].update(interview_start=start, interview_end=end, status="Rescheduled")

    def mark_no_show(self, interview):
        self.repo.interviews[interview["id"]]["status"] = NO_SHOW_STATUS

    def notify(self, interview, title, message):
        self.notifications.append(title)

    def public_link(self, token):
        return f"https://hr.example.com/interview/{token}"


def interview(**over):
    base = {"id": 1, "candidate_id": 10, "recruiter_id": 7, "jd_id": 3, "candidate_name": "Asha Rao",
            "job_role": "QA Engineer", "to_email": "asha@example.com", "recruiter_email": "rec@example.com",
            "interviewer": "Ravi", "interview_start": datetime(2026, 10, 9, 10, 0),
            "interview_end": datetime(2026, 10, 9, 11, 0), "status": "Scheduled",
            "candidate_access_token": str(uuid.uuid4())}
    base.update(over)
    return base


class RecoveryTestBase(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(T0)
        self.repo = FakeRepo([interview()])
        self.calendar = FakeCalendar(self.repo)
        self.messenger = FakeMessenger()
        self.gateway = FakeGateway(self.repo)
        self.svc = self.make_service(CONFIG)

    def make_service(self, config):
        return RecoveryService(repo=self.repo, calendar=self.calendar, messenger=self.messenger,
                               gateway=self.gateway, config=config, clock=self.clock)

    @property
    def token(self):
        return self.repo.interviews[1]["candidate_access_token"]

    def case(self, case_id=1):
        return self.repo.cases[case_id]

    def actions(self, case_id=1):
        return [a["action"] for a in self.repo.attempts if a["case_id"] == case_id]


class RescheduleTests(RecoveryTestBase):
    def test_request_triggers_slot_search_and_sends_options_without_recruiter(self):
        view = self.svc.request_reschedule(1, source="candidate_portal", reason="Exam clash")
        self.assertEqual(view["status"], S.SLOT_PROPOSED)
        self.assertEqual(len(view["proposed_slots"]), 3)
        self.assertEqual(len(self.messenger.candidate), 1)
        self.assertIn(view["proposed_slots"][0]["label"], self.messenger.candidate[0]["body"])
        self.assertEqual(self.messenger.recruiter, [])
        # 12h notice from 08:00 Thu: earliest is Thu 20:00 -> outside hours -> Friday onward, one per day.
        days = {s["id"][:10] for s in view["proposed_slots"]}
        self.assertEqual(len(days), 3)
        self.assertNotIn("2026-10-10", days)  # Saturday is not a workday

    def test_candidate_selection_updates_existing_interview(self):
        view = self.svc.request_reschedule(1, source="candidate_portal")
        chosen = view["proposed_slots"][1]
        result = self.svc.public_confirm_slot(self.token, chosen["id"])
        self.assertTrue(result["booked"])
        self.assertEqual(self.repo.interviews[1]["interview_start"], datetime.fromisoformat(chosen["start"]))
        self.assertEqual(self.repo.interviews[1]["status"], "Rescheduled")
        self.assertEqual(len(self.repo.interviews), 1)  # updated, not duplicated
        self.assertEqual(self.case()["status"], S.RESCHEDULED)
        self.assertIn("Interview rescheduled automatically", self.gateway.notifications)
        self.assertEqual(self.calendar.updated, [(1, datetime.fromisoformat(chosen["start"]))])

    def test_slot_taken_meanwhile_is_not_booked_and_new_options_are_offered(self):
        view = self.svc.request_reschedule(1, source="candidate_portal")
        chosen = view["proposed_slots"][0]
        start = datetime.fromisoformat(chosen["start"])
        self.repo.interviews[2] = interview(id=2, candidate_id=11, interview_start=start,
                                            interview_end=start + timedelta(hours=1), candidate_access_token=None)
        result = self.svc.public_confirm_slot(self.token, chosen["id"])
        self.assertFalse(result["booked"])
        self.assertTrue(result["slot_unavailable"])
        self.assertEqual(self.repo.interviews[1]["interview_start"], datetime(2026, 10, 9, 10, 0))
        self.assertNotIn(chosen["id"], [s["id"] for s in self.case()["proposed_slots"]])
        self.assertEqual(self.case()["status"], S.SLOT_PROPOSED)
        self.assertEqual(self.case()["attempt_count"], 1)  # a conflict is not the candidate's fault

    def test_duplicate_requests_and_confirmations_do_not_duplicate(self):
        self.svc.request_reschedule(1, source="candidate_portal")
        self.svc.request_reschedule(1, source="candidate_portal")
        self.assertEqual(len(self.repo.cases), 1)
        self.assertEqual(len(self.messenger.candidate), 1)
        chosen = self.case()["proposed_slots"][0]["id"]
        self.svc.public_confirm_slot(self.token, chosen)
        sent = len(self.messenger.candidate)
        again = self.svc.public_confirm_slot(self.token, chosen)
        self.assertTrue(again["booked"])
        self.assertEqual(len(self.messenger.candidate), sent)
        self.assertEqual(self.actions().count("booked"), 1)

    def test_preferred_windows_limit_slots(self):
        windows = [{"date": "2026-10-13", "start": "14:00", "end": "16:00"}]
        view = self.svc.request_reschedule(1, source="candidate_portal", preferred_windows=windows)
        self.assertTrue(view["proposed_slots"])
        self.assertTrue(all(s["id"].startswith("2026-10-13T14") or s["id"].startswith("2026-10-13T15:00")
                            for s in view["proposed_slots"]))

    def test_no_slots_retries_then_escalates_once(self):
        self.calendar.extra_busy.append((datetime(2026, 10, 1), datetime(2026, 12, 1)))
        view = self.svc.request_reschedule(1, source="recruiter_logged")
        self.assertEqual(view["status"], S.RETRY_SCHEDULED)
        for _ in range(5):
            self.clock.advance(minutes=31)
            self.svc.run_due()
        self.assertEqual(self.case()["status"], S.ESCALATED)
        self.assertEqual(self.case()["attempt_count"], 3)
        self.assertEqual(len(self.messenger.recruiter), 1)
        self.assertEqual(self.gateway.notifications.count("Interview recovery needs your attention"), 1)
        self.assertIn("Attempt history", self.messenger.recruiter[0]["body"])

    def test_manual_reschedule_elsewhere_stops_automation(self):
        self.svc.request_reschedule(1, source="candidate_portal")
        self.repo.interviews[1]["interview_start"] = datetime(2026, 10, 20, 10, 0)
        self.clock.advance(minutes=61)
        self.svc.run_due()
        self.assertEqual(self.case()["status"], S.CLOSED)
        self.assertEqual(self.case()["outcome"], "rescheduled_elsewhere")
        self.assertEqual(len(self.messenger.candidate), 1)

    def test_cancelled_interview_cannot_be_rescheduled_automatically(self):
        self.repo.interviews[1]["status"] = "Cancelled"
        with self.assertRaises(RecoveryConflict):
            self.svc.request_reschedule(1, source="candidate_portal")


class NoShowTests(RecoveryTestBase):
    def setUp(self):
        super().setUp()
        self.clock.now = datetime(2026, 10, 9, 10, 20, tzinfo=UTC)  # 20 min after the 10:00 start
        self.auto = self.make_service(RecoveryConfig(**{**CONFIG.__dict__, "no_show_mode": "auto"}))

    def test_genuine_no_show_triggers_automatic_outreach(self):
        result = self.auto.run_due()
        self.assertEqual(result["detected_no_shows"], 1)
        self.assertEqual(self.repo.interviews[1]["status"], NO_SHOW_STATUS)
        self.assertEqual(self.case()["recovery_type"], RecoveryType.NO_SHOW)
        self.assertEqual(self.case()["status"], S.AWAITING_RESPONSE)
        self.assertIn("We missed you", self.messenger.candidate[0]["subject"])

    def test_detection_is_idempotent(self):
        for _ in range(4):
            self.auto.run_due()
        self.assertEqual(len(self.repo.cases), 1)
        self.assertEqual(len(self.messenger.candidate), 1)

    def test_grace_period_is_respected(self):
        self.clock.now = datetime(2026, 10, 9, 10, 10, tzinfo=UTC)
        self.assertEqual(self.auto.run_due()["detected_no_shows"], 0)
        with self.assertRaises(RecoveryConflict):
            self.svc.report_attendance(1, "no_show", actor="rec")

    def test_cancelled_completed_rescheduled_or_attended_are_not_no_shows(self):
        for status, attendance in [("Cancelled", None), ("Client Interview Pending", None),
                                   ("Rejected After Interview", None), ("Scheduled", "attended")]:
            self.repo.interviews[1].update(status=status, attendance_status=attendance)
            self.assertEqual(self.auto.run_due()["detected_no_shows"], 0, status)
        self.repo.interviews[1].update(status="Rescheduled", attendance_status=None,
                                       interview_start=datetime(2026, 10, 12, 10, 0), interview_end=datetime(2026, 10, 12, 11, 0))
        self.assertEqual(self.auto.run_due()["detected_no_shows"], 0)
        self.assertEqual(self.repo.cases, {})
        self.assertEqual(self.messenger.candidate, [])

    def test_confirmed_mode_only_acts_on_recruiter_confirmation(self):
        self.assertEqual(self.svc.run_due()["detected_no_shows"], 0)
        result = self.svc.report_attendance(1, "no_show", actor="rec")
        self.assertEqual(result["case"]["status"], S.AWAITING_RESPONSE)
        self.svc.report_attendance(1, "no_show", actor="rec")
        self.assertEqual(len(self.repo.cases), 1)

    def test_candidate_yes_resumes_into_rescheduling_and_recovers(self):
        self.auto.run_due()
        view = self.auto.public_respond(self.token, True)
        self.assertEqual(view["case"]["status"], S.SLOT_PROPOSED)
        slot = view["case"]["proposed_slots"][0]
        booked = self.auto.public_confirm_slot(self.token, slot["id"])
        self.assertTrue(booked["booked"])
        self.assertEqual(self.case()["status"], S.RECOVERED)
        self.assertEqual(self.repo.interviews[1]["status"], "Rescheduled")
        self.assertIsNone(self.repo.interviews[1]["attendance_status"])

    def test_candidate_no_closes_case_and_informs_recruiter(self):
        self.auto.run_due()
        self.auto.public_respond(self.token, False)
        self.assertEqual(self.case()["status"], S.CLOSED)
        self.assertEqual(self.case()["outcome"], "candidate_declined")
        self.assertIn("Candidate withdrew from interview", self.gateway.notifications)

    def test_no_response_retries_then_escalates_exactly_once(self):
        self.auto.run_due()
        for _ in range(6):
            self.clock.advance(minutes=61)
            self.auto.run_due()
        self.assertEqual(len(self.messenger.candidate), 3)  # initial + 2 reminders = max_attempts
        self.assertEqual(self.case()["status"], S.ESCALATED)
        self.assertEqual(len(self.messenger.recruiter), 1)
        self.assertEqual(self.actions().count("escalated"), 1)
        self.assertEqual(self.actions().count("response_timeout"), 3)

    def test_attended_correction_closes_open_case(self):
        self.auto.run_due()
        self.auto.report_attendance(1, "attended", actor="rec")
        self.assertEqual(self.case()["status"], S.CLOSED)
        self.assertEqual(self.case()["outcome"], "attendance_corrected")


class FailureHandlingTests(RecoveryTestBase):
    def test_transient_delivery_failure_retries_without_using_attempts(self):
        self.messenger.fail_with = DeliveryResult("email", "failed", error="SMTP timeout", transient=True)
        self.svc.request_reschedule(1, source="recruiter_logged")
        self.assertEqual(self.case()["status"], S.RETRY_SCHEDULED)
        self.assertEqual(self.case()["attempt_count"], 0)
        self.assertEqual(self.case()["delivery_failure_count"], 1)
        self.assertIn("SMTP timeout", self.case()["last_error"])
        self.messenger.fail_with = None
        self.clock.advance(minutes=31)
        self.svc.run_due()
        self.assertEqual(self.case()["status"], S.SLOT_PROPOSED)
        self.assertEqual(self.case()["attempt_count"], 1)

    def test_repeated_transient_failures_escalate(self):
        self.messenger.fail_with = DeliveryResult("email", "failed", error="SMTP timeout", transient=True)
        self.svc.request_reschedule(1, source="recruiter_logged")
        for _ in range(6):
            self.clock.advance(hours=3)
            self.svc.run_due()
        self.assertEqual(self.case()["status"], S.ESCALATED)
        self.assertEqual(self.case()["attempt_count"], 0)
        self.assertEqual(len(self.messenger.recruiter), 1)

    def test_permanent_failure_escalates_immediately(self):
        self.messenger.fail_with = DeliveryResult("email", "failed", error="SMTP credentials are not configured.")
        self.svc.request_reschedule(1, source="recruiter_logged")
        self.assertEqual(self.case()["status"], S.ESCALATED)
        self.assertIn("could not be contacted", self.case()["escalation_reason"])

    def test_calendar_error_is_recorded_and_retried(self):
        with patch.object(self.calendar, "busy_intervals", side_effect=RuntimeError("calendar API 503")):
            self.svc.request_reschedule(1, source="recruiter_logged")
        self.assertEqual(self.case()["status"], S.RETRY_SCHEDULED)
        self.assertIn("calendar API 503", self.case()["last_error"])
        self.assertIn("error", self.actions())
        self.clock.advance(minutes=31)
        self.svc.run_due()
        self.assertEqual(self.case()["status"], S.SLOT_PROPOSED)

    def test_case_survives_worker_restart(self):
        self.svc.request_reschedule(1, source="candidate_portal")
        # Simulate a worker that claimed the timed-out case and then died.
        self.clock.advance(minutes=61)
        claimed = self.repo.claim_next_due_case(self.clock(), CONFIG.lease_seconds)
        self.assertEqual(claimed["status"], S.PROCESSING)
        restarted = self.make_service(CONFIG)  # fresh process, same persisted state
        self.assertEqual(restarted.run_due()["processed"], 0)  # lease still held
        self.clock.advance(seconds=CONFIG.lease_seconds + 1)
        restarted.run_due()
        self.assertEqual(self.case()["status"], S.SLOT_PROPOSED)
        self.assertEqual(self.case()["attempt_count"], 2)

    def test_crash_after_booking_is_finished_not_rebooked(self):
        view = self.svc.request_reschedule(1, source="candidate_portal")
        slot = view["proposed_slots"][0]
        self.repo.claim_case(1, {S.SLOT_PROPOSED}, self.clock(), CONFIG.lease_seconds)
        self.repo.update_case(1, {"selected_slot": slot})
        self.gateway.reschedule(self.repo.interviews[1], datetime.fromisoformat(slot["start"]), datetime.fromisoformat(slot["end"]))
        self.clock.advance(seconds=CONFIG.lease_seconds + 1)
        self.svc.run_due()
        self.assertEqual(self.case()["status"], S.RESCHEDULED)
        self.assertEqual(self.case()["confirmed_slot"]["id"], slot["id"])

    def test_manual_retry_resets_and_allows_one_new_escalation(self):
        self.messenger.fail_with = DeliveryResult("email", "failed", error="Candidate email is missing.")
        self.svc.request_reschedule(1, source="recruiter_logged")
        self.assertEqual(self.case()["status"], S.ESCALATED)
        with self.assertRaises(Exception):
            self.svc.retry_case(1, recruiter_id=99, actor="other")
        self.messenger.fail_with = None
        view = self.svc.retry_case(1, recruiter_id=7, actor="rec")
        self.assertEqual(view["status"], S.SLOT_PROPOSED)
        self.assertEqual(len(self.messenger.recruiter), 1)

    def test_disabled_feature_does_nothing(self):
        off = self.make_service(RecoveryConfig(**{**CONFIG.__dict__, "enabled": False}))
        self.assertEqual(off.run_due(), {"enabled": False, "detected_no_shows": 0, "processed": 0})
        with self.assertRaises(Exception):
            off.request_reschedule(1, source="candidate_portal")


class SlotAndConfigTests(unittest.TestCase):
    def test_slot_search_respects_hours_duration_and_busy(self):
        busy = [(datetime(2026, 10, 9, 9, 0), datetime(2026, 10, 9, 18, 0))]
        slots = find_slots(CONFIG, datetime(2026, 10, 8, 8, 0), timedelta(minutes=90), busy)
        self.assertTrue(slots)
        for slot in slots:
            start, end = datetime.fromisoformat(slot["start"]), datetime.fromisoformat(slot["end"])
            self.assertEqual(end - start, timedelta(minutes=90))
            self.assertGreaterEqual(start.hour, 9)
            self.assertLessEqual(end, start.replace(hour=18, minute=0))
            self.assertNotEqual(start.date().isoformat(), "2026-10-09")

    def test_config_validation(self):
        with patch.dict("os.environ", {"INTERVIEW_RECOVERY_MAX_ATTEMPTS": "0"}):
            with self.assertRaises(RecoveryConfigError):
                load_config()
        with patch.dict("os.environ", {"INTERVIEW_TIMEZONE": "Mars/Base"}):
            with self.assertRaises(RecoveryConfigError):
                load_config()
        with patch.dict("os.environ", {"INTERVIEW_RECOVERY_MAX_ATTEMPTS": "5", "INTERVIEW_TIMEZONE": "Asia/Kolkata",
                                       "INTERVIEW_RECOVERY_ENABLED": "false"}):
            cfg = load_config()
        self.assertEqual((cfg.max_attempts, cfg.timezone, cfg.enabled), (5, "Asia/Kolkata", False))


class RouteAuthorizationTests(RecoveryTestBase):
    def setUp(self):
        super().setUp()
        from routes import interview_recovery_routes as routes

        self.routes = routes
        app = Flask(__name__)
        app.register_blueprint(routes.interview_recovery_bp)
        self.client = app.test_client()
        self.patches = [
            patch.object(routes, "get_service", return_value=self.svc),
            patch("services.auth_service.effective_user_id", return_value=99),
            patch.object(routes, "current_user", return_value={"id": 99, "username": "other"}),
            patch.object(routes.db, "get_interview_by_id", side_effect=lambda i: self.repo.raw_interview(i)),
        ]
        for p in self.patches:
            p.start()
        self.svc.request_reschedule(1, source="candidate_portal")

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def test_other_recruiter_cannot_read_or_manipulate_case(self):
        self.assertEqual(self.client.get("/api/interview-recovery/cases/1").status_code, 404)
        self.assertEqual(self.client.post("/api/interview-recovery/cases/1/retry").status_code, 404)
        self.assertEqual(self.client.post("/api/interview-recovery/cases/1/close").status_code, 404)
        self.assertEqual(self.client.post("/api/interviews/1/attendance", json={"attendance": "no_show"}).status_code, 404)
        self.assertEqual(self.client.get("/api/interview-recovery/cases").get_json()["cases"], [])

    def test_owner_can_view_history(self):
        with patch.object(self.routes, "current_user", return_value={"id": 7, "username": "rec"}):
            body = self.client.get("/api/interview-recovery/cases/1").get_json()
        self.assertEqual(body["case"]["status"], S.SLOT_PROPOSED)
        self.assertIn("slots_offered", [h["action"] for h in body["case"]["history"]])

    def test_public_token_endpoints_hide_internal_data(self):
        body = self.client.get(f"/api/interview-recovery/public/{self.token}").get_json()
        self.assertEqual(body["candidate_first_name"], "Asha")
        flat = str(body)
        for secret in ("asha@example.com", "rec@example.com", "recruiter_id", "candidate_access_token"):
            self.assertNotIn(secret, flat)
        self.assertEqual(self.client.get(f"/api/interview-recovery/public/{uuid.uuid4()}").status_code, 404)
        self.assertEqual(self.client.get("/api/interview-recovery/public/not-a-token").status_code, 404)

    def test_scheduler_endpoint_requires_secret(self):
        with patch.dict("os.environ", {"INTERVIEW_RECOVERY_CRON_SECRET": "s3cret"}):
            self.assertEqual(self.client.get("/api/interview-recovery/run").status_code, 401)
            ok = self.client.get("/api/interview-recovery/run", headers={"Authorization": "Bearer s3cret"})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.get_json()["enabled"])


if __name__ == "__main__":
    unittest.main()
