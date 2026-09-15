# Backend file purpose: Service-layer business logic for report features.
from __future__ import annotations

import database as db
from services.jd_service import jd_summary_list_payload


# Purpose: Implements the metrics with normalized candidates backend behavior.
def _metrics_with_normalized_candidates(base: dict, candidates: list[dict]) -> dict:
    selected = int(base.get("selected_candidates") or 0)
    rejected = int(base.get("rejected_candidates") or 0)
    applications = len(candidates)
    decision_total = selected + rejected
    avg_match = int(sum(int(row.get("match_score") or 0) for row in candidates) / applications) if applications else 0
    return {
        **base,
        "total_candidates": applications,
        "screened_candidates": decision_total,
        "selected_candidates": selected,
        "rejected_candidates": rejected,
        "pending_candidates": max(0, applications - selected - rejected),
        "avg_match_score": avg_match,
        "selection_rate": int((selected / decision_total) * 100) if decision_total else 0,
        "rejection_rate": int((rejected / decision_total) * 100) if decision_total else 0,
    }


# Purpose: Implements the dashboard payload backend behavior.
def dashboard_payload() -> dict:
    metrics = db.get_dashboard_metrics()
    activity = db.recent_activity(5)
    candidates = db.get_all_candidates()
    jd_summaries = {int(row["id"]): row for row in jd_summary_list_payload()}
    recent_jds = []
    for jd in activity["recent_jds"]:
        row = {k: v for k, v in jd.items() if k != "raw_text"}
        if row.get("id") is not None and int(row["id"]) in jd_summaries:
            row.update(
                {
                    "selected_count": jd_summaries[int(row["id"])].get("selected_count", 0),
                    "rejected_count": jd_summaries[int(row["id"])].get("rejected_count", 0),
                    "total_resumes": jd_summaries[int(row["id"])].get("total_resumes", 0),
                }
            )
        recent_jds.append(row)
    return {
        "metrics": _metrics_with_normalized_candidates(metrics, candidates),
        "recent_jds": recent_jds,
        "recent_candidates": candidates[:5],
        "recent_comparisons": activity["recent_comparisons"],
        "candidates": candidates,
    }


# Purpose: Implements the reports payload backend behavior.
def reports_payload() -> dict:
    return db.get_reports_data()


# Purpose: Implements the jd performance payload backend behavior.
def jd_performance_payload() -> list[dict]:
    return db.get_jd_performance()
