from __future__ import annotations

from pathlib import Path


PAGE_W = 842
PAGE_H = 595
MARGIN = 44


def esc(text: object) -> str:
    value = str(text)
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class PdfPage:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def text(self, x: float, y: float, value: str, size: int = 10, font: str = "F1") -> None:
        self.ops.append(f"BT /{font} {size} Tf {x:.1f} {y:.1f} Td ({esc(value)}) Tj ET")

    def wrapped_text(self, x: float, y: float, value: str, width_chars: int = 100, size: int = 9, leading: int = 13) -> float:
        words = value.split()
        line = ""
        for word in words:
            maybe = f"{line} {word}".strip()
            if len(maybe) > width_chars and line:
                self.text(x, y, line, size)
                y -= leading
                line = word
            else:
                line = maybe
        if line:
            self.text(x, y, line, size)
            y -= leading
        return y

    def line(self, x1: float, y1: float, x2: float, y2: float, width: float = 1.0) -> None:
        self.ops.append(f"q {width:.1f} w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S Q")

    def rect(self, x: float, y: float, w: float, h: float, fill: str = "0.96 0.98 1.00") -> None:
        self.ops.append(f"q {fill} rg 0.18 0.24 0.32 RG 1.0 w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re B Q")

    def box(self, x: float, y: float, w: float, h: float, title: str, lines: list[str] | None = None, fill: str = "0.96 0.98 1.00") -> None:
        self.rect(x, y, w, h, fill)
        self.text(x + 9, y + h - 17, title, 10, "F2")
        cursor = y + h - 31
        for line in lines or []:
            self.text(x + 9, cursor, line, 7)
            cursor -= 10

    def title(self, value: str, subtitle: str | None = None) -> None:
        self.text(MARGIN, PAGE_H - 44, value, 18, "F2")
        if subtitle:
            self.text(MARGIN, PAGE_H - 64, subtitle, 9)
        self.line(MARGIN, PAGE_H - 78, PAGE_W - MARGIN, PAGE_H - 78, 0.8)

    def footer(self, page_no: int) -> None:
        self.line(MARGIN, 34, PAGE_W - MARGIN, 34, 0.7)
        self.text(MARGIN, 19, "RecruitmentAssist - Backend Folder Explanation", 7)
        self.text(PAGE_W - MARGIN - 42, 19, f"Page {page_no}", 7)

    def stream(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1")


FOLDERS = [
    (
        "agents",
        "AI role modules",
        "Contains specialized agent logic: router, JD, resume, matching, ranking, summary, interview, and recruiter chat agents. These modules decide or generate intelligent responses, but still rely on tools/services for data and side effects.",
        "router_agent.py, recruiter_agent.py, resume_agent.py, matching_agent.py",
    ),
    (
        "app",
        "Core extraction and matching helpers",
        "Older/core application utilities used by services: LLM extraction, regex fallback extraction, text parsing, screening summaries, matching logic, and cleaning helpers.",
        "llm_extraction.py, regex_extractor.py, text_extractor.py, matcher.py",
    ),
    (
        "database",
        "Database setup and migration scripts",
        "Operational scripts and SQL files for schema setup, migration, Mongo import, upload import, seed data, and admin password fixes. Runtime database helpers live in backend/database.py.",
        "schema.sql, migrate_json_to_db.py, seed_mongo_data.py",
    ),
    (
        "orchestration",
        "Agent routing and graph coordination",
        "Coordinates agentic requests. The main orchestrator tracks runs, hr_graph routes tasks through a graph of nodes, and tracing records readable execution events.",
        "main_orchestrator.py, hr_graph.py, tracing.py",
    ),
    (
        "routes",
        "Flask API endpoints",
        "HTTP boundary for the backend. Routes receive frontend requests, validate/authenticate them, call services or workflows, and return JSON responses.",
        "candidate_routes.py, jd_routes.py, interview_routes.py, agentic_routes.py",
    ),
    (
        "schemas",
        "Request validation models",
        "Structured request validation for agentic payloads. It keeps chatbot/orchestrator inputs predictable before they reach agents and tools.",
        "agentic.py",
    ),
    (
        "security",
        "Agent and tool safety controls",
        "Safety rules for context size, prompt-injection detection, and tool policy. This folder helps prevent unsafe assistant behavior and unconfirmed side effects.",
        "context_safety.py, policy.py",
    ),
    (
        "services",
        "Business logic layer",
        "Feature logic used by routes: authentication, candidates, JDs, matching, interviews, and reports. Services transform data and enforce app-level behavior.",
        "candidate_service.py, interview_service.py, matching_service.py",
    ),
    (
        "static",
        "Served static files and uploads",
        "Stores static assets served by Flask, such as the ShimentoX logo and uploaded resume files. Upload files are data artifacts, not application logic.",
        "ShimentoX logo, uploads/",
    ),
    (
        "templates",
        "Flask template placeholder",
        "Reserved for server-rendered templates. In this project the React frontend is primary, so this folder mostly exists for Flask compatibility.",
        ".gitkeep",
    ),
    (
        "tests",
        "Automated backend checks",
        "Backend tests for safety and important behavior. These provide regression checks for security hardening and can be expanded as the backend grows.",
        "test_security_hardening.py",
    ),
    (
        "tools",
        "Safe helper capabilities for agents",
        "Small focused helpers that agents can call for app data or approved actions. The gateway centralizes confirmation/policy checks for side-effecting tools.",
        "recruiter_tools.py, matching_tools.py, tool_gateway.py",
    ),
    (
        "workflows",
        "Multi-step application flows",
        "Orchestrates larger processes like screening and recruiter chat by calling agents, tools, and services in the right order.",
        "app_workflow.py, screening_workflow.py, recruiter_chat_workflow.py",
    ),
]


ROOT_FILES = [
    ("app.py", "Flask application entry point. Registers blueprints, static frontend serving, CORS/session behavior, and API startup wiring."),
    ("database.py", "Runtime database access layer. Centralizes Mongo/database CRUD helpers used by routes, services, tools, and agents."),
    ("requirements.txt", "Python dependencies for running the backend."),
    ("spa_urls.py", "Frontend route allow-list/helper for serving the React single-page application."),
    (".env / .env.example", "Local configuration and example environment variables for database, SMTP, OpenAI, and app secrets."),
]


def overview_page() -> PdfPage:
    p = PdfPage()
    p.title("Backend Folder Explanation", "RecruitmentAssist backend structure and responsibilities")
    y = 500
    p.text(MARGIN, y, "Backend architecture in one sentence", 13, "F2")
    y -= 22
    y = p.wrapped_text(
        MARGIN,
        y,
        "The backend is a Flask application split into routes, services, database helpers, agentic workflows, tools, and safety layers so normal HR features and AI assistant features can share the same data safely.",
        118,
        10,
        14,
    )
    y -= 8
    p.text(MARGIN, y, "How the main layers connect", 13, "F2")
    y -= 24
    p.box(64, y - 46, 120, 48, "routes", ["HTTP API", "auth + JSON"])
    p.box(226, y - 46, 120, 48, "services", ["business logic", "feature rules"])
    p.box(388, y - 46, 120, 48, "database.py", ["runtime CRUD", "Mongo helpers"])
    p.box(550, y - 46, 120, 48, "agents", ["AI reasoning", "drafts + answers"])
    p.box(690, y - 46, 100, 48, "tools", ["safe data", "actions"])
    p.line(184, y - 22, 226, y - 22)
    p.line(346, y - 22, 388, y - 22)
    p.line(508, y - 22, 550, y - 22)
    p.line(670, y - 22, 690, y - 22)
    y -= 90
    bullets = [
        "Routes are the API boundary.",
        "Services hold normal product behavior.",
        "Agents, workflows, tools, schemas, and security support the recruiter assistant and agentic screening flow.",
        "Root files like app.py and database.py wire the application together.",
    ]
    for item in bullets:
        y = p.wrapped_text(MARGIN + 12, y, f"- {item}", 116, 9, 13)
    p.footer(1)
    return p


def folder_page(page_no: int, title: str, folders: list[tuple[str, str, str, str]]) -> PdfPage:
    p = PdfPage()
    p.title(title, "Each folder's purpose and common files")
    y = 500
    for folder, role, desc, examples in folders:
        p.text(MARGIN, y, folder, 11, "F2")
        p.text(MARGIN + 120, y, role, 10, "F2")
        y -= 17
        y = p.wrapped_text(MARGIN + 120, y, desc, 90, 9, 12)
        y = p.wrapped_text(MARGIN + 120, y, f"Key files: {examples}", 90, 8, 11)
        y -= 10
    p.footer(page_no)
    return p


def root_files_page() -> PdfPage:
    p = PdfPage()
    p.title("Backend Root Files", "Important files directly inside backend/")
    y = 500
    for name, desc in ROOT_FILES:
        p.text(MARGIN, y, name, 10, "F2")
        y = p.wrapped_text(MARGIN + 145, y, desc, 88, 9, 13)
        y -= 12
    y -= 4
    p.text(MARGIN, y, "Folders usually ignored while explaining code", 13, "F2")
    y -= 22
    p.wrapped_text(
        MARGIN,
        y,
        "__pycache__ is Python bytecode cache generated automatically. static/uploads can contain user-uploaded resumes and should be treated as runtime data rather than source code.",
        116,
        9,
        13,
    )
    p.footer(5)
    return p


def write_pdf(path: Path, pages: list[PdfPage]) -> None:
    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    font1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    content_refs: list[int] = []
    page_refs: list[int] = []
    for page in pages:
        stream = page.stream()
        content_refs.append(add(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"))
        page_refs.append(0)
    pages_ref = len(objects) + len(pages) + 1
    for idx, content_ref in enumerate(content_refs):
        page_obj = (
            f"<< /Type /Page /Parent {pages_ref} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /Font << /F1 {font1} 0 R /F2 {font2} 0 R >> >> "
            f"/Contents {content_ref} 0 R >>"
        ).encode("ascii")
        page_refs[idx] = add(page_obj)
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
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_ref} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(output)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "docs" / "backend_folder_explanation.pdf"
    pages = [
        overview_page(),
        folder_page(2, "Backend Folders - Part 1", FOLDERS[:4]),
        folder_page(3, "Backend Folders - Part 2", FOLDERS[4:9]),
        folder_page(4, "Backend Folders - Part 3", FOLDERS[9:]),
        root_files_page(),
    ]
    write_pdf(output, pages)
    print(output)


if __name__ == "__main__":
    main()
