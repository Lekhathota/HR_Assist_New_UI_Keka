from __future__ import annotations

from pathlib import Path


PAGE_W = 842
PAGE_H = 595
MARGIN = 44


def esc(text: object) -> str:
    value = str(text)
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class PdfPage:
    def __init__(self, title: str, subtitle: str | None = None) -> None:
        self.ops: list[str] = []
        self.text(MARGIN, PAGE_H - 44, title, 18, "F2")
        if subtitle:
            self.text(MARGIN, PAGE_H - 64, subtitle, 9)
        self.line(MARGIN, PAGE_H - 78, PAGE_W - MARGIN, PAGE_H - 78, 0.8)

    def text(self, x: float, y: float, value: str, size: int = 10, font: str = "F1") -> None:
        self.ops.append(f"BT /{font} {size} Tf {x:.1f} {y:.1f} Td ({esc(value)}) Tj ET")

    def wrapped(self, x: float, y: float, value: str, width_chars: int = 104, size: int = 9, leading: int = 13) -> float:
        words = value.split()
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if len(candidate) > width_chars and line:
                self.text(x, y, line, size)
                y -= leading
                line = word
            else:
                line = candidate
        if line:
            self.text(x, y, line, size)
            y -= leading
        return y

    def heading(self, x: float, y: float, value: str) -> float:
        self.text(x, y, value, 13, "F2")
        return y - 20

    def bullet(self, x: float, y: float, value: str, width_chars: int = 104) -> float:
        return self.wrapped(x + 10, y, f"- {value}", width_chars, 9, 13) - 2

    def line(self, x1: float, y1: float, x2: float, y2: float, width: float = 1.0) -> None:
        self.ops.append(f"q {width:.1f} w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S Q")

    def rect(self, x: float, y: float, w: float, h: float, fill: str = "0.96 0.98 1.00") -> None:
        self.ops.append(f"q {fill} rg 0.18 0.24 0.32 RG 1.0 w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re B Q")

    def box(self, x: float, y: float, w: float, h: float, title: str, lines: list[str], fill: str = "0.96 0.98 1.00") -> None:
        self.rect(x, y, w, h, fill)
        self.text(x + 9, y + h - 17, title, 10, "F2")
        cursor = y + h - 32
        for line in lines:
            self.text(x + 9, cursor, line, 7)
            cursor -= 10

    def arrow(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.line(x1, y1, x2, y2)
        if abs(x2 - x1) >= abs(y2 - y1):
            direction = 1 if x2 >= x1 else -1
            self.line(x2, y2, x2 - 8 * direction, y2 + 5, 0.8)
            self.line(x2, y2, x2 - 8 * direction, y2 - 5, 0.8)
        else:
            direction = 1 if y2 >= y1 else -1
            self.line(x2, y2, x2 - 5, y2 - 8 * direction, 0.8)
            self.line(x2, y2, x2 + 5, y2 - 8 * direction, 0.8)

    def footer(self, page_no: int) -> None:
        self.line(MARGIN, 34, PAGE_W - MARGIN, 34, 0.7)
        self.text(MARGIN, 19, "RecruitmentAssist - Backend and LangGraph Explanation", 7)
        self.text(PAGE_W - MARGIN - 42, 19, f"Page {page_no}", 7)

    def stream(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1")


def page_intro() -> PdfPage:
    p = PdfPage("RecruitmentAssist Backend and LangGraph", "Simple explanation of the backend folder and agent architecture")
    y = 500
    y = p.heading(MARGIN, y, "Tiny Meaning")
    y = p.wrapped(
        MARGIN,
        y,
        "The backend is the hidden kitchen of the HR app. The frontend is what users see. The backend stores data, reads resumes, checks job descriptions, matches candidates, schedules interviews, and talks to AI.",
        118,
        10,
        14,
    )
    y -= 10
    y = p.heading(MARGIN, y, "Main Idea")
    for item in [
        "routes are the doors where frontend requests enter.",
        "services are the workers that do business logic.",
        "database.py is the big notebook that remembers jobs, candidates, interviews, users, and audit logs.",
        "agents are AI helpers for reading, matching, ranking, summarizing, and chatting.",
        "LangGraph is the traffic controller that decides which agent runs first and next.",
    ]:
        y = p.bullet(MARGIN, y, item, 116)
    y -= 8
    y = p.heading(MARGIN, y, "Like You Are 5")
    p.wrapped(
        MARGIN,
        y,
        "Imagine an office helper. One helper opens the door, one writes in the notebook, one reads papers, one compares papers, one makes a list of best people, and one explains the answer. LangGraph tells these helpers whose turn it is.",
        118,
        10,
        14,
    )
    p.footer(1)
    return p


def page_backend_map() -> PdfPage:
    p = PdfPage("Backend Folder Structure", "What each major folder/file does")
    y = 500
    rows = [
        ("app.py", "Starts the Flask backend, connects routes, prepares database and frontend preference."),
        ("database.py", "MongoDB helper. Creates, reads, updates, and deletes jobs, candidates, comparisons, interviews, users, runs, and audit logs."),
        ("routes/", "API doors. Files like jd_routes.py, candidate_routes.py, interview_routes.py, and agentic_routes.py receive frontend requests."),
        ("services/", "Business workers. They prepare JD data, candidate profiles, matching results, interview emails, dashboard data, and auth state."),
        ("agents/", "AI helpers. JD agent, resume agent, matching agent, ranking agent, summary agent, recruiter chat agent, and router agent."),
        ("tools/", "Small controlled tools used by agents, with a gateway and policy checks before important actions."),
        ("workflows/", "Recipes for bigger tasks such as screening, recruiter chat, and app actions."),
        ("orchestration/", "LangGraph and orchestrator layer. This is where the graph is built and executed."),
        ("app/", "Text extraction, regex extraction, LLM extraction, matching rules, summaries, and utility functions."),
        ("security/", "Safety guard. Checks prompt injection and controls what tools/actions are allowed."),
        ("schemas/", "Request validation forms, especially for agentic payloads."),
        ("static/uploads/", "Uploaded resumes and job description files."),
        ("tests/", "Security tests that check validation, policy, prompt injection, and audit behavior."),
    ]
    for name, desc in rows:
        p.text(MARGIN, y, name, 10, "F2")
        y = p.wrapped(MARGIN + 145, y, desc, 88, 9, 12)
        y -= 4
    p.footer(2)
    return p


def page_important_files() -> PdfPage:
    p = PdfPage("Important Files and Functions", "Simple jobs of the main Python parts")
    y = 500
    sections = [
        ("database.py", ["create_jd adds a job.", "create_candidate adds a candidate.", "upsert_comparison saves matching results.", "create_interview stores interview details.", "authenticate_user checks login."]),
        ("jd_service.py", ["allowed_file checks uploaded file types.", "create_jd_from_upload reads and saves a JD.", "jd_details_payload prepares JD details for frontend."]),
        ("candidate_service.py", ["normalize_candidate_record cleans candidate data.", "candidates_payload builds candidate list.", "candidate_profile_payload builds one full candidate profile."]),
        ("matching_service.py", ["run_matching compares resumes with a JD.", "run_matching_from_paths compares already saved resume files."]),
        ("interview_service.py", ["generate_interview_email writes invite email.", "assert_slot_available checks interview time.", "send_email sends the message."]),
        ("security files", ["context_safety.py detects unsafe prompt text.", "policy.py decides which tool actions are allowed."]),
    ]
    for title, bullets in sections:
        y = p.heading(MARGIN, y, title)
        for item in bullets:
            y = p.bullet(MARGIN, y, item, 112)
        y -= 4
    p.footer(3)
    return p


def page_langgraph_simple() -> PdfPage:
    p = PdfPage("How LangGraph Works Here", "The traffic controller for agents")
    y = 500
    y = p.heading(MARGIN, y, "Where It Lives")
    y = p.wrapped(MARGIN, y, "LangGraph is mainly used in RecruitmentAssist/backend/orchestration/hr_graph.py.", 118, 10, 14)
    y -= 8
    y = p.heading(MARGIN, y, "What It Does")
    for item in [
        "It creates a StateGraph named HRGraphState.",
        "It adds nodes such as router, jd_agent, resume_agent, matching_agent, ranking_agent, summary_agent, recruiter_chat_agent, and final_response.",
        "It connects nodes with edges, which means after this step, go to that step.",
        "It uses conditional edges after the router so only the correct path runs.",
        "It returns one final response shape back to Flask and then the frontend.",
    ]:
        y = p.bullet(MARGIN, y, item, 116)
    y -= 8
    y = p.heading(MARGIN, y, "The Shared Backpack")
    p.wrapped(
        MARGIN,
        y,
        "HRGraphState is like a backpack passed from node to node. It can carry payload, username, run_id, task_type, route decision, jd_id, JD context, resume context, match result, ranking result, summary, errors, and final_response.",
        118,
        10,
        14,
    )
    p.footer(4)
    return p


def page_langgraph_flow() -> PdfPage:
    p = PdfPage("LangGraph Flow Diagram", "How a request travels through the graph")
    p.box(70, 455, 125, 46, "Frontend", ["User clicks", "or uploads files"])
    p.box(235, 455, 125, 46, "Flask Route", ["agentic_routes.py", "/api/agentic/run"])
    p.box(400, 455, 145, 46, "Main Orchestrator", ["creates run_id", "stores running"])
    p.box(585, 455, 145, 46, "LangGraph", ["StateGraph", "router first"])
    p.arrow(195, 478, 235, 478)
    p.arrow(360, 478, 400, 478)
    p.arrow(545, 478, 585, 478)

    p.box(335, 365, 170, 48, "Router Node", ["route_request(payload)", "choose path"], "0.98 0.98 0.92")
    p.arrow(657, 455, 420, 413)

    p.box(65, 255, 180, 72, "Screening Path", ["screening_entry", "jd_agent", "resume_agent", "matching_agent", "ranking_agent", "summary_agent"], "0.95 0.99 0.95")
    p.box(330, 255, 180, 72, "Chat Path", ["recruiter_context", "recruiter_chat_agent"], "0.95 0.98 1.00")
    p.box(595, 255, 180, 72, "App Role Path", ["jd/candidate/interview", "dashboard/reports", "run_app_workflow"], "0.98 0.96 1.00")

    p.arrow(420, 365, 155, 327)
    p.arrow(420, 365, 420, 327)
    p.arrow(420, 365, 685, 327)

    p.box(335, 145, 170, 48, "Final Response Node", ["normalize output", "send to API"])
    p.arrow(155, 255, 420, 193)
    p.arrow(420, 255, 420, 193)
    p.arrow(685, 255, 420, 193)

    p.box(335, 75, 170, 38, "Frontend Result", ["JSON response"])
    p.arrow(420, 145, 420, 113)
    p.footer(5)
    return p


def page_langgraph_paths() -> PdfPage:
    p = PdfPage("LangGraph Paths", "What happens for each kind of request")
    y = 500
    y = p.heading(MARGIN, y, "Screening Request")
    y = p.wrapped(MARGIN, y, "Used when the app needs to screen candidates for a job description.", 118, 10, 14)
    for item in [
        "screening_entry_node checks that jd_id exists.",
        "jd_agent_node loads and understands the selected job description.",
        "resume_agent_node turns candidate ids or uploaded resumes into clean profiles.",
        "matching_agent_node compares each profile with the JD and saves comparison records.",
        "ranking_agent_node sorts candidates into ranked/selected/rejected style output.",
        "summary_agent_node creates the final explanation.",
    ]:
        y = p.bullet(MARGIN, y, item, 116)
    y -= 8
    y = p.heading(MARGIN, y, "Chat Request")
    for item in [
        "recruiter_context_node checks the message/action is valid.",
        "recruiter_chat_agent_node runs recruiter_chat_workflow.",
        "It can answer recruiter questions or prepare confirmed actions.",
    ]:
        y = p.bullet(MARGIN, y, item, 116)
    y -= 8
    y = p.heading(MARGIN, y, "App Requests")
    for item in [
        "JD, candidate, interview, dashboard, and reports routes go through app_role_node.",
        "app_role_node calls run_app_workflow, which dispatches the right backend service/tool.",
    ]:
        y = p.bullet(MARGIN, y, item, 116)
    p.footer(6)
    return p


def page_request_lifecycle() -> PdfPage:
    p = PdfPage("Request Lifecycle", "From frontend request to final answer")
    y = 500
    steps = [
        "Frontend sends JSON or uploaded files to /api/agentic/run.",
        "agentic_routes.py normalizes the request into one payload.",
        "validate_agentic_payload checks that the request is allowed and shaped correctly.",
        "run_main_orchestrator creates a run_id and saves an agent run as running.",
        "run_hr_graph invokes the compiled LangGraph graph.",
        "router_node chooses the path.",
        "The selected nodes run and update HRGraphState.",
        "final_response_node creates the final API response.",
        "main_orchestrator saves completed output, or failed error if something breaks.",
        "Flask sends JSON back to the frontend.",
    ]
    for idx, step in enumerate(steps, start=1):
        p.text(MARGIN, y, f"{idx}.", 9, "F2")
        y = p.wrapped(MARGIN + 28, y, step, 112, 9, 13)
        y -= 3
    y -= 6
    y = p.heading(MARGIN, y, "Why This Is Useful")
    for item in [
        "The app does not need one huge messy function.",
        "Each agent has one clear job.",
        "The graph makes the order easy to see.",
        "Failed runs can be saved and inspected.",
        "New paths can be added later by adding nodes and edges.",
    ]:
        y = p.bullet(MARGIN, y, item, 116)
    p.footer(7)
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

    pages_ref = len(objects) + len(pages) + 1
    for content_ref in content_refs:
        page_obj = (
            f"<< /Type /Page /Parent {pages_ref} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /Font << /F1 {font1} 0 R /F2 {font2} 0 R >> >> "
            f"/Contents {content_ref} 0 R >>"
        ).encode("ascii")
        page_refs.append(add(page_obj))

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
    output = root / "docs" / "backend_and_langgraph_explanation.pdf"
    pages = [
        page_intro(),
        page_backend_map(),
        page_important_files(),
        page_langgraph_simple(),
        page_langgraph_flow(),
        page_langgraph_paths(),
        page_request_lifecycle(),
    ]
    write_pdf(output, pages)
    print(output)


if __name__ == "__main__":
    main()
