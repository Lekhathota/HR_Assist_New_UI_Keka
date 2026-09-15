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
        self.text(MARGIN, 19, "Recruitment Assist - Technical Documentation", 7)
        self.text(PAGE_W - MARGIN - 42, 19, f"Page {page_no}", 7)

    def wrapped_text(
        self,
        x: float,
        y: float,
        value: str,
        width_chars: int = 112,
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

    def bullet(self, x: float, y: float, value: str, width_chars: int = 106) -> float:
        return self.wrapped_text(x, y, f"- {value}", width_chars, 8, 11)

    def box(self, x: float, y: float, w: float, h: float, title: str, lines: list[str]) -> None:
        self.rect(x, y, w, h)
        self.text(x + 10, y + h - 18, title, 10, "F2")
        cursor = y + h - 34
        for line in lines:
            self.text(x + 10, cursor, line, 7)
            cursor -= 10

    def arrow(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.line(x1, y1, x2, y2)
        if abs(x2 - x1) >= abs(y2 - y1):
            direction = 1 if x2 >= x1 else -1
            self.line(x2, y2, x2 - 8 * direction, y2 + 5, 0.7)
            self.line(x2, y2, x2 - 8 * direction, y2 - 5, 0.7)
        else:
            direction = 1 if y2 >= y1 else -1
            self.line(x2, y2, x2 - 5, y2 - 8 * direction, 0.7)
            self.line(x2, y2, x2 + 5, y2 - 8 * direction, 0.7)

    def stream(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1")


SECTIONS = [
    (
        "Introduction",
        [
            "Recruitment Assist is a full-stack AI recruitment platform for managing clients, job descriptions, candidates, resume screening, assessments, interviews, vendors, dashboards, reports, and recruiter assistance.",
            "The application combines a React frontend, Flask backend, MongoDB persistence layer, OpenAI-based extraction/generation, and local agent workflow modules.",
        ],
    ),
    (
        "Technology Stack",
        [
            "Frontend: React 18, React Router DOM, Create React App, custom CSS, Flatpickr, jsPDF, xlsx, docx, and file-saver.",
            "Backend: Python, Flask, Flask-CORS, Werkzeug, python-dotenv, Pydantic, and pytest.",
            "Database: MongoDB through PyMongo with indexes, integer counters, session tokens, audit logs, and cached dashboard metrics.",
            "AI/workflows: OpenAI Python SDK, LangGraph/LangChain packages, local agents, workflow modules, and a controlled tool gateway.",
            "Document processing: PyPDF2, PyMuPDF, pdfplumber, and python-docx.",
            "Communication: SMTP email and optional Twilio SMS.",
        ],
    ),
    (
        "Project Structure",
        [
            "frontend/src/pages contains the main React screens: Dashboard, Candidates, JD pages, Comparison, Interviews, Reports, Vendors, Assessments, Workflow Admin, and Profile.",
            "frontend/src/components contains shared layout, navigation, recruiter chat, and feedback components.",
            "backend/routes contains Flask blueprints grouped by feature.",
            "backend/services contains business logic for auth, JDs, candidates, matching, interviews, reports, vendors, assessments, fulfilment, workflow admin, and prompts.",
            "backend/agents contains role-specific AI agents for routing, JD parsing, resume parsing, matching, ranking, summaries, interviews, and recruiter chat.",
            "backend/tools contains controlled agent tools such as JD context loading, resume profile extraction, matching persistence, recruiter context, and the tool gateway.",
            "backend/workflows and backend/orchestration contain multi-step workflows, the main orchestrator, LangGraph state graph, and tracing.",
        ],
    ),
    (
        "Backend Architecture",
        [
            "backend/app.py loads environment variables, creates the Flask app, configures upload limits and CORS, registers feature blueprints, initializes MongoDB, and redirects non-API browser requests to the React frontend.",
            "Routes validate HTTP inputs and return JSON responses.",
            "Services implement business rules, persistence workflows, matching, fulfilment, email/SMS handling, assessment lifecycle, vendors, reporting, and workflow admin controls.",
            "Agents perform AI-assisted extraction, matching, ranking, summarization, interview content generation, and recruiter chat.",
            "database.py centralizes MongoDB access, indexes, counters, serialization, audit logs, session tokens, and dashboard metrics.",
        ],
    ),
    (
        "Frontend Architecture",
        [
            "The React frontend is a single-page application with protected routes.",
            "frontend/src/api.js centralizes backend communication and session token handling.",
            "Key screens include Dashboard, Job Description list/create/details, Candidates, Candidate Profile, Comparison, Interviews, Reports, Vendors, Assessments, Workflow Admin, Login, and Profile.",
            "The frontend uses page-specific CSS files under frontend/src/styles plus shared application styles.",
        ],
    ),
    (
        "Database Collections",
        [
            "users and user_session_tokens store login accounts and expiring API session tokens.",
            "clients and projects store account ownership metadata.",
            "job_descriptions store parsed JD data, categories, status, workflow state, and fulfilment counters.",
            "candidates store uploaded/internal/vendor candidates, resume metadata, structured profile data, category fields, and hiring status.",
            "comparisons store JD-candidate match records, scores, summaries, selection status, and workflow metadata.",
            "interviews store schedule data, email/SMS state, follow-up/cancellation content, and outcomes.",
            "vendors, jd_vendor_assignments, and vendor_email_logs support external vendor fulfilment and communication.",
            "assessments, questions, candidate_answers, and assessment_results store assessment lifecycle data.",
            "agent_runs tracks agentic task execution, while audit_logs stores a hash-chained audit trail.",
        ],
    ),
    (
        "AI and Agentic Architecture",
        [
            "main_orchestrator.py creates run IDs, determines task type, records status, and dispatches work.",
            "hr_graph.py defines graph-based HR routing and state transitions.",
            "screening_workflow.py runs the JD, resume, matching, ranking, and summary sequence.",
            "recruiter_chat_workflow.py handles recruiter messages, context retrieval, answer generation, and action proposals.",
            "router_agent.py, jd_agent.py, resume_agent.py, matching_agent.py, ranking_agent.py, summary_agent.py, interview_agent.py, and recruiter_agent.py split AI responsibilities by role.",
            "tool_gateway.py and security/policy.py provide controlled tool execution and audit-aware guardrails.",
        ],
    ),
    (
        "Security and Operations",
        [
            "Passwords use Werkzeug password hashing.",
            "API sessions use MongoDB-backed tokens with TTL.",
            "Uploaded filenames are sanitized and Flask enforces a maximum upload size.",
            "Audit logs use previous/current hashes to support tamper detection.",
            "Sensitive audit parameters are redacted before storage.",
            "Production should enable secure cookies, restricted CORS, HTTPS, managed secrets, controlled upload storage, and least-privilege MongoDB credentials.",
        ],
    ),
]


API_GROUPS = [
    ("Auth/Profile", "/api/login, /api/logout, /api/profile"),
    ("Dashboard/Reports", "/api/dashboard, /api/metrics/jd-performance, /api/reports, /api/report/email"),
    ("Job Descriptions", "/api/jds, /api/jds/create, /api/jds/<id>, delete endpoint"),
    ("Candidates", "/api/candidates, /api/candidates/<id>, /api/candidates/repair"),
    ("Matching/Fulfilment", "/api/compare, /api/jds/<id>/fulfilment, recalculate endpoint"),
    ("Interviews", "/api/interviews plus schedule, reschedule, email, follow-up, outcome, cancellation"),
    ("Assessments", "generate, lookup, save draft, question CRUD, preview, email, send, token, answer, submit, result"),
    ("Agentic", "/api/agentic/run, /api/agentic/screening, /api/agentic/runs"),
    ("Vendors", "/api/vendors plus JD assignment, email, history, and candidate acceptance"),
    ("Workflow Admin", "/api/admin/workflow-readiness, backfill, required count, categories, overrides, timeline"),
    ("Audit", "/api/audit/logs"),
]


SETUP_ITEMS = [
    "Create and activate a Python virtual environment.",
    "Install backend dependencies from backend/requirements.txt.",
    "Configure backend/.env with MongoDB, OpenAI, CORS, Flask, SMTP, and optional Twilio values.",
    "Install frontend dependencies in frontend with npm install.",
    "Run the Flask backend and React frontend, or use the root helper scripts when available.",
    "Run backend pytest tests and frontend build before handing off changes.",
]


ENV_ITEMS = [
    "MONGODB_URI or MONGO_URI",
    "MONGODB_DB or MONGO_DB",
    "SECRET_KEY",
    "CORS_ORIGINS",
    "FRONTEND_URL",
    "OPENAI_API_KEY",
    "SMTP settings for email delivery",
    "Twilio settings for optional SMS",
    "SESSION_TOKEN_TTL_HOURS",
    "SEED_DEFAULT_USERS and local default user passwords",
]


def overview_page() -> PdfPage:
    p = PdfPage()
    p.title("Recruitment Assist Technical Documentation", "Full-stack AI recruitment application")
    y = 500
    p.text(MARGIN, y, "System Purpose", 13, "F2")
    y -= 22
    y = p.wrapped_text(
        MARGIN,
        y,
        "Recruitment Assist helps recruiters manage job descriptions, candidate profiles, resume/JD matching, assessments, interviews, vendor fulfilment, dashboards, reports, and AI-assisted recruiter workflows.",
        116,
        10,
        14,
    )
    y -= 12
    p.text(MARGIN, y, "Core Runtime", 13, "F2")
    y -= 24
    boxes = [
        ("React", "User interface"),
        ("Flask", "API backend"),
        ("MongoDB", "Persistence"),
        ("OpenAI", "AI extraction"),
        ("Agents", "Workflow logic"),
        ("SMTP/Twilio", "Messaging"),
    ]
    x = MARGIN
    for title, subtitle in boxes:
        p.rect(x, y - 48, 108, 50)
        p.text(x + 10, y - 18, title, 11, "F2")
        p.text(x + 10, y - 34, subtitle, 8)
        x += 124
    y -= 90
    p.text(MARGIN, y, "Request Flow", 13, "F2")
    y -= 24
    for item in [
        "Recruiter/Admin uses the React frontend.",
        "frontend/src/api.js sends requests to Flask API endpoints.",
        "Routes call services, workflows, agents, or controlled tools.",
        "Services read/write MongoDB collections and integrate communication utilities.",
        "Agents use OpenAI and local context to parse, match, rank, summarize, and assist.",
    ]:
        y = p.bullet(MARGIN + 10, y, item)
        y -= 2
    p.footer(1)
    return p


def architecture_page(page_no: int) -> PdfPage:
    p = PdfPage()
    p.title("Architecture Diagram", "High-level application structure")
    p.box(48, 452, 120, 54, "Users", ["Recruiter", "Admin/Manager"])
    p.box(210, 452, 135, 54, "React Frontend", ["Pages", "Components", "api.js"])
    p.box(386, 452, 135, 54, "Flask API", ["Blueprint routes", "Auth/session"])
    p.box(562, 452, 120, 54, "Services", ["Business rules", "Persistence"])
    p.box(706, 452, 92, 54, "MongoDB", ["Collections", "Indexes"])
    p.arrow(168, 479, 210, 479)
    p.arrow(345, 479, 386, 479)
    p.arrow(521, 479, 562, 479)
    p.arrow(682, 479, 706, 479)

    p.box(92, 320, 145, 66, "Orchestration", ["main_orchestrator.py", "hr_graph.py", "tracing.py"])
    p.box(278, 320, 145, 66, "Workflows", ["screening", "recruiter chat", "app workflow"])
    p.box(464, 320, 145, 66, "Agents", ["JD/resume", "matching/ranking", "summary/chat"])
    p.box(650, 320, 120, 66, "OpenAI", ["Extraction", "Generation"])
    p.arrow(454, 452, 164, 386)
    p.arrow(237, 353, 278, 353)
    p.arrow(423, 353, 464, 353)
    p.arrow(609, 353, 650, 353)

    p.box(170, 198, 150, 64, "Tools", ["jd_tools.py", "resume_tools.py", "matching_tools.py"])
    p.box(390, 198, 150, 64, "Tool Gateway", ["Policy checks", "Audit output"])
    p.box(610, 198, 140, 64, "Security", ["policy.py", "context_safety.py"])
    p.arrow(536, 320, 245, 262)
    p.arrow(320, 230, 390, 230)
    p.arrow(540, 230, 610, 230)

    p.text(70, 120, "The application keeps UI, API, business services, persistence, and agent behavior separated.", 10, "F2")
    p.text(70, 102, "That separation makes the system easier to document, test, and extend.", 10)
    p.footer(page_no)
    return p


def section_pages(start_page_no: int) -> list[PdfPage]:
    pages: list[PdfPage] = []
    page_no = start_page_no
    for title, bullets in SECTIONS:
        p = PdfPage()
        p.title(title, "Technical documentation")
        y = 500
        for item in bullets:
            y = p.bullet(MARGIN + 10, y, item)
            y -= 5
        p.footer(page_no)
        pages.append(p)
        page_no += 1
    return pages


def api_page(page_no: int) -> PdfPage:
    p = PdfPage()
    p.title("API Reference Summary", "Main endpoint groups")
    y = 500
    for group, endpoints in API_GROUPS:
        p.text(MARGIN, y, group, 9, "F2")
        y = p.wrapped_text(MARGIN + 148, y, endpoints, 88, 8, 11)
        y -= 8
    p.footer(page_no)
    return p


def setup_page(page_no: int) -> PdfPage:
    p = PdfPage()
    p.title("Setup, Environment, Testing", "Operational guidance")
    y = 500
    p.text(MARGIN, y, "Setup Steps", 12, "F2")
    y -= 22
    for item in SETUP_ITEMS:
        y = p.bullet(MARGIN + 10, y, item)
        y -= 2
    y -= 12
    p.text(MARGIN, y, "Important Environment Variables", 12, "F2")
    y -= 22
    left = ENV_ITEMS[:5]
    right = ENV_ITEMS[5:]
    ly = y
    for item in left:
        ly = p.bullet(MARGIN + 10, ly, item, 48)
    ry = y
    for item in right:
        ry = p.bullet(MARGIN + 390, ry, item, 48)
    y = min(ly, ry) - 16
    p.text(MARGIN, y, "Validation Checklist", 12, "F2")
    y -= 22
    for item in [
        "Run backend pytest tests.",
        "Run frontend build.",
        "Manually test login, JD upload, candidate upload, matching, assessments, interviews, vendors, workflow admin, and reports.",
    ]:
        y = p.bullet(MARGIN + 10, y, item)
    p.footer(page_no)
    return p


def deployment_page(page_no: int) -> PdfPage:
    p = PdfPage()
    p.title("Deployment and Troubleshooting", "Production notes")
    y = 500
    p.text(MARGIN, y, "Deployment Guide", 12, "F2")
    y -= 22
    for item in [
        "Build the React frontend with npm run build.",
        "Deploy Flask behind a WSGI server or managed Python platform.",
        "Use MongoDB Atlas or another managed MongoDB deployment.",
        "Keep secrets outside source control.",
        "Configure production CORS origins, HTTPS, secure cookies, upload storage, and retention policy.",
    ]:
        y = p.bullet(MARGIN + 10, y, item)
        y -= 2
    y -= 12
    p.text(MARGIN, y, "Troubleshooting", 12, "F2")
    y -= 22
    for item in [
        "Database unavailable: verify URI, network access, database permissions, and Atlas IP rules.",
        "Login failure: verify users, password hashes, and session token storage.",
        "Frontend cannot call backend: verify backend port, API base URL/proxy, and CORS origins.",
        "Parsing issues: check file type, upload folder, parser dependencies, and extraction logs.",
        "AI output issues: verify OPENAI_API_KEY, prompt inputs, and JSON parser fallbacks.",
        "Email/SMS failures: verify SMTP/Twilio configuration and recipient fields.",
    ]:
        y = p.bullet(MARGIN + 10, y, item)
    p.footer(page_no)
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
    output = root / "docs" / "recruitment_assist_technical_documentation.pdf"
    pages = [overview_page(), architecture_page(2)]
    pages.extend(section_pages(3))
    pages.append(api_page(len(pages) + 1))
    pages.append(setup_page(len(pages) + 1))
    pages.append(deployment_page(len(pages) + 1))
    write_pdf(output, pages)
    print(output)


if __name__ == "__main__":
    main()
