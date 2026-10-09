"""Automated interview reschedule and no-show recovery.

Workflow (see docs/interview_recovery.md for the full description):

  reschedule request ──► PENDING ──► search slots ──► SLOT_PROPOSED ──► candidate picks ──► RESCHEDULED
  no-show            ──► PENDING ──► outreach     ──► AWAITING_RESPONSE ──► "yes" ──► SLOT_PROPOSED ──► RECOVERED
                                                                         └─► "no"  ──► CLOSED
  no slots / no reply / delivery failure ──► RETRY_SCHEDULED ──► ... ──► ESCALATED (recruiter, exactly once)

Attempts count candidate-facing rounds (an offer or reminder that was
delivered, or a slot search that found nothing). Technical delivery
failures and worker errors are counted separately and never consume the
candidate's attempts.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import database as db
from interview_recovery import repository as default_repo
from interview_recovery.config import RecoveryConfig, load_config
from interview_recovery.models import (
    ACTIVE_INTERVIEW_STATUSES,
    ATTENDANCE_ATTENDED,
    ATTENDANCE_NO_SHOW,
    ATTENDANCE_VALUES,
    AttemptOutcome,
    RecoveryStatus,
    RecoveryType,
    interview_is_active,
)
from interview_recovery.providers import (
    CalendarProvider,
    DeliveryResult,
    MessageOutcome,
    Messenger,
    get_calendar_provider,
)
from interview_recovery.slots import find_slots, parse_preferred_windows, slot_id

logger = logging.getLogger("recruitment.interview_recovery")

NO_SHOW_STATUS = "No Show"
STAGE_CONSENT = "awaiting_consent"
STAGE_SLOTS = "slot_selection"
ACTOR = "interview-recovery"


class RecoveryError(ValueError):
    status_code = 400


class RecoveryNotFound(RecoveryError):
    status_code = 404


class RecoveryConflict(RecoveryError):
    status_code = 409


class RecoveryDisabled(RecoveryError):
    status_code = 503


def _naive(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_iso(v) for v in value]
    if isinstance(value, dict):
        return {k: _iso(v) for k, v in value.items()}
    return value


class InterviewGateway:
    """Side effects on existing HR Assist records. Tests substitute a fake."""

    def slot_available(self, recruiter_id: int, start: datetime, end: datetime, exclude_interview_id: int) -> bool:
        return db.recruiter_slot_is_available(recruiter_id, start, end, exclude_interview_id)

    def candidate_busy(self, candidate_id: int, start: datetime, end: datetime, exclude_interview_id: int):
        rows = db.get_interviews({"candidate_id": candidate_id, "range_start": start, "range_end": end,
                                  "exclude_cancelled": True})
        busy = []
        for row in rows:
            if int(row.get("id") or 0) == int(exclude_interview_id) or row.get("status") not in ACTIVE_INTERVIEW_STATUSES:
                continue
            row_start, row_end = _naive(row.get("interview_start")), _naive(row.get("interview_end"))
            if row_start and row_end:
                busy.append((row_start, row_end))
        return busy

    def reschedule(self, interview: dict, start: datetime, end: datetime) -> None:
        interview_id = int(interview["id"])
        candidate_id = int(interview.get("candidate_id") or 0)
        db.update_interview(interview_id, {"interview_start": start, "interview_end": end, "status": "Rescheduled"})
        if candidate_id:
            db.update_candidate(candidate_id, {"hiring_stage": "Interview Rescheduled"})
            try:
                from services.hiring_process_service import apply_hiring_event
                apply_hiring_event(candidate_id, interview.get("jd_id"), "rescheduled")
            except Exception as exc:  # stage mapping must not undo a confirmed booking
                db.log_audit("Hiring Stage Update Failed", ACTOR,
                             f"Could not apply the 'rescheduled' stage mapping for candidate id={candidate_id}: {exc}",
                             interview.get("jd_id"))
        db.log_audit("Interview Rescheduled", ACTOR,
                     f"Automatically rescheduled interview #{interview_id} to {start:%Y-%m-%d %H:%M} after candidate confirmation.",
                     interview.get("jd_id"))

    def mark_no_show(self, interview: dict) -> None:
        db.update_interview(int(interview["id"]), {"status": NO_SHOW_STATUS})
        if interview.get("candidate_id"):
            db.update_candidate(int(interview["candidate_id"]), {"hiring_stage": "Interview No Show"})
        db.log_audit("Interview No Show", ACTOR, f"Interview #{interview['id']} recorded as a candidate no-show.",
                     interview.get("jd_id"))

    def notify(self, interview: dict, title: str, message: str) -> None:
        jd_id = interview.get("jd_id")
        db.create_notification("interview", title, message, jd_id=int(jd_id) if jd_id else None,
                               link="/hiring-pipeline", actor=ACTOR)

    def public_link(self, token: str) -> str:
        from assessment.utilities import candidate_test_base_url, validate_public_assessment_link

        link = f"{candidate_test_base_url()}/interview/{token}"
        validate_public_assessment_link(link)
        return link


class RecoveryService:
    def __init__(
        self,
        *,
        repo: Any = None,
        calendar: Optional[CalendarProvider] = None,
        messenger: Optional[Messenger] = None,
        gateway: Optional[InterviewGateway] = None,
        config: Optional[RecoveryConfig] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.repo = repo or default_repo
        self._calendar = calendar
        self.messenger = messenger or Messenger()
        self.gateway = gateway or InterviewGateway()
        self._config = config
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    # ----------------------------------------------------------------- helpers
    @property
    def config(self) -> RecoveryConfig:
        return self._config or load_config()

    @property
    def calendar(self) -> CalendarProvider:
        if self._calendar is None:
            self._calendar = get_calendar_provider()
        return self._calendar

    def _now(self) -> datetime:
        return self.clock()

    def _local_now(self) -> datetime:
        return self._now().astimezone(self.config.tz).replace(tzinfo=None)

    def _require_enabled(self) -> RecoveryConfig:
        cfg = self.config
        if not cfg.enabled:
            raise RecoveryDisabled("Automated interview recovery is turned off (INTERVIEW_RECOVERY_ENABLED=false).")
        return cfg

    def _interview(self, interview_id: int) -> dict:
        interview = self.repo.raw_interview(int(interview_id))
        if not interview:
            raise RecoveryNotFound("Interview not found.")
        return interview

    def _interview_by_token(self, token: str) -> dict:
        token = str(token or "").strip().lower()
        try:
            uuid.UUID(token)
        except ValueError as exc:
            raise RecoveryNotFound("This interview link is invalid or has expired.") from exc
        interview = self.repo.find_interview_by_token(token)
        if not interview:
            raise RecoveryNotFound("This interview link is invalid or has expired.")
        return interview

    def ensure_candidate_token(self, interview: dict) -> str:
        token = str(interview.get("candidate_access_token") or "")
        if not token:
            token = str(uuid.uuid4())
            self.repo.set_interview_fields(int(interview["id"]), {"candidate_access_token": token})
            interview["candidate_access_token"] = token
        return token

    def _record(self, case: dict, action: str, *, outcome: str = "", deliveries: Optional[list[DeliveryResult]] = None,
                detail: Optional[dict] = None) -> None:
        self.repo.add_attempt({
            "case_id": int(case["id"]), "interview_id": int(case["interview_id"]), "action": action,
            "outcome": outcome, "attempt_number": int(case.get("attempt_count") or 0),
            "deliveries": [d.to_dict() for d in deliveries or []], "detail": _iso(detail or {}),
        })

    def _new_case(self, interview: dict, recovery_type: str, *, source: str, actor: str, stage: str,
                  reason: str = "", preferred_windows: Optional[list[dict]] = None) -> dict:
        now = self._now()
        return {
            "interview_id": int(interview["id"]), "candidate_id": int(interview.get("candidate_id") or 0),
            "recruiter_id": int(interview.get("recruiter_id") or 0), "jd_id": interview.get("jd_id"),
            "interviewer": interview.get("interviewer") or "", "recovery_type": recovery_type,
            "status": RecoveryStatus.PENDING, "stage": stage, "source": source, "requested_by": actor,
            "reason": (reason or "")[:1000], "preferred_windows": preferred_windows or [],
            "attempt_count": 0, "max_attempts": self.config.max_attempts,
            "delivery_failure_count": 0, "error_count": 0,
            "proposed_slots": [], "unavailable_slots": [], "selected_slot": None, "confirmed_slot": None,
            "original_interview_start": _naive(interview.get("interview_start")),
            "next_action_at": now, "response_deadline": None, "lease_until": None,
            "last_error": "", "escalated_at": None, "escalation_reason": "", "recommended_action": "",
            "outcome": "", "created_at": now, "updated_at": now, "closed_at": None,
        }

    # ------------------------------------------------------------ entry points
    def request_reschedule(self, interview_id: int, *, source: str, actor: str = "", reason: str = "",
                           preferred_windows: object = None, interactive: bool = False) -> dict:
        """Candidate asked to move an interview. Starts the slot search immediately."""
        self._require_enabled()
        windows = parse_preferred_windows(preferred_windows)
        interview = self._interview(interview_id)

        if interview.get("status") == NO_SHOW_STATUS:
            no_show = self.repo.get_open_case(int(interview["id"]), RecoveryType.NO_SHOW)
            if no_show:
                return self._accept_no_show_reschedule(no_show, windows, interactive=interactive)
        if not interview_is_active(interview):
            raise RecoveryConflict("This interview can no longer be rescheduled automatically.")
        if interview.get("attendance_status") == ATTENDANCE_ATTENDED:
            raise RecoveryConflict("This interview has already taken place.")

        case, created = self.repo.create_case(self._new_case(
            interview, RecoveryType.RESCHEDULE, source=source, actor=actor, stage=STAGE_SLOTS,
            reason=reason, preferred_windows=windows))
        if created:
            self._record(case, "reschedule_requested", detail={"source": source, "reason": reason, "preferred_windows": windows})
            self._run_case(int(case["id"]), {RecoveryStatus.PENDING}, interactive=interactive)
        elif windows and case.get("status") in {RecoveryStatus.SLOT_PROPOSED, RecoveryStatus.RETRY_SCHEDULED}:
            # "None of these times work": search again inside the candidate's new windows.
            self.repo.update_case(int(case["id"]), {"preferred_windows": windows})
            self._record(case, "availability_updated", detail={"preferred_windows": windows})
            self._run_case(int(case["id"]), {RecoveryStatus.SLOT_PROPOSED, RecoveryStatus.RETRY_SCHEDULED},
                           interactive=interactive, force_search=True)
        return self.case_view(self.repo.get_case(int(case["id"])))

    def report_attendance(self, interview_id: int, attendance: str, *, actor: str) -> dict:
        """Recruiter/interviewer confirms whether the candidate attended."""
        attendance = str(attendance or "").strip().lower()
        if attendance not in ATTENDANCE_VALUES:
            raise RecoveryError("attendance must be 'attended' or 'no_show'.")
        interview = self._interview(interview_id)
        if attendance == ATTENDANCE_ATTENDED:
            self.repo.set_interview_fields(int(interview["id"]), {"attendance_status": ATTENDANCE_ATTENDED})
            open_case = self.repo.get_open_case(int(interview["id"]), RecoveryType.NO_SHOW)
            if open_case:
                self._close(open_case, "attendance_corrected")
            return {"interview_id": int(interview["id"]), "attendance_status": ATTENDANCE_ATTENDED, "case": None}
        case = self._open_no_show(interview, source="recruiter_confirmed", actor=actor, require_grace=True)
        return {"interview_id": int(interview["id"]), "attendance_status": ATTENDANCE_NO_SHOW, "case": self.case_view(case)}

    def detect_no_shows(self) -> int:
        """Auto mode: treat active interviews without attendance past the grace period as no-shows."""
        cfg = self.config
        if not cfg.enabled or cfg.no_show_mode != "auto":
            return 0
        local_now = self._local_now()
        window_end = local_now - timedelta(minutes=cfg.no_show_grace_minutes)
        window_start = local_now - timedelta(hours=cfg.no_show_lookback_hours)
        opened = 0
        for interview in self.repo.interviews_due_for_no_show_check(window_start, window_end, sorted(ACTIVE_INTERVIEW_STATUSES)):
            try:
                case = self._open_no_show(interview, source="auto_detection", actor=ACTOR, require_grace=True)
                opened += 1 if case and case.get("_created") else 0
            except RecoveryError:
                continue
        return opened

    def run_due(self, limit: int = 50) -> dict:
        """Scheduler tick: detect no-shows, then advance due cases. Safe to run repeatedly."""
        cfg = self.config
        if not cfg.enabled:
            return {"enabled": False, "detected_no_shows": 0, "processed": 0}
        detected = self.detect_no_shows()
        processed = 0
        for _ in range(max(1, limit)):
            case = self.repo.claim_next_due_case(self._now(), cfg.lease_seconds)
            if not case:
                break
            self._dispatch(case)
            processed += 1
        return {"enabled": True, "detected_no_shows": detected, "processed": processed}

    # -------------------------------------------------------- candidate portal
    def public_view(self, token: str) -> dict:
        interview = self._interview_by_token(token)
        case = self.repo.get_open_case(int(interview["id"])) or self._latest_case(interview)
        status = (case or {}).get("status")
        stage = (case or {}).get("stage")
        start = _naive(interview.get("interview_start"))
        name = str(interview.get("candidate_name") or "").split(" ")[0]
        active = interview_is_active(interview) and interview.get("attendance_status") != ATTENDANCE_ATTENDED
        enabled = self.config.enabled
        return {
            "candidate_first_name": name,
            "job_role": interview.get("job_role") or "",
            "interview_mode": interview.get("interview_mode") or "",
            "interview_start": start.isoformat(timespec="minutes") if start else None,
            "interview_status": interview.get("status") or "",
            "timezone": self.config.timezone,
            "case": self._public_case(case),
            "actions": {
                "can_request_reschedule": enabled and active and status not in RecoveryStatus.OPEN - {RecoveryStatus.SLOT_PROPOSED},
                "can_choose_slot": status == RecoveryStatus.SLOT_PROPOSED,
                "can_respond_no_show": status == RecoveryStatus.AWAITING_RESPONSE and stage == STAGE_CONSENT,
                "can_decline": status in {RecoveryStatus.AWAITING_RESPONSE, RecoveryStatus.SLOT_PROPOSED, RecoveryStatus.RETRY_SCHEDULED},
            },
        }

    def public_request_reschedule(self, token: str, reason: str = "", preferred_windows: object = None) -> dict:
        interview = self._interview_by_token(token)
        self.request_reschedule(int(interview["id"]), source="candidate_portal", actor="candidate",
                                reason=reason, preferred_windows=preferred_windows, interactive=True)
        return self.public_view(token)

    def public_respond(self, token: str, wants_reschedule: bool) -> dict:
        self._require_enabled()
        interview = self._interview_by_token(token)
        case = self.repo.get_open_case(int(interview["id"]))
        if not case:
            raise RecoveryConflict("There is nothing waiting for your response on this interview.")
        if not wants_reschedule:
            claimed = self.repo.claim_case(int(case["id"]), {RecoveryStatus.AWAITING_RESPONSE, RecoveryStatus.SLOT_PROPOSED,
                                                             RecoveryStatus.RETRY_SCHEDULED}, self._now(), self.config.lease_seconds)
            if claimed:
                self._record(claimed, "candidate_response", detail={"wants_reschedule": False})
                self._close(claimed, "candidate_declined")
                self.gateway.notify(interview, "Candidate withdrew from interview",
                                    f"{interview.get('candidate_name') or 'The candidate'} said they no longer wish to "
                                    f"interview for {interview.get('job_role') or 'the role'}.")
            return self.public_view(token)
        if case.get("recovery_type") == RecoveryType.NO_SHOW and case.get("stage") == STAGE_CONSENT:
            self._accept_no_show_reschedule(case, [], interactive=True)
        return self.public_view(token)

    def public_confirm_slot(self, token: str, chosen_slot_id: str) -> dict:
        """Book a proposed slot after re-checking it is still free."""
        cfg = self._require_enabled()
        interview = self._interview_by_token(token)
        case = self.repo.get_open_case(int(interview["id"]))
        if not case:
            latest = self._latest_case(interview)
            if latest and (latest.get("confirmed_slot") or {}).get("id") == chosen_slot_id:
                return {**self.public_view(token), "booked": True}  # duplicate confirmation
            raise RecoveryConflict("There are no interview times waiting for confirmation.")
        slot = next((s for s in case.get("proposed_slots") or [] if s.get("id") == chosen_slot_id), None)
        if not slot:
            raise RecoveryError("Please choose one of the interview times offered to you.")
        claimed = self.repo.claim_case(int(case["id"]), {RecoveryStatus.SLOT_PROPOSED}, self._now(), cfg.lease_seconds)
        if not claimed:
            raise RecoveryConflict("Your choice is already being processed. Please refresh in a moment.")
        self.repo.update_case(int(case["id"]), {"selected_slot": slot})
        claimed["selected_slot"] = slot

        lock_key = f"interview-booking:recruiter:{int(interview.get('recruiter_id') or 0)}"
        owner = f"case:{case['id']}:{uuid.uuid4().hex}"
        if not self.repo.acquire_lock(lock_key, owner, self._now(), 60):
            self.repo.update_case(int(case["id"]), {"status": RecoveryStatus.SLOT_PROPOSED, "selected_slot": None, "lease_until": None})
            raise RecoveryConflict("Another booking is being finalised. Please try again in a few seconds.")
        try:
            start, end = _naive(slot["start"]), _naive(slot["end"])
            if not self._slot_still_free(interview, start, end):
                self._record(claimed, "slot_unavailable", detail={"slot": slot})
                unavailable = list({*(claimed.get("unavailable_slots") or []), slot["id"]})
                self.repo.update_case(int(case["id"]), {"unavailable_slots": unavailable, "selected_slot": None})
                claimed["unavailable_slots"] = unavailable
                self._search_and_propose(claimed, interview, interactive=True, count_attempt=False)
                return {**self.public_view(token), "booked": False, "slot_unavailable": True}
            self._book(claimed, interview, slot)
        finally:
            self.repo.release_lock(lock_key, owner)
        return {**self.public_view(token), "booked": True}

    # --------------------------------------------------------- recruiter tools
    def retry_case(self, case_id: int, *, recruiter_id: int, actor: str) -> dict:
        self._require_enabled()
        case = self._owned_case(case_id, recruiter_id)
        if case.get("status") != RecoveryStatus.ESCALATED:
            raise RecoveryConflict("Only escalated cases can be retried.")
        now = self._now()
        updated = self.repo.update_case(int(case["id"]), {
            "status": RecoveryStatus.PENDING, "attempt_count": 0, "delivery_failure_count": 0, "error_count": 0,
            "max_attempts": self.config.max_attempts, "escalated_at": None, "escalation_reason": "",
            "recommended_action": "", "next_action_at": now, "last_error": "",
        }, expected_status=RecoveryStatus.ESCALATED)
        if updated:
            self._record(case, "manual_retry", detail={"actor": actor})
            self._run_case(int(case["id"]), {RecoveryStatus.PENDING})
        return self.case_view(self.repo.get_case(int(case["id"])), include_history=True)

    def close_case(self, case_id: int, *, recruiter_id: int, actor: str, note: str = "") -> dict:
        case = self._owned_case(case_id, recruiter_id)
        if case.get("status") in RecoveryStatus.TERMINAL:
            return self.case_view(case, include_history=True)
        self._record(case, "closed_by_recruiter", detail={"actor": actor, "note": note[:500]})
        self._close(case, "closed_by_recruiter")
        return self.case_view(self.repo.get_case(int(case["id"])), include_history=True)

    def close_for_interview(self, interview_id: int, outcome: str) -> None:
        """Stop automation when a recruiter manually reschedules or cancels."""
        for recovery_type in RecoveryType.ALL:
            case = self.repo.get_open_case(int(interview_id), recovery_type)
            if case:
                self._record(case, "superseded", detail={"outcome": outcome})
                self._close(case, outcome)

    def get_case_for_recruiter(self, case_id: int, recruiter_id: int) -> dict:
        return self.case_view(self._owned_case(case_id, recruiter_id), include_history=True)

    def list_cases_for_recruiter(self, recruiter_id: int, statuses: Optional[list[str]] = None) -> list[dict]:
        return [self.case_view(c) for c in self.repo.list_cases(recruiter_id=int(recruiter_id), statuses=statuses)]

    def summaries_for_interviews(self, interview_ids: list[int]) -> dict[int, dict]:
        return {iid: self.case_view(case) for iid, case in self.repo.latest_cases_for_interviews(interview_ids).items()}

    def _owned_case(self, case_id: int, recruiter_id: int) -> dict:
        case = self.repo.get_case(int(case_id))
        if not case or int(case.get("recruiter_id") or 0) != int(recruiter_id):
            raise RecoveryNotFound("Recovery case not found.")
        return case

    # ------------------------------------------------------------ the engine
    def _run_case(self, case_id: int, from_statuses: set[str], *, interactive: bool = False, force_search: bool = False) -> None:
        case = self.repo.claim_case(case_id, from_statuses, self._now(), self.config.lease_seconds)
        if case:
            self._dispatch(case, interactive=interactive, force_search=force_search)

    def _dispatch(self, case: dict, *, interactive: bool = False, force_search: bool = False) -> None:
        resume = case.get("resume_from") or RecoveryStatus.PENDING
        interview = self.repo.raw_interview(int(case["interview_id"]))
        try:
            selected = case.get("selected_slot")
            if selected and interview and _naive(interview.get("interview_start")) == _naive(selected.get("start")):
                # A worker stopped after booking but before finishing the case.
                self._finish_booking(case, interview, selected)
                return
            if selected:
                self.repo.update_case(int(case["id"]), {"selected_slot": None})
            ineligible = self._ineligible_reason(case, interview)
            if ineligible:
                self._record(case, "stopped", detail={"reason": ineligible})
                self._close(case, ineligible)
                return
            if force_search:
                self._search_and_propose(case, interview, interactive=interactive, count_attempt=False)
            elif resume in {RecoveryStatus.PENDING, RecoveryStatus.RETRY_SCHEDULED}:
                if case.get("stage") == STAGE_CONSENT:
                    self._send_no_show_outreach(case, interview)
                else:
                    self._search_and_propose(case, interview, interactive=interactive)
            elif resume in {RecoveryStatus.AWAITING_RESPONSE, RecoveryStatus.SLOT_PROPOSED}:
                deadline = case.get("response_deadline")
                if deadline and deadline <= self._now():
                    self._handle_timeout(case, interview)
                else:
                    self.repo.update_case(int(case["id"]), {"status": resume, "lease_until": None})
            else:
                self.repo.update_case(int(case["id"]), {"status": RecoveryStatus.RETRY_SCHEDULED,
                                                        "next_action_at": self._now(), "lease_until": None})
        except Exception as exc:  # never leave a case stuck in PROCESSING
            self._handle_unexpected(case, interview, exc)

    def _ineligible_reason(self, case: dict, interview: Optional[dict]) -> str:
        if not interview:
            return "interview_deleted"
        if interview.get("attendance_status") == ATTENDANCE_ATTENDED:
            return "candidate_attended"
        status = str(interview.get("status") or "")
        if case.get("recovery_type") == RecoveryType.NO_SHOW:
            return "" if status == NO_SHOW_STATUS else "interview_no_longer_no_show"
        if status not in ACTIVE_INTERVIEW_STATUSES:
            return "interview_cancelled_or_completed"
        if _naive(interview.get("interview_start")) != _naive(case.get("original_interview_start")):
            return "rescheduled_elsewhere"
        return ""

    def _search_and_propose(self, case: dict, interview: dict, *, interactive: bool = False, count_attempt: bool = True) -> None:
        cfg = self.config
        local_now = self._local_now()
        start = _naive(interview.get("interview_start"))
        end = _naive(interview.get("interview_end"))
        duration = (end - start) if start and end and end > start else timedelta(minutes=60)
        window_end = local_now + timedelta(days=cfg.slot_search_days + 1)
        busy = list(self.calendar.busy_intervals(int(case["recruiter_id"]), local_now, window_end, int(interview["id"])))
        busy += self.gateway.candidate_busy(int(case["candidate_id"]), local_now, window_end, int(interview["id"]))
        exclude = set(case.get("unavailable_slots") or [])
        if start:
            exclude.add(slot_id(start))
        slots = find_slots(cfg, local_now, duration, busy, preferred_windows=case.get("preferred_windows") or None,
                           exclude_starts=exclude)
        attempts = int(case.get("attempt_count") or 0) + (1 if count_attempt else 0)

        if not slots:
            self._record({**case, "attempt_count": attempts}, "slot_search", outcome=AttemptOutcome.NO_SLOTS,
                         detail={"calendar": self.calendar.name, "search_days": cfg.slot_search_days})
            if attempts >= int(case.get("max_attempts") or cfg.max_attempts):
                self._escalate(case, interview, "No mutually available interview time was found within the search window.",
                               "Agree a time with the candidate directly or open more interviewer availability, then retry.",
                               {"attempt_count": attempts, "proposed_slots": []})
            else:
                self.repo.update_case(int(case["id"]), {
                    "status": RecoveryStatus.RETRY_SCHEDULED, "attempt_count": attempts, "proposed_slots": [],
                    "next_action_at": self._now() + timedelta(minutes=cfg.retry_delay_minutes),
                    "last_error": "No mutually available slots yet.", "lease_until": None,
                })
            return

        outcome = self._message_candidate(case, interview, "slots", slots)
        self._record({**case, "attempt_count": attempts}, "slots_offered",
                     outcome=AttemptOutcome.DELIVERED if outcome.delivered else AttemptOutcome.DELIVERY_FAILED,
                     deliveries=outcome.deliveries, detail={"slots": slots})
        if outcome.delivered or interactive:
            # Interactive requests show the options on the portal page itself.
            self.repo.update_case(int(case["id"]), {
                "status": RecoveryStatus.SLOT_PROPOSED, "stage": STAGE_SLOTS, "proposed_slots": slots,
                "attempt_count": attempts, "next_action_at": None, "lease_until": None,
                "response_deadline": self._now() + timedelta(minutes=cfg.response_timeout_minutes),
                "last_error": "" if outcome.delivered else outcome.error, "delivery_failure_count": 0 if outcome.delivered else int(case.get("delivery_failure_count") or 0),
            })
            return
        self._delivery_failed(case, interview, outcome, {"proposed_slots": slots})

    def _send_no_show_outreach(self, case: dict, interview: dict) -> None:
        outcome = self._message_candidate(case, interview, "no_show")
        attempts = int(case.get("attempt_count") or 0) + 1
        self._record({**case, "attempt_count": attempts}, "no_show_outreach",
                     outcome=AttemptOutcome.DELIVERED if outcome.delivered else AttemptOutcome.DELIVERY_FAILED,
                     deliveries=outcome.deliveries)
        if outcome.delivered:
            self.repo.update_case(int(case["id"]), {
                "status": RecoveryStatus.AWAITING_RESPONSE, "attempt_count": attempts, "next_action_at": None,
                "response_deadline": self._now() + timedelta(minutes=self.config.response_timeout_minutes),
                "lease_until": None, "last_error": "", "delivery_failure_count": 0,
            })
            return
        self._delivery_failed(case, interview, outcome, {})

    def _accept_no_show_reschedule(self, case: dict, windows: list[dict], *, interactive: bool) -> dict:
        claimed = self.repo.claim_case(int(case["id"]), {RecoveryStatus.AWAITING_RESPONSE, RecoveryStatus.RETRY_SCHEDULED},
                                       self._now(), self.config.lease_seconds)
        if claimed:
            patch = {"stage": STAGE_SLOTS, "preferred_windows": windows or claimed.get("preferred_windows") or []}
            self.repo.update_case(int(case["id"]), patch)
            claimed.update(patch)
            self._record(claimed, "candidate_response", detail={"wants_reschedule": True, "preferred_windows": windows})
            interview = self.repo.raw_interview(int(case["interview_id"]))
            try:
                self._search_and_propose(claimed, interview, interactive=interactive, count_attempt=False)
            except Exception as exc:
                self._handle_unexpected(claimed, interview, exc)
        return self.case_view(self.repo.get_case(int(case["id"])))

    def _handle_timeout(self, case: dict, interview: dict) -> None:
        self._record(case, "response_timeout", outcome=AttemptOutcome.NO_RESPONSE)
        if int(case.get("attempt_count") or 0) >= int(case.get("max_attempts") or self.config.max_attempts):
            self._escalate(case, interview,
                           f"The candidate did not respond after {case.get('attempt_count')} automated attempts.",
                           "Call the candidate to agree a time, or close the case if they have withdrawn.")
        elif case.get("stage") == STAGE_CONSENT:
            self._send_no_show_outreach(case, interview)
        else:
            self._search_and_propose(case, interview)

    def _delivery_failed(self, case: dict, interview: dict, outcome: MessageOutcome, extra: dict) -> None:
        failures = int(case.get("delivery_failure_count") or 0) + 1
        if not outcome.transient_failure:
            self._escalate(case, interview, f"The candidate could not be contacted: {outcome.error}",
                           "Check the candidate's contact details and the email/SMS configuration, then retry.",
                           {**extra, "delivery_failure_count": failures, "last_error": outcome.error})
        elif failures >= self.config.max_delivery_failures:
            self._escalate(case, interview, f"Messages kept failing after {failures} tries: {outcome.error}",
                           "Check the email/SMS provider status, then retry the case.",
                           {**extra, "delivery_failure_count": failures, "last_error": outcome.error})
        else:
            backoff = min(self.config.retry_delay_minutes * (2 ** (failures - 1)), 24 * 60)
            self.repo.update_case(int(case["id"]), {
                **extra, "status": RecoveryStatus.RETRY_SCHEDULED, "delivery_failure_count": failures,
                "next_action_at": self._now() + timedelta(minutes=backoff), "last_error": outcome.error,
                "lease_until": None,
            })

    def _handle_unexpected(self, case: dict, interview: Optional[dict], exc: Exception) -> None:
        logger.exception("Interview recovery case %s failed", case.get("id"))
        errors = int(case.get("error_count") or 0) + 1
        message = f"{exc.__class__.__name__}: {exc}"[:500]
        try:
            self._record(case, "error", detail={"error": message})
            if errors >= self.config.max_delivery_failures:
                self._escalate(case, interview or {}, f"Automated recovery failed repeatedly: {message}",
                               "Review the error, fix the integration or data, then retry.",
                               {"error_count": errors, "last_error": message})
            else:
                self.repo.update_case(int(case["id"]), {
                    "status": RecoveryStatus.RETRY_SCHEDULED, "error_count": errors, "last_error": message,
                    "next_action_at": self._now() + timedelta(minutes=self.config.retry_delay_minutes), "lease_until": None,
                })
        except Exception:
            logger.exception("Could not record failure for interview recovery case %s", case.get("id"))

    def _slot_still_free(self, interview: dict, start: Optional[datetime], end: Optional[datetime]) -> bool:
        if not start or not end or start <= self._local_now():
            return False
        recruiter_id = int(interview.get("recruiter_id") or 0)
        busy = self.calendar.busy_intervals(recruiter_id, start, end, int(interview["id"]))
        busy += self.gateway.candidate_busy(int(interview.get("candidate_id") or 0), start, end, int(interview["id"]))
        if any(start < b_end and end > b_start for b_start, b_end in busy):
            return False
        return self.gateway.slot_available(recruiter_id, start, end, int(interview["id"]))

    def _book(self, case: dict, interview: dict, slot: dict) -> None:
        start, end = _naive(slot["start"]), _naive(slot["end"])
        self.gateway.reschedule(interview, start, end)
        self.repo.set_interview_fields(int(interview["id"]), {"attendance_status": None})
        refreshed = self.repo.raw_interview(int(interview["id"])) or {**interview, "interview_start": start, "interview_end": end}
        self._finish_booking(case, refreshed, slot)

    def _finish_booking(self, case: dict, interview: dict, slot: dict) -> None:
        try:
            calendar_result = self.calendar.update_event(interview, _naive(slot["start"]), _naive(slot["end"]))
        except Exception as exc:
            calendar_result = {"status": "failed", "error": str(exc)[:300]}
        self._record(case, "booked", outcome="booked", detail={"slot": slot, "calendar": calendar_result})
        final = RecoveryStatus.RECOVERED if case.get("recovery_type") == RecoveryType.NO_SHOW else RecoveryStatus.RESCHEDULED
        now = self._now()
        self.repo.update_case(int(case["id"]), {
            "status": final, "confirmed_slot": slot, "selected_slot": None, "outcome": "rescheduled",
            "response_deadline": None, "next_action_at": None, "lease_until": None, "closed_at": now,
        })
        confirmation = self._message_candidate(case, interview, "confirmed", [slot])
        self._record(case, "confirmation_sent",
                     outcome=AttemptOutcome.DELIVERED if confirmation.delivered else AttemptOutcome.DELIVERY_FAILED,
                     deliveries=confirmation.deliveries)
        interviewer = interview.get("interviewer") or "the interviewer"
        note = "" if confirmation.delivered else " The confirmation email could not be delivered; please let the candidate know."
        self.gateway.notify(interview, "Interview rescheduled automatically",
                            f"{interview.get('candidate_name') or 'The candidate'} confirmed a new time: {slot['label']}. "
                            f"Please share the new time with {interviewer}.{note}")

    def _escalate(self, case: dict, interview: dict, reason: str, action: str, patch: Optional[dict] = None) -> None:
        if patch:
            self.repo.update_case(int(case["id"]), patch)
        if not self.repo.mark_escalated(int(case["id"]), self._now(), reason, action):
            self.repo.update_case(int(case["id"]), {"status": RecoveryStatus.ESCALATED, "lease_until": None})
            return
        self._record(case, "escalated", detail={"reason": reason, "recommended_action": action})
        attempts = self.repo.list_attempts(int(case["id"]))
        history = "\n".join(
            f"- {a.get('created_at'):%Y-%m-%d %H:%M} {a.get('action')} {a.get('outcome') or ''}".rstrip()
            for a in attempts if isinstance(a.get("created_at"), datetime)
        )
        candidate = interview.get("candidate_name") or f"candidate #{case.get('candidate_id')}"
        try:
            self.gateway.notify(interview, "Interview recovery needs your attention",
                                f"Interview #{case['interview_id']} with {candidate}: {reason} Next step: {action}")
        except Exception:
            logger.exception("Could not create escalation notification for case %s", case.get("id"))
        body = (
            f"Automated interview recovery could not finish and needs your decision.\n\n"
            f"Interview: #{case['interview_id']} ({interview.get('job_role') or 'role not set'})\n"
            f"Candidate: {candidate} (id {case.get('candidate_id')})\n"
            f"Recovery type: {case.get('recovery_type')}\n"
            f"Reason: {reason}\n"
            f"Recommended next step: {action}\n\n"
            f"Attempt history:\n{history or '- none'}\n\n"
            f"Open the Hiring Pipeline in HR Assist to review, retry or close this case."
        )
        result = self.messenger.send_recruiter(interview, f"Action needed: interview recovery for {candidate}", body)
        self._record(case, "recruiter_notified",
                     outcome=AttemptOutcome.DELIVERED if result.delivered else AttemptOutcome.DELIVERY_FAILED,
                     deliveries=result.deliveries)

    def _close(self, case: dict, outcome: str) -> None:
        self.repo.update_case(int(case["id"]), {
            "status": RecoveryStatus.CLOSED, "outcome": outcome, "next_action_at": None,
            "response_deadline": None, "lease_until": None, "closed_at": self._now(),
        })

    def _open_no_show(self, interview: dict, *, source: str, actor: str, require_grace: bool) -> dict:
        self._require_enabled()
        cfg = self.config
        start = _naive(interview.get("interview_start"))
        if interview.get("status") not in ACTIVE_INTERVIEW_STATUSES and interview.get("status") != NO_SHOW_STATUS:
            raise RecoveryConflict("Only scheduled interviews can be marked as a no-show.")
        if interview.get("attendance_status") == ATTENDANCE_ATTENDED:
            raise RecoveryConflict("The candidate is recorded as having attended this interview.")
        if not start or (require_grace and self._local_now() < start + timedelta(minutes=cfg.no_show_grace_minutes)):
            raise RecoveryConflict(f"A no-show can be recorded {cfg.no_show_grace_minutes} minutes after the interview start.")
        existing = self.repo.get_open_case(int(interview["id"]), RecoveryType.NO_SHOW)
        if existing or self.repo.case_exists_for_occurrence(int(interview["id"]), RecoveryType.NO_SHOW, start):
            return existing or {}
        case, created = self.repo.create_case(self._new_case(interview, RecoveryType.NO_SHOW, source=source,
                                                             actor=actor, stage=STAGE_CONSENT))
        if not created:
            return case
        self.gateway.mark_no_show(interview)
        self.repo.set_interview_fields(int(interview["id"]), {"attendance_status": ATTENDANCE_NO_SHOW})
        self._record(case, "no_show_detected", detail={"source": source, "interview_start": start})
        self._run_case(int(case["id"]), {RecoveryStatus.PENDING})
        return {**(self.repo.get_case(int(case["id"])) or case), "_created": True}

    def _latest_case(self, interview: dict) -> Optional[dict]:
        return self.repo.latest_cases_for_interviews([int(interview["id"])]).get(int(interview["id"]))

    # ---------------------------------------------------------------- messages
    def _message_candidate(self, case: dict, interview: dict, kind: str, slots: Optional[list[dict]] = None) -> MessageOutcome:
        try:
            link = self.gateway.public_link(self.ensure_candidate_token(interview))
        except Exception as exc:
            return MessageOutcome([DeliveryResult("email", "failed", error=f"Candidate link unavailable: {exc}"[:300], transient=False)])
        name = str(interview.get("candidate_name") or "there").split(" ")[0]
        role = interview.get("job_role") or "the role"
        options = "\n".join(f"  - {s['label']}" for s in slots or [])
        if kind == "slots":
            subject = f"Choose a new interview time for {role}"
            body = (f"Hi {name},\n\nHere are the next available times for your {role} interview "
                    f"({self.config.timezone}):\n{options}\n\nPlease pick the one that suits you here:\n{link}\n\n"
                    "If none of these work, you can share your availability on the same page.\n\nRegards,\nRecruitment Team")
            sms = f"New interview times are available for {role}. Choose one here: {link}"
        elif kind == "no_show":
            subject = f"We missed you at your {role} interview"
            body = (f"Hi {name},\n\nWe were sorry not to see you at your scheduled interview for {role}. "
                    f"If you are still interested, you can pick a new time here:\n{link}\n\n"
                    "If you are no longer interested, you can let us know on the same page.\n\nRegards,\nRecruitment Team")
            sms = f"We missed you at your {role} interview. Reschedule or reply here: {link}"
        else:
            subject = f"Your {role} interview is confirmed"
            body = (f"Hi {name},\n\nYour interview for {role} is confirmed for {options.strip(' -')} "
                    f"({self.config.timezone}).\n\nYou can view or change it here:\n{link}\n\nRegards,\nRecruitment Team")
            sms = f"Your {role} interview is confirmed for {(slots or [{}])[0].get('label', '')}."
        return self.messenger.send_candidate(interview, subject, body, sms)

    # ------------------------------------------------------------------- views
    def case_view(self, case: Optional[dict], include_history: bool = False) -> Optional[dict]:
        if not case:
            return None
        keys = ("id", "interview_id", "candidate_id", "recruiter_id", "jd_id", "interviewer", "recovery_type", "status",
                "stage", "source", "reason", "preferred_windows", "attempt_count", "max_attempts", "delivery_failure_count",
                "proposed_slots", "selected_slot", "confirmed_slot", "original_interview_start", "next_action_at",
                "response_deadline", "last_error", "escalated_at", "escalation_reason", "recommended_action", "outcome",
                "created_at", "updated_at", "closed_at")
        view = {key: _iso(case.get(key)) for key in keys}
        if include_history:
            view["history"] = [_iso({k: v for k, v in a.items() if k != "_id"}) for a in self.repo.list_attempts(int(case["id"]))]
        return view

    @staticmethod
    def _public_case(case: Optional[dict]) -> Optional[dict]:
        if not case:
            return None
        return {"status": case.get("status"), "recovery_type": case.get("recovery_type"), "stage": case.get("stage"),
                "proposed_slots": case.get("proposed_slots") or [], "confirmed_slot": case.get("confirmed_slot"),
                "response_deadline": _iso(case.get("response_deadline"))}


_service: Optional[RecoveryService] = None


def get_service() -> RecoveryService:
    global _service
    if _service is None:
        _service = RecoveryService()
    return _service
