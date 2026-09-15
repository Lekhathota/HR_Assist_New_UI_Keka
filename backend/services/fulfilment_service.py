"""Automated bench screening and vendor shortage calculations."""
from __future__ import annotations

from typing import Any, Callable

import database as db
from services.candidate_service import SELECTION_MATCH_THRESHOLD


def calculate_remaining_requirement(total_required: int, selected_bench: int, accepted_vendor: int) -> int:
    """Return the outstanding requirement without allowing negative shortages."""
    total = int(total_required or 0)
    if total <= 0:
        raise ValueError("required_candidate_count must be greater than zero")
    return max(total - int(selected_bench or 0) - int(accepted_vendor or 0), 0)


def _jd(jd_id: int) -> dict[str, Any]:
    jd = db.get_jd_by_id(int(jd_id), include_raw_text=False)
    if not jd:
        raise ValueError("JD not found")
    count = jd.get("required_candidate_count")
    if count is None or int(count) <= 0:
        raise ValueError("required_candidate_count must be greater than zero")
    return jd


def _summary(jd: dict[str, Any], selected: int, analyzed: int, qualified: int, accepted: int) -> dict[str, Any]:
    remaining = calculate_remaining_requirement(int(jd["required_candidate_count"]), selected, accepted)
    return {
        "total_required": int(jd["required_candidate_count"]),
        "bench_matched_count": int(jd.get("bench_matched_count") or 0),
        "bench_analyzed_count": analyzed,
        "bench_qualified_count": qualified,
        "selected_bench_count": selected,
        "accepted_vendor_count": accepted,
        "remaining_vendor_requirement": remaining,
        "workflow_status": jd.get("workflow_status") or "ACTIVE",
    }


def get_fulfilment(jd_id: int) -> dict[str, Any]:
    jd = _jd(jd_id)
    selected = db.count_selected_bench_candidates(jd_id)
    accepted = db.count_accepted_vendor_candidates(jd_id)
    remaining = calculate_remaining_requirement(int(jd["required_candidate_count"]), selected, accepted)
    return _summary(jd, selected, int(jd.get("bench_analyzed_count") or 0), int(jd.get("bench_qualified_count") or 0), accepted) | {
        "remaining_vendor_requirement": remaining,
    }


def recalculate_fulfilment(jd_id: int) -> dict[str, Any]:
    """Rebuild persisted counters from comparison state without re-running AI."""
    jd = _jd(jd_id)
    selected = db.count_selected_bench_candidates(jd_id)
    accepted = db.count_accepted_vendor_candidates(jd_id)
    comparisons = db.get_comparisons(jd_id=jd_id)
    analyzed = sum(1 for row in comparisons if row.get("candidate_source") == "bench")
    qualified = sum(1 for row in comparisons if row.get("candidate_source") == "bench" and row.get("qualification_status") == "qualified")
    summary = _summary(jd, selected, analyzed, qualified, accepted)
    status = "REQUIREMENT_FULFILLED" if summary["remaining_vendor_requirement"] == 0 else "BENCH_PARTIALLY_FULFILLED"
    db.update_jd(jd_id, {**summary, "workflow_status": status, "workflow_version": int(jd.get("workflow_version") or 1) + 1})
    return {**summary, "workflow_status": status}


def accept_vendor_candidate(jd_id: int, candidate_id: int) -> dict[str, Any]:
    _jd(jd_id)
    candidate = db.get_candidate_by_id(int(candidate_id))
    if not candidate or int(candidate.get("jd_id") or 0) != int(jd_id) or not candidate.get("source_vendor_id"):
        raise ValueError("Vendor candidate was not found for this JD")
    if not db.update_comparison_metadata(jd_id, candidate_id, {
        "candidate_source": "vendor",
        "selection_status": "accepted_vendor",
        "qualification_status": "qualified",
    }):
        raise ValueError("Vendor candidate has no comparison record")
    return recalculate_fulfilment(jd_id)


def discover_bench_candidates(jd_id: int) -> list[dict[str, Any]]:
    jd = _jd(jd_id)
    category = str(jd.get("job_category") or "").strip()
    if not category or category.lower() in {"others", "unknown"}:
        db.update_jd(jd_id, {"workflow_status": "CATEGORY_REVIEW_REQUIRED"})
        raise ValueError("JD category must be reviewed before bench analysis")
    db.update_jd(jd_id, {"workflow_status": "BENCH_FILTERING"})
    candidates = db.get_available_bench_candidates_for_category(category, jd.get("project_id"))
    db.update_jd(jd_id, {"bench_matched_count": len(candidates), "workflow_status": "BENCH_ANALYSIS_IN_PROGRESS"})
    if hasattr(db, "log_audit"):
        db.log_audit("Bench Query Completed", "", f"Found {len(candidates)} available bench candidates for category {category}.", jd_id)
    return candidates


def apply_bench_selection(jd_id: int, ranked: list[dict[str, Any]], run_id: str = "") -> dict[str, Any]:
    jd = _jd(jd_id)
    bench_rows = [row for row in ranked if row.get("candidate_source") in {None, "bench", "existing"}]
    qualified = [row for row in bench_rows if int(row.get("match_score") or 0) >= SELECTION_MATCH_THRESHOLD]
    required = int(jd["required_candidate_count"])
    selected_ids = {int(row["id"]) for row in qualified[:required] if row.get("id") is not None}
    selected, waitlisted, rejected = [], [], []
    for row in bench_rows:
        candidate_id = int(row.get("id") or 0)
        score = int(row.get("match_score") or 0)
        if candidate_id in selected_ids:
            selection_status = "selected_bench"
            selected.append(row)
        elif score >= SELECTION_MATCH_THRESHOLD:
            selection_status = "waitlisted_bench"
            waitlisted.append(row)
        else:
            selection_status = "rejected"
            rejected.append(row)
        db.update_comparison_metadata(jd_id, candidate_id, {
            "candidate_source": "bench",
            "selection_status": selection_status,
            "qualification_status": "qualified" if score >= SELECTION_MATCH_THRESHOLD else "unqualified",
            "analysis_run_id": run_id,
        })
        if hasattr(db, "log_audit"):
            db.log_audit("Bench Candidate Classified", "", f"Candidate id={candidate_id} marked {selection_status}.", jd_id, run_id=run_id)
    selected_count = db.count_selected_bench_candidates(jd_id)
    accepted_count = db.count_accepted_vendor_candidates(jd_id)
    summary = _summary(jd, selected_count, len(bench_rows), len(qualified), accepted_count)
    status = "BENCH_FULLY_FULFILLED" if summary["remaining_vendor_requirement"] == 0 else "BENCH_PARTIALLY_FULFILLED"
    db.update_jd(jd_id, {**summary, "workflow_status": status})
    return {"selected": selected, "waitlisted": waitlisted, "rejected": rejected, "fulfilment_summary": {**summary, "workflow_status": status}}


def run_automated_bench_workflow(jd_id: int, username: str = "", runner: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    """Discover, screen, rank, and persist bench fulfilment for one JD."""
    candidates = discover_bench_candidates(jd_id)
    if not candidates:
        result = apply_bench_selection(jd_id, [], "")
        return {"run_id": "", "bench_results": result, "fulfilment_summary": result["fulfilment_summary"], "vendor_assignments": _assign_shortage(jd_id, result["fulfilment_summary"], username)}
    if runner is None:
        from orchestration.main_orchestrator import run_main_orchestrator
        runner = run_main_orchestrator
    result = runner({"task_type": "screening", "jd_id": int(jd_id), "candidate_ids": [c["id"] for c in candidates], "resume_items": [], "auto_bench": True}, username=username)
    applied = apply_bench_selection(jd_id, result.get("ranked_candidates") or [], result.get("run_id") or "")
    return {
        "run_id": result.get("run_id") or "",
        "bench_results": applied,
        "fulfilment_summary": applied["fulfilment_summary"],
        "vendor_assignments": _assign_shortage(jd_id, applied["fulfilment_summary"], username),
        "summary": result.get("summary") or {},
    }


def _assign_shortage(jd_id: int, summary: dict[str, Any], username: str) -> list[dict[str, Any]]:
    remaining = int(summary.get("remaining_vendor_requirement") or 0)
    if remaining <= 0:
        if hasattr(db, "log_audit"):
            db.log_audit("Bench Fully Fulfilled", username, f"No vendor shortage remains for JD id={jd_id}.", jd_id)
        return []
    jd = _jd(jd_id)
    vendors = db.get_eligible_vendors_for_category(str(jd.get("job_category") or ""))
    if not vendors:
        db.update_jd(jd_id, {"workflow_status": "BENCH_PARTIALLY_FULFILLED"})
        if hasattr(db, "log_audit"):
            db.log_audit("No Eligible Vendors", username, f"No active vendors support category {jd.get('job_category') or ''}.", jd_id)
        return []
    allocation_counts = {int(vendor["id"]): 0 for vendor in vendors}
    vendor_ids = list(allocation_counts)
    for index in range(remaining):
        allocation_counts[vendor_ids[index % len(vendor_ids)]] += 1
    allocation = {
        vendor_id: {
            "total_required_count": int(summary["total_required"]),
            "bench_fulfilled_count": int(summary["selected_bench_count"]),
            "remaining_requirement_at_assignment": remaining,
            "allocated_count": count,
            "accepted_count": 0,
            "assignment_source": "automated_shortage",
            "delivery_status": "pending",
        }
        for vendor_id, count in allocation_counts.items()
        if count > 0
    }
    current_vendor_ids = [int(row.get("id") or 0) for row in db.get_jd_vendor_assignments(jd_id)]
    assignments = db.assign_vendors_to_jd(jd_id, list(dict.fromkeys([*current_vendor_ids, *allocation.keys()])), allocation=allocation)
    db.update_jd(jd_id, {"workflow_status": "AWAITING_VENDOR_SUBMISSIONS"})
    if hasattr(db, "log_audit"):
        db.log_audit("Vendor Shortage Assigned", username, f"Assigned remaining shortage of {remaining} across {len(allocation)} eligible vendor(s).", jd_id)
    return assignments
