"""
Parse JSON from LLM text responses (including fenced or embedded JSON).
"""

from __future__ import annotations

import json
import re
from typing import Any


def parse_json_response(raw: str) -> dict[str, Any]:
    """
    Parse a dictionary from LLM output.

    Handles plain JSON, markdown code fences, and embedded JSON objects.
    """
    text = (raw or "").strip()
    if not text:
        return {}

    candidates: list[str] = [text]

    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence_match:
        candidates.insert(0, fence_match.group(1).strip())

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        object_match = re.search(r"\{[\s\S]*\}", candidate)
        if object_match:
            try:
                parsed = json.loads(object_match.group())
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

    return {}
