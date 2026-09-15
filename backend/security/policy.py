from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DESTRUCTIVE_TOOLS = {"jd.delete", "candidate.delete"}
PRIVILEGED_ACTION_TOOLS = {
    "jd.delete",
    "candidate.delete",
    "jd.fulfilment.recalculate",
    "jd.workflow.retry",
    "vendor.assignment.retry",
    "vendor.email.retry",
    "bench.selection.override",
}
APPROVAL_REQUIRED_TOOLS = {
    "jd.delete",
    "candidate.delete",
    "candidate.repair",
    "interview.schedule",
    "email.send",
    "profile.update_password",
    "bulk.write",
    "jd.fulfilment.recalculate",
    "jd.workflow.retry",
    "vendor.assignment.retry",
    "vendor.email.retry",
    "bench.selection.override",
}
PRIVILEGED_ROLES = {"admin", "manager", "hiring manager"}


@dataclass(frozen=True)
class ToolRequest:
    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    user: dict[str, Any] = field(default_factory=dict)
    confirmed: bool = False
    run_id: str = ""


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    requires_approval: bool = False
    reason: str = ""


class PolicyEngine:
    def check(self, request: ToolRequest) -> PolicyDecision:
        user = request.user or {}
        if not user:
            return PolicyDecision(False, reason="Authenticated user is required.")

        role = str(user.get("role") or "").strip().lower()
        if request.tool in PRIVILEGED_ACTION_TOOLS and role not in PRIVILEGED_ROLES:
            return PolicyDecision(False, reason="This action requires a manager or admin role.")

        row_count = int(request.params.get("row_count") or 0)
        if row_count > 50 and not request.confirmed:
            return PolicyDecision(False, True, "Bulk writes over 50 rows require approval.")

        if request.tool == "profile.update" and any(request.params.get(key) for key in ("current_password", "new_password")):
            if not request.confirmed:
                return PolicyDecision(False, True, "Password changes require explicit approval.")

        if request.tool in APPROVAL_REQUIRED_TOOLS and not request.confirmed:
            return PolicyDecision(False, True, f"{request.tool} requires explicit approval.")

        return PolicyDecision(True)
