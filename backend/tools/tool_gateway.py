from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

import database as db
from security.policy import PolicyEngine, ToolRequest


@dataclass(frozen=True)
class ToolResult:
    success: bool
    tool: str
    requires_approval: bool = False
    approval_reason: str = ""
    data: dict[str, Any] | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["data"] = self.data or {}
        return payload


def _audit(request: ToolRequest, outcome: str, details: str, params: dict[str, Any]) -> None:
    user = request.user or {}
    db.log_audit(
        f"Tool {outcome}",
        user.get("username") or "",
        details,
        params.get("jd_id"),
        run_id=request.run_id,
        tool=request.tool,
        outcome=outcome,
        params=params,
    )


class ToolGateway:
    def __init__(self, policy: PolicyEngine | None = None):
        self.policy = policy or PolicyEngine()
        self._tools: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
            "jd.create": self._jd_create,
            "jd.delete": self._jd_delete,
            "candidate.delete": self._candidate_delete,
            "candidate.repair": self._candidate_repair,
            "interview.schedule": self._interview_schedule,
            "profile.update": self._profile_update,
        }

    def execute(self, request: ToolRequest) -> ToolResult:
        if request.tool not in self._tools:
            return ToolResult(False, request.tool, error=f"Unsupported tool: {request.tool}")

        decision = self.policy.check(request)
        if decision.requires_approval:
            _audit(request, "approval_required", decision.reason, request.params)
            return ToolResult(False, request.tool, True, decision.reason)
        if not decision.allowed:
            _audit(request, "denied", decision.reason, request.params)
            return ToolResult(False, request.tool, error=decision.reason)

        try:
            data = self._tools[request.tool](request.params, request.user)
            _audit(request, "allowed", "Tool executed successfully.", request.params)
            return ToolResult(True, request.tool, data=data)
        except Exception as exc:
            _audit(request, "failed", str(exc), request.params)
            return ToolResult(False, request.tool, error=str(exc))

    def _jd_create(self, params: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        from services.jd_service import create_jd_from_upload

        upload = params.get("file")
        if not upload:
            raise ValueError("No file uploaded")
        return {
            "jd": create_jd_from_upload(
                upload,
                str(params.get("upload_folder") or ""),
                int(params.get("client_id") or 0) or None,
                int(params.get("required_candidate_count") or 0) or None,
            ).get("jd")
        }

    def _jd_delete(self, params: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        jd_id = int(params.get("jd_id") or 0)
        return {"success": bool(db.delete_jd(jd_id))}

    def _candidate_delete(self, params: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        candidate_id = int(params.get("candidate_id") or 0)
        success = bool(db.delete_candidate(candidate_id))
        if not success:
            raise ValueError("Candidate not found")
        return {"success": True}

    def _candidate_repair(self, params: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        from services.candidate_service import normalize_candidate_record, repair_all_candidates

        candidate_id = int(params.get("candidate_id") or 0)
        if not candidate_id:
            return {"success": True, **repair_all_candidates(force_reextract=True)}
        candidate = db.get_candidate_by_id(candidate_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        normalized = normalize_candidate_record(candidate, repair=True, force_reextract=True)
        return {"success": True, "candidate": normalized}

    def _interview_schedule(self, params: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        from services.interview_service import (
            assert_slot_available,
            default_from_email,
            interview_window,
            schedule_context,
            send_email,
        )

        candidate_id = int(params.get("candidate_id") or 0)
        jd_id = int(params.get("jd_id") or 0)
        interview_date = str(params.get("interview_date") or "").strip()
        interview_time = str(params.get("interview_time") or "").strip()
        subject = str(params.get("subject") or "").strip()
        body = str(params.get("body") or "").strip()
        if not all([candidate_id, jd_id, interview_date, interview_time, subject, body]):
            raise ValueError("candidate_id, jd_id, interview date/time, subject, and body are required.")
        interview_start, interview_end = interview_window(interview_date, interview_time)
        assert_slot_available(int(user["id"]), interview_start, interview_end)
        ctx = schedule_context(candidate_id, jd_id)
        from_email = default_from_email(user)
        to_email = ctx["candidate"].get("email") or ""
        send_email(to_email, subject, body, from_email)
        interview_id = db.create_interview(
            {
                "candidate_id": candidate_id,
                "candidate_email": to_email,
                "candidate_name": ctx["candidate"].get("name") or "",
                "jd_id": jd_id,
                "job_role": ctx["jd"].get("title") or "",
                "recruiter_id": int(user["id"]),
                "recruiter_email": user.get("email") or "",
                "interview_start": interview_start,
                "interview_end": interview_end,
                "from_email": from_email,
                "to_email": to_email,
                "email_subject": subject,
                "email_body": body,
                "status": "Scheduled",
            }
        )
        db.update_candidate(candidate_id, {"hiring_stage": "Interview Scheduled"})
        return {"success": True, "interview_id": interview_id}

    def _profile_update(self, params: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        email = str(params.get("email") or "").strip()
        current_password = str(params.get("current_password") or "")
        new_password = str(params.get("new_password") or "")
        confirm_password = str(params.get("confirm_password") or "")
        if new_password or current_password or confirm_password:
            if not current_password or not new_password:
                raise ValueError("Current password and new password are required.")
            if new_password != confirm_password:
                raise ValueError("New passwords do not match.")
            if not db.update_user_password(int(user["id"]), current_password, new_password):
                raise ValueError("Current password is incorrect.")
        db.update_user_profile(int(user["id"]), email)
        return {"success": True, "message": "Profile updated successfully", "user": db.get_user_by_id(int(user["id"]))}


gateway = ToolGateway()
