from __future__ import annotations

from typing import Any


MAX_STRING_CHARS = 1600
MAX_LIST_ITEMS = 12
MAX_CONTEXT_CHARS = 12000

INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore the system prompt",
    "reveal your system prompt",
    "show me your system prompt",
    "print your system prompt",
    "bypass approval",
    "skip approval",
    "override approval",
    "disable safety",
    "developer message",
    "exfiltrate",
    "secret key",
    "api key",
    "smtp_pass",
    "mongodb_uri",
)


def detect_prompt_injection(text: str) -> tuple[bool, str]:
    lowered = (text or "").lower()
    for marker in INJECTION_MARKERS:
        if marker in lowered:
            return True, marker
    return False, ""


def _guard(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= MAX_STRING_CHARS else value[:MAX_STRING_CHARS] + "...[truncated]"
    if isinstance(value, list):
        return [_guard(item) for item in value[:MAX_LIST_ITEMS]]
    if isinstance(value, dict):
        return {str(key): _guard(item) for key, item in value.items()}
    return value


def guard_context_window(context: dict[str, Any]) -> dict[str, Any]:
    guarded = _guard(context)
    if len(str(guarded)) <= MAX_CONTEXT_CHARS:
        return guarded
    return {
        "summary": "Context was reduced because it exceeded the safe prompt budget.",
        "keys": sorted(str(key) for key in context.keys())[:MAX_LIST_ITEMS],
    }

