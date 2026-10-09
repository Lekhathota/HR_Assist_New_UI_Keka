"""Calendar and messaging provider interfaces for interview recovery.

Production code never fabricates success: a provider that is not configured
reports "not_configured", and delivery failures are classified as transient
(retry later) or permanent (needs a recruiter or configuration change).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import database as db
from interview_recovery.models import ACTIVE_INTERVIEW_STATUSES

_PERMANENT_MARKERS = ("not configured", "authentication", "missing", "not installed", "set twilio")


@dataclass
class DeliveryResult:
    channel: str
    status: str  # sent | failed | skipped
    provider_message_id: str = ""
    error: str = ""
    transient: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"channel": self.channel, "status": self.status, "provider_message_id": self.provider_message_id,
                "error": self.error, "transient": self.transient}


@dataclass
class MessageOutcome:
    deliveries: list[DeliveryResult] = field(default_factory=list)

    @property
    def delivered(self) -> bool:
        return any(d.status == "sent" for d in self.deliveries)

    @property
    def transient_failure(self) -> bool:
        failures = [d for d in self.deliveries if d.status == "failed"]
        return bool(failures) and all(d.transient for d in failures)

    @property
    def error(self) -> str:
        return "; ".join(f"{d.channel}: {d.error}" for d in self.deliveries if d.error)


def _classify(exc: Exception) -> tuple[str, bool]:
    message = str(exc) or exc.__class__.__name__
    permanent = any(marker in message.lower() for marker in _PERMANENT_MARKERS)
    return message[:500], not permanent


class CalendarProvider(ABC):
    name = "abstract"

    @abstractmethod
    def busy_intervals(self, recruiter_id: int, start: datetime, end: datetime,
                       exclude_interview_id: Optional[int] = None) -> list[tuple[datetime, datetime]]:
        """Busy periods (naive local wall-clock) for the recruiter in [start, end)."""

    @abstractmethod
    def update_event(self, interview: dict, new_start: datetime, new_end: datetime) -> dict[str, Any]:
        """Move the external calendar event, if one exists."""


class InternalScheduleCalendar(CalendarProvider):
    """Availability from interviews already booked in HR Assist.

    HR Assist has no external calendar connection today, so the interview
    record is the system of record and no external event is moved.
    """

    name = "internal"

    def busy_intervals(self, recruiter_id, start, end, exclude_interview_id=None):
        rows = db.get_interviews({"recruiter_id": recruiter_id, "range_start": start, "range_end": end,
                                  "exclude_cancelled": True})
        busy = []
        for row in rows:
            if exclude_interview_id and int(row.get("id") or 0) == int(exclude_interview_id):
                continue
            if str(row.get("status") or "") not in ACTIVE_INTERVIEW_STATUSES:
                continue
            row_start = _parse(row.get("interview_start"))
            row_end = _parse(row.get("interview_end"))
            if row_start and row_end:
                busy.append((row_start, row_end))
        return busy

    def update_event(self, interview, new_start, new_end):
        return {"status": "not_configured", "provider": self.name,
                "detail": "No external calendar is connected; the HR Assist interview record was updated."}


def _parse(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def get_calendar_provider() -> CalendarProvider:
    name = (os.environ.get("INTERVIEW_CALENDAR_PROVIDER") or "internal").strip().lower()
    if name == "internal":
        return InternalScheduleCalendar()
    raise RuntimeError(
        f"INTERVIEW_CALENDAR_PROVIDER={name!r} is not implemented. Use 'internal' or add a CalendarProvider "
        "implementation (Google/Microsoft) with read-free/busy and event-update permissions."
    )


class Messenger:
    """Candidate and recruiter messaging through the existing SMTP/Twilio senders."""

    def send_candidate(self, interview: dict, subject: str, body: str, sms_body: str = "") -> MessageOutcome:
        from services.interview_service import default_from_email, send_email, send_text_message

        outcome = MessageOutcome()
        to_email = interview.get("to_email") or interview.get("candidate_email") or ""
        if not to_email:
            outcome.deliveries.append(DeliveryResult("email", "failed", error="Candidate email is missing.", transient=False))
        else:
            try:
                send_email(to_email, subject, body, default_from_email())
                outcome.deliveries.append(DeliveryResult("email", "sent"))
            except Exception as exc:
                error, transient = _classify(exc)
                outcome.deliveries.append(DeliveryResult("email", "failed", error=error, transient=transient))

        phone = self._candidate_phone(interview)
        if sms_body and phone and os.environ.get("TWILIO_ACCOUNT_SID"):
            try:
                sid = send_text_message(phone, sms_body)
                outcome.deliveries.append(DeliveryResult("sms", "sent", provider_message_id=sid))
            except Exception as exc:
                error, transient = _classify(exc)
                outcome.deliveries.append(DeliveryResult("sms", "failed", error=error, transient=transient))
        return outcome

    def send_recruiter(self, interview: dict, subject: str, body: str) -> MessageOutcome:
        from services.interview_service import default_from_email, send_email

        outcome = MessageOutcome()
        to_email = interview.get("recruiter_email") or ""
        if not to_email:
            outcome.deliveries.append(DeliveryResult("email", "skipped", error="Recruiter email is missing."))
            return outcome
        try:
            send_email(to_email, subject, body, default_from_email())
            outcome.deliveries.append(DeliveryResult("email", "sent"))
        except Exception as exc:
            error, transient = _classify(exc)
            outcome.deliveries.append(DeliveryResult("email", "failed", error=error, transient=transient))
        return outcome

    @staticmethod
    def _candidate_phone(interview: dict) -> str:
        if interview.get("candidate_phone"):
            return str(interview["candidate_phone"])
        candidate = db.get_candidate_by_id(int(interview.get("candidate_id") or 0)) or {}
        return str(candidate.get("phone") or "")
