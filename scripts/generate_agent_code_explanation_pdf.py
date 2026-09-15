from __future__ import annotations

from pathlib import Path


PAGE_W = 842
PAGE_H = 595
MARGIN = 44


def esc(text: object) -> str:
    value = str(text)
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class PdfPage:
    """Small PDF drawing helper used to create the architecture explanation document."""

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
        self.text(MARGIN, 19, "RecruitmentAssist - Agent Code Explanation", 7)
        self.text(PAGE_W - MARGIN - 42, 19, f"Page {page_no}", 7)

    def stream(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1")


def overview_page() -> PdfPage:
    p = PdfPage()
    p.title("Agent Code Explanation", "How to explain every major agent and orchestrator file")
    y = 500
    p.text(MARGIN, y, "High level idea", 13, "F2")
    y -= 22
    y = p.wrapped_text(MARGIN, y, "The project uses one Main HR Orchestrator and one LangGraph StateGraph. The graph starts at a Router Agent, then sends the request to a role-specific path such as screening, chat, JD, candidate, interview, dashboard, reports, or unsupported.", 118, 10, 14)
    y -= 4
    p.text(MARGIN, y, "Code layers to explain", 13, "F2")
    y -= 22
    bullets = [
        "Flask route layer: receives requests, files, and authenticated user context.",
        "Main orchestrator: creates run_id, stores agent_runs status, invokes the graph.",
        "LangGraph graph: defines nodes, conditional routing, and final response normalization.",
        "Agents: role-specific code for routing, JD loading, resume extraction, matching, ranking, summary, chat, and interview questions.",
        "Tools and workflows: reusable helpers for database, matching persistence, recruiter context, and application tasks.",
    ]
    for item in bullets:
        y = p.wrapped_text(MARGIN + 12, y, f"- {item}", 116, 9, 13)
    p.box(68, 125, 190, 60, "Key message", ["Agents are specialized", "Router decides route", "Graph coordinates work"])
    p.box(318, 125, 190, 60, "Screening", ["JD -> Resume", "Matching -> Ranking", "Summary"])
    p.box(568, 125, 190, 60, "Traceability", ["run_id", "agent_runs", "trace_start/end"])
    p.arrow(258, 155, 318, 155)
    p.arrow(508, 155, 568, 155)
    p.footer(1)
    return p


def architecture_page() -> PdfPage:
    p = PdfPage()
    p.title("Architecture Diagram", "Code modules and runtime flow")
    p.box(42, 450, 120, 54, "Frontend", ["api.js", "floating chat", "screening form"])
    p.box(205, 450, 132, 54, "Flask API", ["agentic_routes.py", "auth user"])
    p.box(380, 450, 150, 54, "Main Orchestrator", ["main_orchestrator.py", "agent_runs"])
    p.box(572, 450, 155, 54, "LangGraph", ["hr_graph.py", "StateGraph"])
    p.arrow(162, 477, 205, 477)
    p.arrow(337, 477, 380, 477)
    p.arrow(530, 477, 572, 477)

    p.box(78, 335, 135, 55, "Router Agent", ["router_agent.py", "route decision"])
    p.box(262, 335, 135, 55, "Screening Agents", ["jd/resume", "match/rank/summary"])
    p.box(446, 335, 135, 55, "Chat Agent", ["recruiter_agent.py", "chat actions"])
    p.box(630, 335, 135, 55, "App Workflow", ["JD/candidate", "interview/report"])
    p.arrow(650, 450, 145, 390)
    p.arrow(145, 335, 330, 390)
    p.arrow(145, 335, 514, 390)
    p.arrow(145, 335, 698, 390)

    p.box(118, 205, 170, 62, "Tools", ["jd_tools.py", "resume_tools.py", "matching_tools.py"])
    p.box(342, 205, 170, 62, "Services", ["candidate_service.py", "jd_service.py", "interview_service.py"])
    p.box(566, 205, 170, 62, "Database", ["MongoDB helpers", "agent_runs"])
    p.arrow(330, 335, 203, 267)
    p.arrow(514, 335, 427, 267)
    p.arrow(698, 335, 651, 267)
    p.footer(2)
    return p


def orchestrator_page() -> PdfPage:
    p = PdfPage()
    p.title("Orchestrator Code", "What to say about main_orchestrator.py and hr_graph.py")
    y = 500
    items = [
        ("_task_type", "Infers the task label used for run tracking from task_type, type, message, or jd_id."),
        ("_safe_input", "Removes private fields and uploaded file objects before saving run input metadata."),
        ("run_main_orchestrator", "Creates run_id, writes running status, invokes run_hr_graph, then writes completed or failed output."),
        ("HRGraphState", "Typed dictionary that carries payload, route, contexts, errors, path result, and final response between nodes."),
        ("router_node", "Runs route_request and stores route_decision plus route in graph state."),
        ("route_after_router", "Conditional edge function that decides which branch runs after the router."),
        ("final_response_node", "Converts each branch result into the stable API response shape."),
        ("build_hr_graph", "Registers LangGraph nodes and edges, then compiles the graph once."),
    ]
    for name, desc in items:
        p.text(MARGIN, y, name, 10, "F2")
        y = p.wrapped_text(MARGIN + 132, y, desc, 90, 9, 13)
        y -= 6
    p.footer(3)
    return p


def screening_agents_page() -> PdfPage:
    p = PdfPage()
    p.title("Screening Agents", "What each screening function does")
    agents = [
        ("JD Agent", "run_jd_agent loads the JD row and normalized JD JSON. build_jd_agent_prompt documents what the JD Agent would extract."),
        ("Resume Agent", "run_resume_agent builds profiles from existing candidates and uploaded resumes. It records non-fatal extraction errors."),
        ("Matching Agent", "run_matching_agent compares each profile with the JD and persists comparison rows through matching_tools.persist_match."),
        ("Ranking Agent", "run_ranking_agent sorts results by match_score and splits selected_results from rejected_results."),
        ("Summary Agent", "run_summary_agent produces the recruiter-facing summary, selected/rejected counts, top candidate, and errors."),
    ]
    y = 500
    for title, desc in agents:
        p.box(MARGIN, y - 36, 150, 38, title)
        p.wrapped_text(MARGIN + 175, y - 5, desc, 86, 9, 13)
        y -= 72
    p.box(92, 95, 130, 45, "JD")
    p.box(272, 95, 130, 45, "Resume")
    p.box(452, 95, 130, 45, "Match")
    p.box(632, 95, 130, 45, "Rank/Summary")
    p.arrow(222, 118, 272, 118)
    p.arrow(402, 118, 452, 118)
    p.arrow(582, 118, 632, 118)
    p.footer(4)
    return p


def chat_app_page() -> PdfPage:
    p = PdfPage()
    p.title("Chat, Interview, and App Workflow Agents", "How to explain non-screening branches")
    y = 500
    items = [
        ("Router Agent", "deterministic_route handles known task types. route_request uses deterministic routing first and LLM routing only when needed."),
        ("Recruiter Agent", "run_recruiter_agent answers grounded recruiter questions. execute_recruiter_action runs supported chat actions with confirmation for side effects."),
        ("Interview Agent", "run_interview_question_agent generates role-specific interview questions from candidate and JD context."),
        ("App Workflow", "run_app_workflow dispatches JD, candidate, profile, dashboard, report, and interview tasks to existing services."),
        ("Agentic Routes", "api_agentic_run normalizes request payloads, adds authenticated user context, and calls the Main HR Orchestrator."),
    ]
    for name, desc in items:
        p.text(MARGIN, y, name, 10, "F2")
        y = p.wrapped_text(MARGIN + 132, y, desc, 90, 9, 13)
        y -= 14
    p.footer(5)
    return p


def sequence_page() -> PdfPage:
    p = PdfPage()
    p.title("UML Sequence Diagram", "How one request moves through the code")
    lanes = [(54, "Frontend"), (178, "API Route"), (302, "Orchestrator"), (426, "LangGraph"), (550, "Agent"), (674, "DB/Service")]
    for x, label in lanes:
        p.box(x, 500, 94, 30, label, [], "0.94 0.96 0.99")
        p.line(x + 47, 500, x + 47, 86, 0.6)
    messages = [
        (462, 54, 178, "POST request"),
        (422, 178, 302, "run_main_orchestrator"),
        (382, 302, 674, "create_agent_run"),
        (342, 302, 426, "invoke graph"),
        (302, 426, 550, "router/role node"),
        (262, 550, 674, "load or persist data"),
        (222, 550, 426, "path_result"),
        (182, 426, 302, "final_response"),
        (142, 302, 674, "update_agent_run"),
        (102, 302, 178, "result"),
        (78, 178, 54, "JSON"),
    ]
    for y, x1, x2, label in messages:
        p.arrow(x1 + 47, y, x2 + 47, y)
        p.text(min(x1, x2) + 54, y + 8, label, 7)
    p.footer(6)
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
    output = root / "docs" / "agent_code_explanation.pdf"
    pages = [overview_page(), architecture_page(), orchestrator_page(), screening_agents_page(), chat_app_page(), sequence_page()]
    write_pdf(output, pages)
    print(output)


if __name__ == "__main__":
    main()
