"""Shared email helpers."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("recruitment.email")

_INVISIBLE_EMAIL_CHARS = ("\u200b", "\u200c", "\u200d", "\ufeff", "\u00a0")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str | None) -> str:
    """Strip whitespace and invisible Unicode characters that break SMTP delivery."""
    cleaned = str(value or "").strip()
    for ch in _INVISIBLE_EMAIL_CHARS:
        cleaned = cleaned.replace(ch, "")
    return cleaned.strip()


def is_valid_email(value: str | None) -> bool:
    email = normalize_email(value)
    return bool(email and _EMAIL_RE.match(email))
