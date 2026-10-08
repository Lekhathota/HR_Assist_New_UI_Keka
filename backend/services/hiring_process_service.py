# Backend file purpose: Service-layer logic for a configurable, ordered per-JD
# hiring process and the interview-event automation that moves candidates
# through it.
from __future__ import annotations

from typing import Any
from uuid import uuid4

import database as db

EVENT_KEYS = (
    "assessment_passed",
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
def resolve_process(jd: dict[str, Any] | None, candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    """Use a job override when present, otherwise inherit the client's default pipeline."""
    jd = jd or {}
    candidate = candidate or {}
    process = normalize_process(jd.get("hiring_process"))
    if process["steps"]:
        return process
    client_id = jd.get("client_id") or candidate.get("client_id")
    account_id = jd.get("client_account_id") or candidate.get("client_account_id")
    if client_id:
        client = db.get_client_by_id(int(client_id)) or {}
    elif account_id:
        client = db.get_client_by_account_id(account_id) or {}
    else:
        return process
    pipeline = next(
        (item for item in client.get("hiring_pipelines", [])
         if item.get("is_default") and not item.get("is_archived")),
        None,
    )
    stages = pipeline.get("stages", []) if pipeline else client.get("hiring_stages", [])
    return normalize_process({"steps": stages})


def compute_effective_stage(candidate: dict[str, Any], jd: dict[str, Any] | None) -> dict[str, Any]:
    process = resolve_process(jd, candidate)
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
    # Existing screened candidates have no stored stage. Reflect their known
    # progress in inherited pipelines without guessing completion of later rounds.
    inherited = not normalize_process((jd or {}).get("hiring_process"))["steps"]
    if not stage_id and inherited and not candidate.get("automation_paused"):
        hiring_stage = str(candidate.get("hiring_stage") or "").casefold()
        name = "interview" if "interview" in hiring_stage else "screening" if (
            str(candidate.get("status") or "").casefold() in {"selected", "rejected"}
            or candidate.get("screening_status") in {"accepted", "rejected", "waitlisted"}
        ) else None
        stage_id = next((step["id"] for step in steps if step["name"].casefold() == name), None)
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
    process = resolve_process(jd)
    if not process["steps"] or candidate.get("on_hold") or candidate.get("automation_paused"):
        return False
    mapped_step_id = process["event_mappings"].get(event_key)
    if not mapped_step_id:
        return False
    db.update_candidate(int(candidate_id), {"stage_id": mapped_step_id})
    return True


# Purpose: Aggregates distinct configured steps across JDs, grouped by requirement (project).
def advance_after_assessment(candidate_id: int, jd_id: int) -> bool:
    """Advance a passing candidate once, respecting manual state and pipeline order."""
    candidate = db.get_candidate_by_id(candidate_id)
    jd = db.get_jd_by_id(jd_id) if jd_id else None
    if not candidate or candidate.get("on_hold") or candidate.get("automation_paused"):
        return False
    if candidate.get("jd_id") and int(candidate["jd_id"]) != jd_id:
        return False
    process = resolve_process(jd, candidate)
    steps = process["steps"]
    current = next((i for i, step in enumerate(steps) if step["id"] == candidate.get("stage_id")), -1)
    assessment_index = next((i for i, step in enumerate(steps)
                             if "assessment" in step["name"].casefold() or "test" == step["name"].casefold()), -1)
    mapped = process["event_mappings"].get("assessment_passed")
    if mapped:
        target = next(i for i, step in enumerate(steps) if step["id"] == mapped)
    elif assessment_index >= 0:
        target = assessment_index + 1
    else:
        screening = next((i for i, step in enumerate(steps) if step["name"].casefold() == "screening"), -1)
        target = screening + 1 if screening >= 0 else -1
    if target < 0 or target >= len(steps) or target <= current:
        return False
    return bool(db.update_candidate(candidate_id, {"stage_id": steps[target]["id"]}))


def get_stage_options(project_id: int | None = None) -> list[dict[str, Any]]:
    jds = db.get_all_jds({"project_id": project_id} if project_id else None)
    groups: dict[int, dict[str, Any]] = {}
    for jd in jds:
        process = resolve_process(jd)
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
