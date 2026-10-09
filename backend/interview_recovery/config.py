"""Environment-driven settings for interview reschedule and no-show recovery.

Every value has a safe default and is validated; an invalid value raises a
clear error instead of silently changing retry or escalation behaviour.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

NO_SHOW_MODES = {"confirmed", "auto"}


class RecoveryConfigError(ValueError):
    """Raised when an INTERVIEW_* recovery setting is invalid."""


def _int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RecoveryConfigError(f"{name} must be a whole number.") from exc
    if not minimum <= value <= maximum:
        raise RecoveryConfigError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RecoveryConfigError(f"{name} must be true or false.")


@dataclass(frozen=True)
class RecoveryConfig:
    enabled: bool = True
    no_show_grace_minutes: int = 15
    no_show_mode: str = "confirmed"
    no_show_lookback_hours: int = 48
    max_attempts: int = 3
    response_timeout_minutes: int = 1440
    retry_delay_minutes: int = 60
    max_delivery_failures: int = 5
    slot_search_days: int = 10
    slot_count: int = 3
    slot_step_minutes: int = 30
    min_notice_hours: int = 12
    workday_start_hour: int = 9
    workday_end_hour: int = 18
    workdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    timezone: str = "UTC"
    lease_seconds: int = 300

    @property
    def tz(self) -> tzinfo:
        return _zone(self.timezone)


def _zone(name: str) -> tzinfo:
    # UTC needs no tz database (Windows without the tzdata package has none).
    return timezone.utc if name.upper() == "UTC" else ZoneInfo(name)


def load_config() -> RecoveryConfig:
    tz_name = (os.environ.get("INTERVIEW_TIMEZONE") or "UTC").strip()
    try:
        _zone(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise RecoveryConfigError("INTERVIEW_TIMEZONE must be an IANA time zone such as Asia/Kolkata.") from exc

    mode = (os.environ.get("INTERVIEW_NO_SHOW_DETECTION") or "confirmed").strip().lower()
    if mode not in NO_SHOW_MODES:
        raise RecoveryConfigError("INTERVIEW_NO_SHOW_DETECTION must be 'confirmed' or 'auto'.")

    raw_days = (os.environ.get("INTERVIEW_RECOVERY_WORKDAYS") or "0,1,2,3,4").strip()
    try:
        workdays = tuple(sorted({int(day) for day in raw_days.split(",") if day.strip()}))
    except ValueError as exc:
        raise RecoveryConfigError("INTERVIEW_RECOVERY_WORKDAYS must be weekday numbers 0 (Mon) to 6 (Sun).") from exc
    if not workdays or any(day < 0 or day > 6 for day in workdays):
        raise RecoveryConfigError("INTERVIEW_RECOVERY_WORKDAYS must be weekday numbers 0 (Mon) to 6 (Sun).")

    start = _int("INTERVIEW_RECOVERY_WORKDAY_START_HOUR", 9, 0, 23)
    end = _int("INTERVIEW_RECOVERY_WORKDAY_END_HOUR", 18, 1, 24)
    if end <= start:
        raise RecoveryConfigError("INTERVIEW_RECOVERY_WORKDAY_END_HOUR must be after the start hour.")

    return RecoveryConfig(
        enabled=_bool("INTERVIEW_RECOVERY_ENABLED", True),
        no_show_grace_minutes=_int("INTERVIEW_NO_SHOW_GRACE_MINUTES", 15, 0, 1440),
        no_show_mode=mode,
        no_show_lookback_hours=_int("INTERVIEW_NO_SHOW_LOOKBACK_HOURS", 48, 1, 720),
        max_attempts=_int("INTERVIEW_RECOVERY_MAX_ATTEMPTS", 3, 1, 20),
        response_timeout_minutes=_int("INTERVIEW_RECOVERY_RESPONSE_TIMEOUT_MINUTES", 1440, 5, 20160),
        retry_delay_minutes=_int("INTERVIEW_RECOVERY_RETRY_DELAY_MINUTES", 60, 1, 10080),
        max_delivery_failures=_int("INTERVIEW_RECOVERY_MAX_DELIVERY_FAILURES", 5, 1, 50),
        slot_search_days=_int("INTERVIEW_RECOVERY_SLOT_SEARCH_DAYS", 10, 1, 60),
        slot_count=_int("INTERVIEW_RECOVERY_SLOT_COUNT", 3, 1, 10),
        slot_step_minutes=_int("INTERVIEW_RECOVERY_SLOT_STEP_MINUTES", 30, 5, 240),
        min_notice_hours=_int("INTERVIEW_RECOVERY_MIN_NOTICE_HOURS", 12, 0, 336),
        workday_start_hour=start,
        workday_end_hour=end,
        workdays=workdays,
        timezone=tz_name,
        lease_seconds=_int("INTERVIEW_RECOVERY_LEASE_SECONDS", 300, 30, 3600),
    )
