# Backend file purpose: Finds the job/requisition ID written inside an uploaded JD.
#
# A labelled reference ("Job ID: REQ-1023", "Requisition # 45678", "Position Code - JR_2024/015")
# is matched deterministically. An ID suggested by the LLM is accepted only when that exact
# value appears in the document, so a hallucinated ID can never be stored.
from __future__ import annotations

import re

_LABELS = (
    r"job\s*(?:id|code|ref(?:erence)?(?:\s*(?:no\.?|number|id))?|no\.?|number|#)"
    r"|requisition(?:\s*(?:id|code|no\.?|number|#))?"
    r"|req\.?\s*(?:id|no\.?|number|#)"
    r"|position\s*(?:id|code|no\.?|number|#)"
    r"|vacancy\s*(?:id|code|ref(?:erence)?|no\.?|number|#)"
    r"|posting\s*(?:id|code|no\.?|number)"
    r"|opening\s*(?:id|code|no\.?|number)"
    r"|reference\s*(?:id|code|no\.?|number|#)"
    r"|ref\.?\s*(?:id|no\.?|number|#)"
    r"|jr\s*(?:id|no\.?|number|#)"
)
# Label, optional separator, then an ID-like token (letters/digits with - _ / . inside).
_PATTERN = re.compile(
    rf"\b(?:{_LABELS})\s*[:#\-–—=]?\s*#?\s*([A-Za-z0-9][A-Za-z0-9\-_/.]{{0,39}})",
    re.IGNORECASE,
)
_PLACEHOLDERS = {"na", "n/a", "tbd", "tba", "none", "nil", "null", "pending"}


def _clean(value: str) -> str:
    value = str(value or "").strip().strip(".,;:)(-_/")
    if not value or value.lower() in _PLACEHOLDERS:
        return ""
    if not re.search(r"\d", value):  # an ID always carries at least one digit
        return ""
    if value.isdigit() and len(value) < 3:  # "Vacancies: 3" is a count, not an ID
        return ""
    return value[:40]


def find_labelled_job_code(text: str) -> str:
    """Return the first labelled job/requisition ID in the text, or ''."""
    for match in _PATTERN.finditer(str(text or "")):
        value = _clean(match.group(1))
        if value:
            return value
    return ""


def verified_llm_job_code(value: str, *texts: str) -> str:
    """Accept an LLM-extracted ID only if it literally appears in the document."""
    candidate = _clean(value)
    if not candidate:
        return ""
    haystack = " ".join(str(t or "") for t in texts).lower()
    return candidate if candidate.lower() in haystack else ""


def extract_job_code(raw_text: str, cleaned_text: str = "", llm_value: str = "") -> str:
    """Job ID from the JD document: labelled match first, then a verified LLM value."""
    return (
        find_labelled_job_code(raw_text)
        or find_labelled_job_code(cleaned_text)
        or verified_llm_job_code(llm_value, raw_text, cleaned_text)
    )
