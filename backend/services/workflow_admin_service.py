from __future__ import annotations

from typing import Any

import database as db
from services.fulfilment_service import recalculate_fulfilment


PRIVILEGED_ROLES = {"admin", "manager", "hiring manager"}


def require_manager(user: dict | None) -> None:
    role = str((user or {}).get("role") or "").strip().lower()
    if role not in PRIVILEGED_ROLES:
        raise PermissionError("This action requires a manager or admin role.")


def readiness_payload() -> dict[str, Any]:
    jds = db.get_all_jds({"status": "Active"})
    vendors = db.get_all_vendors({"status": "Active", "sort": "company_name"})
    missing_counts = [row for row in jds if not row.get("required_candidate_count") or int(row.get("required_candidate_count") or 0) <= 0]
    category_review = [row for row in jds if not str(row.get("job_category") or "").strip() or str(row.get("job_category") or "").strip().lower() in {"others", "unknown"}]
    vendor_category_gaps = [row for row in vendors if not row.get("supported_categories")]
    categories = sorted({str(row.get("job_category") or "").strip() for row in jds if str(row.get("job_category") or "").strip()})
    return {
        "summary": {
            "active_jds": len(jds),
            "missing_required_counts": len(missing_counts),
            "category_review_required": len(category_review),
            "vendors_without_categories": len(vendor_category_gaps),
            "workflow_ready_jds": max(0, len(jds) - len(set(int(row["id"]) for row in [*missing_counts, *category_review]))),
        },
        "missing_counts": missing_counts,
        "category_review": category_review,
        "vendor_category_gaps": vendor_category_gaps,
        "categories": categories,
    }


def run_backfill(default_required_candidate_count: int | None = None) -> dict[str, int]:
    return db.backfill_workflow_defaults(default_required_candidate_count)


def update_jd_required_count(jd_id: int, required_count: int, user: dict | None = None) -> dict[str, Any]:
    require_manager(user)
    count = int(required_count or 0)
    if count <= 0:
        raise ValueError("required_candidate_count must be greater than zero")
    if not db.update_jd(jd_id, {"required_candidate_count": count}):
        raise ValueError("JD not found")
    db.log_audit("JD Required Count Updated", (user or {}).get("username") or "", f"Set JD id={jd_id} required count to {count}.", jd_id)
    return db.get_jd_by_id(jd_id, include_raw_text=False) or {}


def update_vendor_categories(vendor_id: int, categories: list[str], sub_tags: list[str] | None = None, user: dict | None = None) -> dict[str, Any]:
    require_manager(user)
    clean_categories = [str(item).strip() for item in categories if str(item).strip()]
    if not db.update_vendor(vendor_id, {"supported_categories": clean_categories, "supported_sub_tags": sub_tags or []}):
        raise ValueError("Vendor not found")
    db.log_audit("Vendor Categories Updated", (user or {}).get("username") or "", f"Updated automated categories for vendor id={vendor_id}.")
    return db.get_vendor_by_id(vendor_id) or {}


def override_bench_selection(jd_id: int, candidate_id: int, selection_status: str, user: dict | None = None) -> dict[str, Any]:
    require_manager(user)
    allowed = {"selected_bench", "waitlisted_bench", "rejected"}
    status = str(selection_status or "").strip()
    if status not in allowed:
        raise ValueError("selection_status must be selected_bench, waitlisted_bench, or rejected")
    qualification = "qualified" if status in {"selected_bench", "waitlisted_bench"} else "unqualified"
    if not db.update_comparison_metadata(
        jd_id,
        candidate_id,
        {"candidate_source": "bench", "selection_status": status, "qualification_status": qualification},
    ):
        raise ValueError("Comparison record not found")
    db.log_audit("Bench Selection Override", (user or {}).get("username") or "", f"Set candidate id={candidate_id} to {status} for JD id={jd_id}.", jd_id)
    return recalculate_fulfilment(jd_id)


def mark_bench_unavailable(jd_id: int, candidate_id: int, user: dict | None = None) -> dict[str, Any]:
    require_manager(user)
    if not db.update_candidate(candidate_id, {"availability_status": "Unavailable", "allocation_status": "Unavailable"}):
        raise ValueError("Candidate not found")
    db.update_comparison_metadata(
        jd_id,
        candidate_id,
        {"candidate_source": "bench", "selection_status": "rejected", "qualification_status": "unqualified"},
    )
    db.log_audit("Bench Candidate Unavailable", (user or {}).get("username") or "", f"Marked candidate id={candidate_id} unavailable for JD id={jd_id}.", jd_id)
    return recalculate_fulfilment(jd_id)

