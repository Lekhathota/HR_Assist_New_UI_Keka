# Backend file purpose: Tool/helper functions used by agents and workflows for jd.
from __future__ import annotations

from typing import Any

import database as db
from services.matching_service import _normalized_jd_payload


# Purpose: Loads jd context for later processing.
def load_jd_context(jd_id: int) -> dict[str, Any]:
    """Load a JD row and convert it into the normalized JSON shape used by matching."""
    jd_row = db.get_jd_by_id(int(jd_id), include_raw_text=True)
    if not jd_row:
        raise ValueError("JD not found.")
    return {"jd_row": jd_row, "jd_json": _normalized_jd_payload(jd_row)}
