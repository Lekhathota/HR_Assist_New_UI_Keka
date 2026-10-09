"""Recovery case states, types and interview eligibility rules."""

from __future__ import annotations


class RecoveryType:
    RESCHEDULE = "RESCHEDULE"
    NO_SHOW = "NO_SHOW"
    ALL = frozenset({RESCHEDULE, NO_SHOW})


class RecoveryStatus:
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    AWAITING_RESPONSE = "AWAITING_RESPONSE"
    SLOT_PROPOSED = "SLOT_PROPOSED"
    RESCHEDULED = "RESCHEDULED"
    RECOVERED = "RECOVERED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    ESCALATED = "ESCALATED"
    CLOSED = "CLOSED"

    # A case stays "open" (and blocks a duplicate case for the same interview)
    # until automation finishes it or a recruiter closes it.
    OPEN = frozenset({PENDING, PROCESSING, AWAITING_RESPONSE, SLOT_PROPOSED, RETRY_SCHEDULED, ESCALATED})
    # States the scheduler acts on without a human.
    AUTOMATED = frozenset({PENDING, PROCESSING, AWAITING_RESPONSE, SLOT_PROPOSED, RETRY_SCHEDULED})
    TERMINAL = frozenset({RESCHEDULED, RECOVERED, CLOSED})


class AttemptOutcome:
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"
    NO_SLOTS = "no_slots"
    NO_RESPONSE = "no_response"


# Interview statuses (existing convention in routes/interview_routes.py).
ACTIVE_INTERVIEW_STATUSES = frozenset({"Scheduled", "Rescheduled", "Email Sent"})
INTERVIEW_CANCELLED = frozenset({"Cancelled", "cancelled", "canceled"})

ATTENDANCE_ATTENDED = "attended"
ATTENDANCE_NO_SHOW = "no_show"
ATTENDANCE_VALUES = frozenset({ATTENDANCE_ATTENDED, ATTENDANCE_NO_SHOW})


def interview_is_active(interview: dict) -> bool:
    return str(interview.get("status") or "") in ACTIVE_INTERVIEW_STATUSES
