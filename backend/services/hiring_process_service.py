# Backend file purpose: Service-layer logic for a configurable, ordered per-JD
# hiring process and the interview-event automation that moves candidates
# through it.
from __future__ import annotations

from typing import Any
from uuid import uuid4

import database as db

EVENT_KEYS = (
    "scheduled",
    "rescheduled",
    "selected_after_interview",
    "rejected_after_interview",
    "cancelled",
)


# Purpose: Tolerant read-time normalization of a JD's stored hiring_process.
def normalize_process(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
    clean_steps: list[dict[str, str]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        name = str(step.get("name") or "").strip()
        step_id = str(step.get("id") or "").strip()
        if not name or not step_id:
            continue
        clean_steps.append({"id": step_id, "name": name})
    valid_ids = {step["id"] for step in clean_steps}
    raw_mappings = raw.get("event_mappings") if isinstance(raw.get("event_mappings"), dict) else {}
    mappings = {key: (raw_mappings.get(key) if raw_mappings.get(key) in valid_ids else None) for key in EVENT_KEYS}
    return {"steps": clean_steps, "event_mappings": mappings}


# Purpose: Assigns/validates step ids for a save request; does not touch mappings.
def build_steps(raw_steps: Any) -> tuple[list[dict[str, str]], str | None]:
    if not isinstance(raw_steps, list) or not raw_steps:
        return [], "At least one hiring-process step is required."
    seen_ids: set[str] = set()
    steps: list[dict[str, str]] = []
    for entry in raw_steps:
        if not isinstance(entry, dict):
            return [], "Each step must be an object with a name."
        name = str(entry.get("name") or "").strip()
        if not name:
            return [], "Every step needs a non-empty name."
        step_id = str(entry.get("id") or "").strip() or uuid4().hex[:12]
        if step_id in seen_ids:
            step_id = uuid4().hex[:12]
        seen_ids.add(step_id)
        steps.append({"id": step_id, "name": name})
    return steps, None


# Purpose: Validates that every mapping value is null or an id present in steps.
def validate_mappings(steps: list[dict[str, str]], raw_mappings: Any) -> tuple[dict[str, str | None], str | None]:
    valid_ids = {step["id"] for step in steps}
    raw_mappings = raw_mappings if isinstance(raw_mappings, dict) else {}
    mappings: dict[str, str | None] = {}
    for key in EVENT_KEYS:
        value = raw_mappings.get(key)
        if value in (None, ""):
            mappings[key] = None
            continue
        if value not in valid_ids:
            return {}, f"Event mapping '{key}' references a step that doesn't exist."
        mappings[key] = value
    return mappings, None


# Purpose: Rejects removing a step that's still referenced by a mapping or a linked candidate.
def validate_step_removal(
    jd_id: int,
    previous_steps: list[dict[str, str]],
    new_steps: list[dict[str, str]],
    raw_mappings: Any,
) -> str | None:
    new_ids = {step["id"] for step in new_steps}
    removed_ids = {step["id"] for step in previous_steps} - new_ids
    if not removed_ids:
        return None
    raw_mappings = raw_mappings if isinstance(raw_mappings, dict) else {}
    for key in EVENT_KEYS:
        if raw_mappings.get(key) in removed_ids:
            return f"Cannot remove a step that the '{key}' event is still mapped to. Update the mapping first."
    for removed_id in removed_ids:
        if db.get_all_candidates({"jd_id": int(jd_id), "stage_id": removed_id}):
            return "Cannot remove a step that candidates are currently on. Move them to another stage first."
    return None


# Purpose: Resolves the display-ready effective hiring stage for one candidate.
def compute_effective_stage(candidate: dict[str, Any], jd: dict[str, Any] | None) -> dict[str, Any]:
    process = normalize_process((jd or {}).get("hiring_process"))
    steps = process["steps"]
    if not steps:
        return {
            "configured": False,
            "stage_id": None,
            "stage_name": None,
            "on_hold": bool(candidate.get("on_hold")),
            "automation_paused": bool(candidate.get("automation_paused")),
            "steps": [],
        }
    stage_id = candidate.get("stage_id")
    stage_name = next((step["name"] for step in steps if step["id"] == stage_id), None) or "Not Started"
    return {
        "configured": True,
        "stage_id": stage_id,
        "stage_name": stage_name,
        "on_hold": bool(candidate.get("on_hold")),
        "automation_paused": bool(candidate.get("automation_paused")),
        "steps": steps,
    }


# Purpose: Moves a candidate to the step mapped to an interview event, unless blocked.
def apply_hiring_event(candidate_id: int, jd_id: int | None, event_key: str) -> bool:
    if event_key not in EVENT_KEYS or not jd_id:
        return False
    candidate = db.get_candidate_by_id(int(candidate_id))
    jd = db.get_jd_by_id(int(jd_id))
    if not candidate or not jd:
        return False
    process = normalize_process(jd.get("hiring_process"))
    if not process["steps"] or candidate.get("on_hold") or candidate.get("automation_paused"):
        return False
    mapped_step_id = process["event_mappings"].get(event_key)
    if not mapped_step_id:
        return False
    db.update_candidate(int(candidate_id), {"stage_id": mapped_step_id})
    return True


# Purpose: Aggregates distinct configured steps across JDs, grouped by requirement (project).
def get_stage_options(project_id: int | None = None) -> list[dict[str, Any]]:
    jds = db.get_all_jds({"project_id": project_id} if project_id else None)
    groups: dict[int, dict[str, Any]] = {}
    for jd in jds:
        process = normalize_process(jd.get("hiring_process"))
        if not process["steps"]:
            continue
        pid = int(jd.get("project_id") or 0)
        group = groups.setdefault(pid, {"project_id": pid or None, "project_name": jd.get("project_name") or "", "steps": []})
        existing_ids = {step["id"] for step in group["steps"]}
        for step in process["steps"]:
            if step["id"] not in existing_ids:
                group["steps"].append(step)
                existing_ids.add(step["id"])
    return list(groups.values())
