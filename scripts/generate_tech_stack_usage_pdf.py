from __future__ import annotations

from pathlib import Path
import textwrap


PAGE_W = 842
PAGE_H = 595
MARGIN = 44
CONTENT_W = PAGE_W - (MARGIN * 2)


def esc(text: object) -> str:
    value = str(text)
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class PdfPage:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def text(self, x: float, y: float, value: str, size: int = 9, font: str = "F1") -> None:
        self.ops.append(f"BT /{font} {size} Tf {x:.1f} {y:.1f} Td ({esc(value)}) Tj ET")

    def line(self, x1: float, y1: float, x2: float, y2: float, width: float = 0.7) -> None:
        self.ops.append(f"q {width:.1f} w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S Q")

    def rect(self, x: float, y: float, w: float, h: float, fill: str = "0.95 0.97 1.00") -> None:
        self.ops.append(f"q {fill} rg 0.20 0.24 0.32 RG 0.8 w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re B Q")

    def title(self, value: str, subtitle: str | None = None) -> None:
        self.text(MARGIN, PAGE_H - 42, value, 18, "F2")
        if subtitle:
            self.text(MARGIN, PAGE_H - 62, subtitle, 9)
        self.line(MARGIN, PAGE_H - 76, PAGE_W - MARGIN, PAGE_H - 76)

    def footer(self, page_no: int) -> None:
        self.line(MARGIN, 34, PAGE_W - MARGIN, 34)
        self.text(MARGIN, 19, "Recruitment Assist - Tech Stack Usage Document", 7)
        self.text(PAGE_W - MARGIN - 42, 19, f"Page {page_no}", 7)

    def wrapped_text(
        self,
        x: float,
        y: float,
        value: str,
        width_chars: int = 110,
        size: int = 9,
        leading: int = 12,
        font: str = "F1",
    ) -> float:
        for paragraph in str(value).split("\n"):
            if not paragraph.strip():
                y -= leading
                continue
            for line in textwrap.wrap(paragraph, width=width_chars, break_long_words=False):
                self.text(x, y, line, size, font)
                y -= leading
        return y

    def stream(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1")


SECTIONS = [
    (
        "Frontend Technologies",
        [
            ("React 18", "frontend/src/App.jsx, frontend/src/pages/*, frontend/src/components/*", "Builds the single-page application UI with reusable components."),
            ("React DOM", "frontend/src/index.js", "Mounts the React app into the browser DOM."),
            ("React Router DOM", "frontend/src/App.jsx and files using Link/useNavigate/useParams", "Handles routes like /dashboard, /jobs, /analyze, /talent, /interviews, and /profile."),
            ("Create React App / react-scripts", "frontend/package.json", "Provides the dev server, build command, test runner, and standard React tooling."),
            ("CSS", "frontend/src/styles/*.css and frontend/src/index.css", "Controls layout, branding, dashboard styling, forms, reports, and responsive UI."),
            ("Flatpickr", "frontend/src/pages/Dashboard.jsx and frontend/src/styles/dashboard.css", "Provides dashboard date picker controls."),
            ("Fetch API", "frontend/src/api.js", "Sends HTTP requests from React to Flask APIs."),
            ("localStorage / sessionStorage", "frontend/src/api.js", "Stores session tokens and small frontend caches."),
            ("Tailwind config", "frontend/tailwind.config.js", "Defines design tokens; the current UI mainly uses custom CSS files."),
        ],
    ),
    (
        "Backend Technologies",
        [
            ("Python", "backend/**/*.py", "Main backend programming language."),
            ("Flask", "backend/app.py and backend/routes/*.py", "Provides API routing, request handling, sessions, redirects, and JSON responses."),
            ("Flask Blueprints", "backend/app.py and backend/routes/*.py", "Organizes APIs by feature: auth, dashboard, jobs, candidates, matching, interviews, reports, audit, and agentic routes."),
            ("Flask-CORS", "backend/app.py", "Allows React localhost frontend requests to Flask /api/* endpoints during development."),
            ("Werkzeug", "backend/database.py and backend/services/*.py", "Handles password hashing and secure uploaded filenames."),
            ("python-dotenv", "backend/app.py and backend/agents/openai_config.py", "Loads .env settings such as MongoDB URI, OpenAI key, Flask config, SMTP, and Twilio values."),
            ("Pydantic", "backend/schemas/agentic.py", "Validates structured agentic API payloads."),
            ("pytest", "backend/tests/test_security_hardening.py", "Runs backend security and regression tests."),
        ],
    ),
    (
        "Database and Persistence",
        [
            ("MongoDB / MongoDB Atlas", "backend/database.py", "Stores users, job descriptions, candidates, comparisons, interviews, audit logs, agent runs, tokens, and counters."),
            ("PyMongo", "backend/database.py", "Connects to MongoDB, creates indexes, queries collections, and updates documents."),
            ("MongoDB indexes", "backend/database.py", "Improves lookups and enforces uniqueness for usernames, job IDs, candidate IDs, comparisons, interviews, and tokens."),
            ("Integer counters", "backend/database.py", "Keeps simple numeric IDs in URLs and payloads while using MongoDB documents internally."),
        ],
    ),
    (
        "AI and Agentic Technologies",
        [
            ("OpenAI Python SDK", "backend/app/llm_extraction.py and backend/agents/*.py", "Performs extraction, resume/JD parsing, matching, ranking, summaries, interview content generation, and recruiter chat."),
            ("LangGraph", "backend/orchestration/hr_graph.py", "Coordinates multi-step HR workflows using graph-based routing and state transitions."),
            ("LangChain dependency", "backend/requirements.txt", "Included as part of the AI/agent workflow stack."),
            ("Agent modules", "backend/agents/*.py", "Separate AI responsibilities into JD, resume, matching, ranking, summary, interview, recruiter, and router agents."),
            ("Workflow modules", "backend/workflows/*.py", "Encapsulate screening, recruiter chat, and application workflows."),
            ("Tool gateway", "backend/tools/tool_gateway.py", "Controls agent access to tools and applies policy checks before actions."),
            ("Security policy", "backend/security/policy.py and backend/security/context_safety.py", "Adds tool-use guardrails, prompt-injection checks, and safer agent execution."),
        ],
    ),
    (
        "File Upload and Parsing",
        [
            ("PyPDF2", "backend/app/text_extractor.py", "Extracts PDF text as one parser fallback."),
            ("PyMuPDF", "backend/app/text_extractor.py", "Extracts PDF text through fitz, useful for complex PDFs."),
            ("pdfplumber", "backend/app/text_extractor.py", "Extracts layout-sensitive PDF text as another fallback."),
            ("python-docx", "backend/app/text_extractor.py", "Extracts text from .docx resumes and job descriptions."),
            ("secure_filename", "backend/services/jd_service.py and backend/services/matching_service.py", "Sanitizes uploaded filenames before saving files."),
            ("Static uploads", "backend/static/uploads", "Stores uploaded resumes and job description files."),
        ],
    ),
    (
        "Communication, Auth, and Tooling",
        [
            ("smtplib / EmailMessage", "backend/services/interview_service.py", "Sends interview emails, follow-ups, and cancellations through SMTP."),
            ("Twilio", "backend/services/interview_service.py and backend/requirements.txt", "Supports SMS/text notifications when configured."),
            ("Custom session token", "frontend/src/api.js, backend/services/auth_service.py, backend/database.py", "Stores a frontend token and validates it against MongoDB."),
            ("Protected React routes", "frontend/src/App.jsx", "Redirects unauthenticated users to /login."),
            ("Audit logs", "backend/database.py and backend/routes/audit_routes.py", "Records important actions with hash-chain integrity checks."),
            ("npm/concurrently/cross-env", "RecruitmentAssist/package.json", "Runs Flask and React together during development."),
            ("requirements.txt / package-lock.json", "backend/requirements.txt and package-lock files", "Locks and documents backend/frontend dependencies."),
        ],
    ),
]


FEATURES = [
    ("Login and authentication", "Login.jsx, auth_routes.py, auth_service.py, database.py", "React, Flask, MongoDB, Werkzeug hashing, session tokens"),
    ("Dashboard", "Dashboard.jsx, dashboard_routes.py, report_service.py", "React, Flatpickr, Flask, MongoDB queries"),
    ("Job descriptions", "JdList.jsx, JdCreate.jsx, JdDetails.jsx, jd_routes.py, jd_service.py", "React, Flask, file upload, PDF/DOCX parsing, OpenAI, MongoDB"),
    ("Candidate management", "Candidates.jsx, CandidateProfile.jsx, candidate_routes.py, candidate_service.py", "React, Flask, MongoDB, resume parsing"),
    ("Resume/JD comparison", "Comparison.jsx, matching_service.py, screening_workflow.py", "React multipart upload, Flask, OpenAI, agent workflow, MongoDB"),
    ("Interviews", "Interviews.jsx, interview_routes.py, interview_service.py", "React, Flask, MongoDB, SMTP, Twilio, OpenAI drafts"),
    ("Reports and insights", "Reports.jsx, report_routes.py, report_service.py", "React, Flask, MongoDB reporting queries"),
    ("Recruiter chat", "FloatingRecruiterChat.jsx, recruiter_chat_workflow.py, recruiter_agent.py", "React, Flask, OpenAI, tool gateway, MongoDB"),
    ("Agent orchestration", "hr_graph.py, main_orchestrator.py, backend/agents/*.py", "LangGraph, OpenAI, Flask, MongoDB, security policy"),
]


def add_row(page: PdfPage, y: float, name: str, where: str, why: str) -> float:
    if y < 92:
        return -1
    page.text(MARGIN, y, name, 9, "F2")
    y = page.wrapped_text(MARGIN + 142, y, f"Where: {where}", 86, 8, 10)
    y = page.wrapped_text(MARGIN + 142, y, f"Why: {why}", 86, 8, 10)
    y -= 7
    return y


def overview_page() -> PdfPage:
    page = PdfPage()
    page.title("Technology Stack and Usage Document", "Recruitment Assist full-stack AI recruitment application")
    y = 500
    page.text(MARGIN, y, "Project Overview", 13, "F2")
    y -= 22
    y = page.wrapped_text(
        MARGIN,
        y,
        "Recruitment Assist is a full-stack AI-powered recruitment platform. It manages job descriptions, resumes, candidate comparison, interview scheduling, communication drafts, dashboards, reports, and recruiter assistance.",
        118,
        10,
        14,
    )
    y -= 10
    page.text(MARGIN, y, "Core Stack", 13, "F2")
    y -= 24
    boxes = [
        ("React", "Frontend UI"),
        ("Flask", "Backend API"),
        ("MongoDB", "Database"),
        ("OpenAI", "AI extraction"),
        ("LangGraph", "Agent workflow"),
        ("PDF/DOCX", "Parsing"),
    ]
    x = MARGIN
    for title, subtitle in boxes:
        page.rect(x, y - 46, 108, 48)
        page.text(x + 10, y - 18, title, 11, "F2")
        page.text(x + 10, y - 33, subtitle, 8)
        x += 124
    y -= 82
    page.text(MARGIN, y, "Application Flow", 13, "F2")
    y -= 22
    flow = [
        "1. User works in the React frontend.",
        "2. frontend/src/api.js sends requests to Flask and attaches the session token.",
        "3. Flask routes call services, workflows, or agents.",
        "4. MongoDB stores users, jobs, candidates, comparisons, interviews, audit logs, and agent runs.",
        "5. OpenAI and LangGraph power extraction, screening, matching, summaries, and recruiter assistance.",
    ]
    for item in flow:
        y = page.wrapped_text(MARGIN + 10, y, item, 112, 9, 13)
    page.footer(1)
    return page


def section_pages(start_page_no: int) -> list[PdfPage]:
    pages: list[PdfPage] = []
    page_no = start_page_no
    for title, rows in SECTIONS:
        page = PdfPage()
        page.title(title, "Where each technology is used and why")
        y = 500
        for name, where, why in rows:
            next_y = add_row(page, y, name, where, why)
            if next_y == -1:
                page.footer(page_no)
                pages.append(page)
                page_no += 1
                page = PdfPage()
                page.title(title, "Continued")
                y = 500
                next_y = add_row(page, y, name, where, why)
            y = next_y
        page.footer(page_no)
        pages.append(page)
        page_no += 1
    return pages


def feature_page(page_no: int) -> PdfPage:
    page = PdfPage()
    page.title("Feature-Wise Stack Mapping", "Main features and the technologies behind them")
    y = 500
    for feature, files, stack in FEATURES:
        page.text(MARGIN, y, feature, 9, "F2")
        y = page.wrapped_text(MARGIN + 156, y, f"Files: {files}", 82, 8, 10)
        y = page.wrapped_text(MARGIN + 156, y, f"Tech: {stack}", 82, 8, 10)
        y -= 7
    page.footer(page_no)
    return page


def summary_page(page_no: int) -> PdfPage:
    page = PdfPage()
    page.title("Why This Stack Fits", "Summary")
    y = 500
    paragraphs = [
        "React fits because the application has many interactive screens, protected routes, upload flows, forms, modals, dashboards, and recruiter workflows.",
        "Flask fits because the backend needs lightweight API routing, file upload handling, session handling, and direct integration with Python AI and document-processing libraries.",
        "MongoDB fits because recruitment data is flexible: resumes, parsed profiles, job descriptions, comparisons, interviews, audit logs, and agent outputs can vary in shape.",
        "OpenAI fits because the core product depends on natural language understanding: extracting resume/JD details, comparing profiles, creating summaries, generating interview messages, and powering recruiter chat.",
        "LangGraph fits because screening and recruiter assistance are multi-step workflows that need routing, state management, and controlled agent coordination.",
        "PDF/DOCX parsing, SMTP, and Twilio support real recruiter workflows: uploaded documents, email communication, and optional text notifications.",
    ]
    for paragraph in paragraphs:
        y = page.wrapped_text(MARGIN, y, paragraph, 116, 9, 13)
        y -= 8
    y -= 4
    page.text(MARGIN, y, "Final Stack", 12, "F2")
    y -= 22
    page.wrapped_text(
        MARGIN + 10,
        y,
        "React frontend + Flask backend + MongoDB database + OpenAI AI layer + LangGraph workflow orchestration + PDF/DOCX parsing + SMTP/Twilio communication + custom authentication and audit logging.",
        112,
        10,
        14,
    )
    page.footer(page_no)
    return page


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
    output = root / "docs" / "tech_stack_usage_document.pdf"
    pages = [overview_page()]
    pages.extend(section_pages(2))
    pages.append(feature_page(len(pages) + 1))
    pages.append(summary_page(len(pages) + 1))
    write_pdf(output, pages)
    print(output)


if __name__ == "__main__":
    main()
