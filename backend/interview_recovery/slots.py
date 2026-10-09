"""Mutual-availability slot search.

All datetimes here are naive local wall-clock times in the configured
INTERVIEW_TIMEZONE, matching how interview_start/interview_end are stored.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Iterable, Optional

from interview_recovery.config import RecoveryConfig


def slot_id(start: datetime) -> str:
    return start.strftime("%Y-%m-%dT%H:%M")


def slot_payload(start: datetime, end: datetime) -> dict:
    return {"id": slot_id(start), "start": start.isoformat(timespec="minutes"), "end": end.isoformat(timespec="minutes"),
            "label": f"{start.strftime('%a %d %b %Y, %H:%M')} - {end.strftime('%H:%M')}"}


def _overlaps(start: datetime, end: datetime, busy: Iterable[tuple[datetime, datetime]]) -> bool:
    return any(start < b_end and end > b_start for b_start, b_end in busy)


def _in_windows(start: datetime, end: datetime, windows: Optional[list[dict]]) -> bool:
    if not windows:
        return True
    for window in windows:
        try:
            day = datetime.fromisoformat(str(window["date"])).date()
            w_start = datetime.combine(day, time.fromisoformat(str(window.get("start") or "00:00")))
            w_end = datetime.combine(day, time.fromisoformat(str(window.get("end") or "23:59")))
        except (KeyError, TypeError, ValueError):
            continue
        if start >= w_start and end <= w_end:
            return True
    return False


def parse_preferred_windows(raw: object) -> list[dict]:
    """Validate candidate-supplied availability windows: [{date, start, end}]."""
    if raw in (None, "", []):
        return []
    if not isinstance(raw, list) or len(raw) > 14:
        raise ValueError("preferred_windows must be a list of up to 14 {date, start, end} entries.")
    windows = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each preferred window needs date, start and end.")
        try:
            day = datetime.fromisoformat(str(item.get("date"))).date()
            start = time.fromisoformat(str(item.get("start")))
            end = time.fromisoformat(str(item.get("end")))
        except (TypeError, ValueError) as exc:
            raise ValueError("Use date YYYY-MM-DD and start/end HH:MM for preferred windows.") from exc
        if end <= start:
            raise ValueError("Each preferred window must end after it starts.")
        windows.append({"date": day.isoformat(), "start": start.strftime("%H:%M"), "end": end.strftime("%H:%M")})
    return windows


def find_slots(
    config: RecoveryConfig,
    local_now: datetime,
    duration: timedelta,
    busy: list[tuple[datetime, datetime]],
    *,
    preferred_windows: Optional[list[dict]] = None,
    exclude_starts: Optional[set[str]] = None,
) -> list[dict]:
    """Return up to config.slot_count free slots, preferring one per day."""
    earliest = local_now + timedelta(hours=config.min_notice_hours)
    step = timedelta(minutes=config.slot_step_minutes)
    exclude_starts = exclude_starts or set()
    by_day: list[list[tuple[datetime, datetime]]] = []

    for offset in range(config.slot_search_days + 1):
        day = (local_now + timedelta(days=offset)).date()
        if day.weekday() not in config.workdays:
            continue
        day_start = datetime.combine(day, time(config.workday_start_hour))
        day_end = datetime.combine(day, time.min) + timedelta(hours=config.workday_end_hour)
        cursor = day_start
        free: list[tuple[datetime, datetime]] = []
        while cursor + duration <= day_end:
            end = cursor + duration
            if (cursor >= earliest and slot_id(cursor) not in exclude_starts
                    and not _overlaps(cursor, end, busy) and _in_windows(cursor, end, preferred_windows)):
                free.append((cursor, end))
            cursor += step
        if free:
            by_day.append(free)

    picked: list[tuple[datetime, datetime]] = []
    # Round-robin across days so candidates get genuinely different options.
    depth = 0
    while len(picked) < config.slot_count and any(depth < len(day) for day in by_day):
        for day in by_day:
            if depth < len(day) and len(picked) < config.slot_count:
                picked.append(day[depth])
        depth += 1
    picked.sort()
    return [slot_payload(start, end) for start, end in picked]
