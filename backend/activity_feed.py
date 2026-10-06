# Backend file purpose: Turns Hire-panel actions (JDs, resumes, screening, pipeline,
# interviews, assessments) into top-bar notifications.
#
# Write functions in database.py / assessment.repository call emit(). Events are
# buffered per HTTP request and flushed once by app.after_request, so one user
# action becomes one grouped notification (e.g. "10 resumes uploaded") and failed
# requests produce nothing. Writes outside a request (seed/import scripts) are ignored.
from __future__ import annotations

import logging
import uuid
from collections import OrderedDict
from typing import Any, Optional

from flask import g, has_request_context

logger = logging.getLogger(__name__)

_BUFFER_KEY = "_ra_activity_events"


def emit(kind: str, **fields: Any) -> None:
    """Record an activity event for the current request."""
    if not has_request_context():
        return
    events = g.get(_BUFFER_KEY)
    if events is None:
        events = []
        setattr(g, _BUFFER_KEY, events)
    events.append({"kind": kind, **fields})


def discard() -> None:
    if has_request_context():
        setattr(g, _BUFFER_KEY, [])


def pending() -> list[dict]:
    return list(g.get(_BUFFER_KEY) or []) if has_request_context() else []


def flush(user: Optional[dict]) -> int:
    """Write the buffered events as notifications. Returns the number created."""
    events = pending()
    discard()
    if not events:
        return 0
    import database as db  # Lazy import: database.py imports this module.

    actor = (user or {}).get("username") or ""
    try:
        db.record_activity_events(events, user, uuid.uuid4().hex)
    except Exception:  # Stats are secondary; notifications must still be written.
        logger.exception("Could not record activity events")
    notes = build_notifications(events, actor, _jd_titles(db, events))
    for note in notes:
        db.create_notification(
            note["type"], note["title"], note["message"],
            jd_id=note.get("jd_id"), link=note.get("link"), actor=actor or None,
        )
    return len(notes)


def _jd_titles(db, events: list[dict]) -> dict[int, str]:
    ids = {int(e["jd_id"]) for e in events if e.get("jd_id") not in (None, "") and not e.get("jd_title")}
    titles = {int(e["jd_id"]): e["jd_title"] for e in events if e.get("jd_id") not in (None, "") and e.get("jd_title")}
    if ids - set(titles):
        try:
            for row in db.get_database().job_descriptions.find({"id": {"$in": list(ids - set(titles))}}, {"id": 1, "title": 1}):
                titles[int(row["id"])] = row.get("title") or f"JD #{row['id']}"
        except Exception:  # Titles are cosmetic; never fail the flush over them.
            logger.exception("Could not load JD titles for notifications")
    return titles


def _plural(count: int, word: str, plural: Optional[str] = None) -> str:
    return f"{count} {word if count == 1 else (plural or word + 's')}"


def _by(actor: str) -> str:
    return f" by {actor}" if actor else ""


def build_notifications(events: list[dict], actor: str, titles: dict[int, str]) -> list[dict]:
    """Group one request's events into notification payloads (pure function)."""
    def title_of(jd_id: Any) -> str:
        if jd_id in (None, ""):
            return ""
        return titles.get(int(jd_id)) or f"JD #{jd_id}"

    def jd_suffix(jd_id: Any) -> str:
        name = title_of(jd_id)
        return f" for {name}" if name else ""

    kinds = {e["kind"] for e in events}
    created_jds = {e["jd_id"] for e in events if e["kind"] == "jd_created"}
    status_jds = {e["jd_id"] for e in events if e["kind"] == "jd_status"}
    screened_jds = {e.get("jd_id") for e in events if e["kind"] == "screening"}
    new_candidates = {e["candidate_id"] for e in events if e["kind"] == "resume_uploaded"}

    # Merge repeated events for the same subject; the latest value wins.
    def unique(kind: str, key) -> list[dict]:
        rows: "OrderedDict[Any, dict]" = OrderedDict()
        for event in events:
            if event["kind"] == kind:
                rows[key(event)] = event
        return list(rows.values())

    notes: list[dict] = []

    for e in unique("jd_created", lambda e: e["jd_id"]):
        notes.append({"type": "jd_created", "title": "New JD uploaded", "jd_id": e["jd_id"], "link": f"/jobs/{e['jd_id']}",
                      "message": f"{title_of(e['jd_id'])} was added to Jobs{_by(actor)}."})

    for e in unique("jd_status", lambda e: e["jd_id"]):
        if e["jd_id"] in created_jds:
            continue
        notes.append({"type": "jd_status", "title": "JD status changed", "jd_id": e["jd_id"], "link": f"/jobs/{e['jd_id']}",
                      "message": f"{title_of(e['jd_id'])} moved from {e.get('old') or 'Unknown'} to {e.get('new')}{_by(actor)}."})

    for e in unique("jd_updated", lambda e: e["jd_id"]):
        if e["jd_id"] in created_jds or e["jd_id"] in status_jds:
            continue
        notes.append({"type": "jd_updated", "title": "JD updated", "jd_id": e["jd_id"], "link": f"/jobs/{e['jd_id']}",
                      "message": f"{title_of(e['jd_id'])} details were updated{_by(actor)}."})

    for e in unique("jd_deleted", lambda e: e["jd_id"]):
        notes.append({"type": "jd_deleted", "title": "JD deleted", "jd_id": None, "link": "/jobs",
                      "message": f"{e.get('jd_title') or 'A job description'} was deleted{_by(actor)}."})

    for e in unique("jd_vendors_assigned", lambda e: e["jd_id"]):
        count = int(e.get("count") or 0)
        notes.append({"type": "jd_vendors_assigned", "title": "Vendors assigned", "jd_id": e["jd_id"], "link": f"/jobs/{e['jd_id']}",
                      "message": f"{_plural(count, 'vendor')} assigned to {title_of(e['jd_id'])}{_by(actor)}."})

    # Resumes: one notification per JD (or one for unassigned uploads).
    uploads: "OrderedDict[Any, list[dict]]" = OrderedDict()
    for e in unique("resume_uploaded", lambda e: e["candidate_id"]):
        uploads.setdefault(e.get("jd_id"), []).append(e)
    for jd_id, rows in uploads.items():
        if len(rows) == 1:
            row = rows[0]
            notes.append({"type": "resume_uploaded", "title": "Resume uploaded", "jd_id": jd_id, "link": f"/talent/{row['candidate_id']}",
                          "message": f"{row.get('name') or 'A candidate'} was added to Talent{jd_suffix(jd_id)}{_by(actor)}."})
        else:
            notes.append({"type": "resume_uploaded", "title": f"{len(rows)} resumes uploaded", "jd_id": jd_id, "link": "/talent",
                          "message": f"{_plural(len(rows), 'candidate')} added to Talent{jd_suffix(jd_id)}{_by(actor)}."})

    removed = unique("candidate_deleted", lambda e: e["candidate_id"])
    if len(removed) == 1:
        notes.append({"type": "candidate_deleted", "title": "Candidate removed", "jd_id": None, "link": "/talent",
                      "message": f"{removed[0].get('name') or 'A candidate'} was removed from Talent{_by(actor)}."})
    elif removed:
        notes.append({"type": "candidate_deleted", "title": f"{len(removed)} candidates removed", "jd_id": None, "link": "/talent",
                      "message": f"{_plural(len(removed), 'candidate')} were removed from Talent{_by(actor)}."})

    # Screening results: one summary per JD.
    screening: "OrderedDict[Any, list[dict]]" = OrderedDict()
    for e in unique("screening", lambda e: (e.get("jd_id"), e.get("candidate_id"))):
        screening.setdefault(e.get("jd_id"), []).append(e)
    for jd_id, rows in screening.items():
        selected = sum(1 for r in rows if str(r.get("status")).lower() == "selected")
        rejected = sum(1 for r in rows if str(r.get("status")).lower() == "rejected")
        parts = [f"{selected} selected"] + ([f"{rejected} rejected"] if rejected else [])
        notes.append({"type": "screening", "title": "Screening completed", "jd_id": jd_id, "link": f"/jobs/{jd_id}" if jd_id else "/talent",
                      "message": f"{_plural(len(rows), 'candidate')} analysed{jd_suffix(jd_id)}: {', '.join(parts)}."})

    for e in unique("candidate_status", lambda e: e["candidate_id"]):
        if e.get("jd_id") in screened_jds or e["candidate_id"] in new_candidates:
            continue
        notes.append({"type": "candidate_status", "title": "Candidate status updated", "jd_id": e.get("jd_id"), "link": f"/talent/{e['candidate_id']}",
                      "message": f"{e.get('name') or 'A candidate'} is now {e.get('new')}{jd_suffix(e.get('jd_id'))}{_by(actor)}."})

    for e in unique("candidate_stage", lambda e: e["candidate_id"]):
        if e["candidate_id"] in new_candidates:
            continue
        notes.append({"type": "candidate_stage", "title": "Pipeline stage changed", "jd_id": e.get("jd_id"), "link": f"/talent/{e['candidate_id']}",
                      "message": f"{e.get('name') or 'A candidate'} moved to {e.get('stage') or 'a new stage'}{jd_suffix(e.get('jd_id'))}{_by(actor)}."})

    for e in unique("candidate_hold", lambda e: e["candidate_id"]):
        state = "put on hold" if e.get("on_hold") else "taken off hold"
        notes.append({"type": "candidate_hold", "title": "Candidate " + ("on hold" if e.get("on_hold") else "resumed"), "jd_id": e.get("jd_id"),
                      "link": f"/talent/{e['candidate_id']}", "message": f"{e.get('name') or 'A candidate'} was {state}{jd_suffix(e.get('jd_id'))}{_by(actor)}."})

    interview_titles = {"Scheduled": "Interview scheduled", "Rescheduled": "Interview rescheduled", "Cancelled": "Interview cancelled",
                        "Completed": "Interview completed", "No Show": "Interview no-show"}
    for e in unique("interview", lambda e: (e.get("candidate_id"), e.get("jd_id"))):
        status = e.get("status") or "Scheduled"
        subject = f"Interview with {e.get('name') or 'the candidate'}{jd_suffix(e.get('jd_id'))}"
        if status == "Scheduled":
            detail = f"scheduled for {e['when']}" if e.get("when") else "scheduled"
        elif status == "Rescheduled":
            detail = f"moved to {e['when']}" if e.get("when") else "rescheduled"
        else:
            detail = f"marked {status.lower()}"
        notes.append({"type": "interview", "title": interview_titles.get(status, f"Interview {status.lower()}"), "jd_id": e.get("jd_id"),
                      "link": "/hiring-pipeline", "message": f"{subject} {detail}{_by(actor)}."})

    assessment_text = {
        "CREATED": ("Assessment created", "An assessment was created for {name}{jd}{by}."),
        "SENT": ("Assessment sent", "The assessment was sent to {name}{jd}{by}."),
        "IN_PROGRESS": ("Assessment started", "{name} started the assessment{jd}."),
        "COMPLETED": ("Assessment submitted", "{name} submitted the assessment{jd}."),
        "PASSED": ("Assessment passed", "{name} passed the assessment{jd}."),
        "FAILED": ("Assessment failed", "{name} did not pass the assessment{jd}."),
    }
    for e in unique("assessment", lambda e: e.get("assessment_id")):
        text = assessment_text.get(str(e.get("status")).upper())
        if not text:
            continue
        title, template = text
        notes.append({"type": "assessment", "title": title, "jd_id": e.get("jd_id"), "link": "/hiring-pipeline",
                      "message": template.format(name=e.get("name") or "The candidate", jd=jd_suffix(e.get("jd_id")), by=_by(actor))})

    report_labels = {"jobs": "Jobs", "job_details": "Job details", "talent": "Talent", "candidate_profile": "Candidate profile",
                     "analytics": "Analytics"}
    for e in unique("report_generated", lambda e: e.get("report_id")):
        label = report_labels.get(e.get("scope"), "Hiring")
        fmt = str(e.get("format") or "").upper()
        notes.append({"type": "report_generated", "title": "Report generated", "jd_id": e.get("jd_id"), "link": None,
                      "message": f"{label} report {e.get('report_id')}{' (' + fmt + ')' if fmt else ''} was generated{_by(actor)}."})

    if not notes and kinds:
        logger.debug("Activity events produced no notifications: %s", sorted(kinds))
    return notes
