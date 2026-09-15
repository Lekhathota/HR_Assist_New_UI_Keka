from __future__ import annotations

from datetime import datetime
from pathlib import Path


PAGE_W = 842
PAGE_H = 595
MARGIN = 44


def esc(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class Page:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def text(self, x: float, y: float, value: str, size: int = 10, font: str = "F1") -> None:
        self.ops.append(f"BT /{font} {size} Tf {x:.1f} {y:.1f} Td ({esc(value)}) Tj ET")

    def line(self, x1: float, y1: float, x2: float, y2: float, width: float = 0.8) -> None:
        self.ops.append(f"q {width:.1f} w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S Q")

    def rect(self, x: float, y: float, w: float, h: float, fill: str = "0.96 0.98 1.00") -> None:
        self.ops.append(f"q {fill} rg 0.18 0.24 0.32 RG 0.9 w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re B Q")

    def arrow(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.line(x1, y1, x2, y2)
        if abs(x2 - x1) >= abs(y2 - y1):
            direction = 1 if x2 >= x1 else -1
            self.line(x2, y2, x2 - 7 * direction, y2 + 4, 0.7)
            self.line(x2, y2, x2 - 7 * direction, y2 - 4, 0.7)
        else:
            direction = 1 if y2 >= y1 else -1
            self.line(x2, y2, x2 - 4, y2 - 7 * direction, 0.7)
            self.line(x2, y2, x2 + 4, y2 - 7 * direction, 0.7)

    def wrap(self, x: float, y: float, value: str, width: int = 112, size: int = 9, leading: int = 13) -> float:
        words = str(value).split()
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if len(candidate) > width and line:
                self.text(x, y, line, size)
                y -= leading
                line = word
            else:
                line = candidate
        if line:
            self.text(x, y, line, size)
            y -= leading
        return y

    def bullet(self, y: float, value: str, width: int = 112) -> float:
        return self.wrap(MARGIN + 12, y, f"- {value}", width, 9, 13) - 2

    def title(self, title: str, subtitle: str) -> float:
        self.text(MARGIN, PAGE_H - 45, title, 18, "F2")
        self.text(MARGIN, PAGE_H - 64, subtitle, 9)
        self.line(MARGIN, PAGE_H - 78, PAGE_W - MARGIN, PAGE_H - 78)
        return PAGE_H - 108

    def section(self, y: float, title: str) -> float:
        self.text(MARGIN, y, title, 13, "F2")
        return y - 20

    def box(self, x: float, y: float, w: float, h: float, title: str, lines: list[str] | None = None, fill: str = "0.96 0.98 1.00") -> None:
        self.rect(x, y, w, h, fill)
        self.text(x + 8, y + h - 16, title, 9, "F2")
        cursor = y + h - 30
        for line in lines or []:
            self.text(x + 8, cursor, line, 7)
            cursor -= 10

    def footer(self, page_no: int) -> None:
        self.line(MARGIN, 34, PAGE_W - MARGIN, 34, 0.7)
        self.text(MARGIN, 19, "RecruitmentAssist - Production Hardening Report", 7)
        self.text(PAGE_W - MARGIN - 42, 19, f"Page {page_no}", 7)

    def stream(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1")


def page_summary() -> Page:
    page = Page()
    y = page.title("Production Hardening Report", f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    y = page.section(y, "Executive Summary")
    for item in [
        "The existing Flask, LangGraph, and MongoDB HR agent system was hardened without replacing the product workflow.",
        "The implementation adds typed validation, a policy-enforced tool gateway, tamper-evident audit logging, and prompt/context safety checks.",
        "The core recruitment graph remains intact: router, screening path, recruiter chat path, and app workflow path still use the same API surface.",
        "Controlled mutations now have a security boundary instead of being called directly from agents or workflows.",
    ]:
        y = page.bullet(y, item)

    y -= 8
    y = page.section(y, "Design Intent")
    for item in [
        "Preserve working HR behavior while adding production safeguards around the riskiest operations.",
        "Prefer incremental hardening over a disruptive migration to FastAPI, MCP servers, or a new database stack.",
        "Make unsafe or ambiguous actions fail closed with clear approval-required or authorization-denied responses.",
    ]:
        y = page.bullet(y, item)
    page.footer(1)
    return page


def page_architecture() -> Page:
    page = Page()
    page.title("Updated Architecture", "How the new controls fit around the existing LangGraph system")
    page.box(45, 455, 128, 54, "Client / Frontend", ["Sends agentic task", "JSON or multipart"])
    page.box(215, 455, 128, 54, "Flask Route", ["Validates payload", "Pydantic schemas"])
    page.box(385, 455, 128, 54, "Main Orchestrator", ["Creates run_id", "Invokes graph"])
    page.box(555, 455, 170, 54, "LangGraph", ["Router", "Screening/chat/app paths"])
    page.arrow(173, 482, 215, 482)
    page.arrow(343, 482, 385, 482)
    page.arrow(513, 482, 555, 482)

    page.box(115, 330, 145, 60, "Read-Only Services", ["Dashboard", "JD/candidate lists", "Reports"], "0.96 0.99 0.96")
    page.box(348, 330, 145, 60, "Tool Gateway", ["Validate params", "Policy check", "Audit attempt"], "0.98 0.98 0.92")
    page.box(585, 330, 145, 60, "Controlled Tools", ["Deletes", "Repair", "Schedule/send"], "0.99 0.96 0.96")
    page.arrow(640, 455, 420, 390)
    page.arrow(260, 360, 348, 360)
    page.arrow(493, 360, 585, 360)

    page.box(155, 195, 150, 60, "Policy Engine", ["Auth required", "Role checks", "Approval gates"], "0.95 0.98 1.00")
    page.box(345, 195, 150, 60, "Audit Chain", ["previous_hash", "current_hash", "sanitized params"], "0.95 0.98 1.00")
    page.box(535, 195, 150, 60, "Prompt Safety", ["Injection markers", "Context budget", "Blocked logs"], "0.95 0.98 1.00")
    page.arrow(420, 330, 230, 255)
    page.arrow(420, 330, 420, 255)
    page.arrow(640, 455, 610, 255)

    page.text(80, 120, "Key boundary: role agents can still decide what to do, but controlled side effects are executed only by the gateway.", 10, "F2")
    page.footer(2)
    return page


def page_changes() -> Page:
    page = Page()
    y = page.title("Implementation Changes", "Files and behavior added by the hardening pass")
    sections = [
        (
            "Validation Layer",
            [
                "Added schemas/agentic.py with Pydantic v2 models for agentic payloads and recruiter action params.",
                "Routes now validate /api/agentic/run and /api/agentic/screening before graph invocation.",
                "Invalid task types, missing IDs, malformed params, and missing files now return request validation errors earlier.",
            ],
        ),
        (
            "Gateway and Policy",
            [
                "Added tools/tool_gateway.py with ToolRequest, ToolResult, and registered controlled tool handlers.",
                "Added security/policy.py with role checks, approval gates, auth requirements, and bulk-write protection.",
                "App workflow now routes JD create/delete, candidate delete/repair, interview schedule, and profile update through the gateway.",
            ],
        ),
        (
            "Audit and Prompt Safety",
            [
                "database.log_audit now supports run_id, tool, outcome, sanitized params, previous_hash, and current_hash.",
                "Added verify_audit_chain() for tamper-evident audit validation.",
                "Router and recruiter chat now run lightweight prompt-injection checks before LLM calls.",
            ],
        ),
    ]
    for title, bullets in sections:
        y = page.section(y, title)
        for item in bullets:
            y = page.bullet(y, item)
        y -= 6
    page.footer(3)
    return page


def page_behavior() -> Page:
    page = Page()
    y = page.title("Behavioral Understanding", "What changed at runtime")
    y = page.section(y, "Controlled Action Rules")
    for item in [
        "Deletes require a manager/admin-style role and explicit confirmation.",
        "Candidate repair, interview scheduling, email sending, password changes, and bulk writes over 50 rows require explicit confirmation.",
        "If approval is missing, the tool is not executed and the response says approval is required.",
        "If authorization fails, the tool is not executed and the response says the action is not allowed.",
        "Every gateway attempt is audited as allowed, denied, approval_required, or failed.",
    ]:
        y = page.bullet(y, item)

    y -= 8
    y = page.section(y, "Prompt and Context Safety")
    for item in [
        "Recruiter chat still uses compact grounded context, but the context is now trimmed before it enters the prompt.",
        "Messages that try to ignore system instructions, reveal secrets, or bypass approvals are blocked before LLM execution.",
        "Blocked prompt attempts are written to the audit log with sanitized metadata.",
        "Semantic vector memory was intentionally deferred; the immediate priority was safety around tool execution.",
    ]:
        y = page.bullet(y, item)
    page.footer(4)
    return page


def page_sequence() -> Page:
    page = Page()
    page.title("Security Sequence", "Lifecycle of a controlled agent action")
    lanes = [
        (52, "Frontend"),
        (178, "Route"),
        (304, "Graph"),
        (430, "Workflow/Agent"),
        (556, "Gateway"),
        (682, "DB/Service"),
    ]
    for x, title in lanes:
        page.box(x, 500, 96, 30, title)
        page.line(x + 48, 500, x + 48, 95, 0.5)

    messages = [
        (465, 52, 178, "POST task payload"),
        (425, 178, 178, "Pydantic validate"),
        (385, 178, 304, "run graph"),
        (345, 304, 430, "selected path"),
        (305, 430, 556, "ToolRequest"),
        (265, 556, 556, "policy check"),
        (225, 556, 682, "execute if allowed"),
        (185, 556, 682, "write audit hash"),
        (145, 556, 430, "ToolResult"),
        (110, 430, 52, "response"),
    ]
    for y, x1, x2, label in messages:
        if x1 == x2:
            page.box(x1 + 8, y - 9, 82, 18, label, [], "0.98 0.98 0.92")
        else:
            page.arrow(x1 + 48, y, x2 + 48, y)
            page.text(min(x1, x2) + 54, y + 7, label, 7)
    page.footer(5)
    return page


def page_testing() -> Page:
    page = Page()
    y = page.title("Verification and Test Report", "Checks completed after implementation")
    y = page.section(y, "Automated Verification")
    for item in [
        "Focused test file added: backend/tests/test_security_hardening.py.",
        "Tests cover payload validation, policy approval rules, destructive action role denial, prompt-injection detection, and audit hash tamper detection.",
        "Command passed: .venv/Scripts/python.exe -m pytest RecruitmentAssist/backend/tests/test_security_hardening.py.",
        "Result: 8 tests passed.",
        "Compile check passed for all touched backend modules and the new test file.",
    ]:
        y = page.bullet(y, item)

    y -= 8
    y = page.section(y, "Manual Checks Recommended")
    for item in [
        "Try candidate_delete as a recruiter and confirm it is denied.",
        "Try candidate_delete as manager/admin without confirmed=True and confirm approval is required.",
        "Try interview_schedule without confirmed=True and confirm no email is sent.",
        "Ask recruiter chat to ignore previous instructions and confirm the message is blocked and audited.",
        "Run verify_audit_chain() after several controlled actions and confirm the chain is valid.",
    ]:
        y = page.bullet(y, item)
    page.footer(6)
    return page


def write_pdf(path: Path, pages: list[Page]) -> None:
    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    font_regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    content_refs = []
    page_refs = []
    for page in pages:
        stream = page.stream()
        content_refs.append(add(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"))

    pages_ref = len(objects) + len(pages) + 1
    for content_ref in content_refs:
        page_refs.append(
            add(
                (
                    f"<< /Type /Page /Parent {pages_ref} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                    f"/Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >> >> "
                    f"/Contents {content_ref} 0 R >>"
                ).encode("ascii")
            )
        )
    kids = " ".join(f"{ref} 0 R" for ref in page_refs)
    add(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_refs)} >>".encode("ascii"))
    catalog_ref = add(f"<< /Type /Catalog /Pages {pages_ref} 0 R >>".encode("ascii"))

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{idx} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_ref} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(output)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "docs" / "production_hardening_report.pdf"
    pages = [
        page_summary(),
        page_architecture(),
        page_changes(),
        page_behavior(),
        page_sequence(),
        page_testing(),
    ]
    write_pdf(output, pages)
    print(output)


if __name__ == "__main__":
    main()
