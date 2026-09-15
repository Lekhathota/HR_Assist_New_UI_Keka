from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


KNOWN_TASKS = {
    "screening",
    "agentic_screening",
    "chat",
    "chat_action",
    "message",
    "msg",
    "recruiter_chat",
    "jd_list",
    "jd_details",
    "jd_create",
    "jd_delete",
    "candidate_list",
    "candidate_profile",
    "candidate_delete",
    "candidate_repair",
    "client_list",
    "client_details",
    "profile_get",
    "profile_update",
    "interview_defaults",
    "interview_blocked_slots",
    "interview_generate_email",
    "interview_schedule",
    "dashboard",
    "dashboard_team",
    "jd_performance",
    "reports",
}


class RecruiterActionParams(BaseModel):
    model_config = ConfigDict(extra="allow")

    jd_id: int | None = Field(default=None, ge=1)
    candidate_id: int | None = Field(default=None, ge=1)
    client_id: int | None = Field(default=None, ge=1)
    interview_date: str = ""
    interview_time: str = ""
    subject: str = ""
    body: str = ""


class AgenticPayload(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    task_type: str = ""
    type: str = ""
    message: str = ""
    msg: str = ""
    action: str = ""
    jd_id: int | None = Field(default=None, ge=1)
    candidate_id: int | None = Field(default=None, ge=1)
    candidate_ids: list[str] = Field(default_factory=list)
    resume_items: list[dict[str, str]] = Field(default_factory=list)
    skipped_files: int = Field(default=0, ge=0)
    file: Any = None
    upload_folder: str = ""
    required_candidate_count: int | None = Field(default=None, ge=1)
    data: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False

    APP_TASKS_REQUIRING_IDS: ClassVar[dict[str, str]] = {
        "jd_details": "jd_id",
        "jd_delete": "jd_id",
        "candidate_profile": "candidate_id",
        "candidate_delete": "candidate_id",
        "client_details": "client_id",
    }

    @field_validator("task_type", "type", mode="before")
    @classmethod
    def _clean_task(cls, value: Any) -> str:
        return str(value or "").strip().lower()

    @field_validator("message", "msg", "action", "upload_folder", mode="before")
    @classmethod
    def _clean_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("candidate_ids", mode="before")
    @classmethod
    def _candidate_ids(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        values = value if isinstance(value, list) else [value]
        out = []
        for item in values:
            raw = str(item).strip()
            if raw:
                int(raw)
                out.append(raw)
        return out

    @field_validator("data", "params", mode="before")
    @classmethod
    def _dict_or_empty(cls, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @field_validator("confirmed", mode="before")
    @classmethod
    def _bool_value(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @model_validator(mode="after")
    def _validate_task(self) -> "AgenticPayload":
        task = self.task_type or self.type
        if not task and (self.message or self.msg):
            self.task_type = "chat"
            task = "chat"
        if not task and self.jd_id:
            self.task_type = "screening"
            task = "screening"
        if not task:
            raise ValueError("task_type is required unless message or jd_id is provided.")
        if task not in KNOWN_TASKS:
            raise ValueError(f"Unsupported task_type: {task}")
        if task in {"screening", "agentic_screening"} and not self.jd_id:
            raise ValueError("jd_id is required for screening.")
        if task == "chat_action" and not self.action:
            raise ValueError("action is required for chat_action.")
        if task == "jd_create" and self.file is None:
            raise ValueError("file is required for jd_create.")
        required_id = self.APP_TASKS_REQUIRING_IDS.get(task)
        if required_id == "jd_id" and not self.jd_id:
            raise ValueError("jd_id is required.")
        if required_id == "candidate_id" and not self.candidate_id:
            raise ValueError("candidate_id is required.")
        if required_id == "client_id" and not self.client_id:
            raise ValueError("client_id is required.")
        return self


def validate_agentic_payload(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        model = AgenticPayload.model_validate(payload or {})
    except ValidationError as exc:
        messages = [err.get("msg", "Invalid request") for err in exc.errors()]
        raise ValueError("; ".join(messages)) from exc
    data = model.model_dump()
    for key, value in payload.items():
        if key.startswith("_") or key not in data:
            data[key] = value
    data["task_type"] = data.get("task_type") or data.get("type") or ""
    return data
