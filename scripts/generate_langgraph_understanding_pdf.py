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

    def wrapped_text(self, x: float, y: float, value: str, width_chars: int = 98, size: int = 9, leading: int = 13) -> float:
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
            self.line(x2, y2, x2 - 8 * direction, y2 + 5, 0.9)
            self.line(x2, y2, x2 - 8 * direction, y2 - 5, 0.9)
        else:
            direction = 1 if y2 >= y1 else -1
            self.line(x2, y2, x2 - 5, y2 - 8 * direction, 0.9)
            self.line(x2, y2, x2 + 5, y2 - 8 * direction, 0.9)

    def rect(self, x: float, y: float, w: float, h: float, fill: str = "0.96 0.98 1.00") -> None:
        self.ops.append(f"q {fill} rg 0.18 0.24 0.32 RG 1.1 w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re B Q")

    def box(self, x: float, y: float, w: float, h: float, title: str, lines: list[str] | None = None, fill: str = "0.96 0.98 1.00") -> None:
        self.rect(x, y, w, h, fill)
        self.text(x + 9, y + h - 17, title, 10, "F2")
        cursor = y + h - 32
        for line in lines or []:
            self.text(x + 9, cursor, line, 7)
            cursor -= 10

    def lane(self, x: float, title: str) -> None:
        self.box(x, 500, 105, 34, title, [], "0.94 0.96 0.99")
        self.line(x + 52, 500, x + 52, 75, 0.6)

    def title(self, value: str, subtitle: str | None = None) -> None:
        self.text(MARGIN, PAGE_H - 44, value, 18, "F2")
        if subtitle:
            self.text(MARGIN, PAGE_H - 64, subtitle, 9)
        self.line(MARGIN, PAGE_H - 78, PAGE_W - MARGIN, PAGE_H - 78, 0.8)

    def footer(self, page_no: int) -> None:
        self.line(MARGIN, 34, PAGE_W - MARGIN, 34, 0.7)
        self.text(MARGIN, 19, "RecruitmentAssist - LangGraph Agent Architecture Understanding Document", 7)
        self.text(PAGE_W - MARGIN - 42, 19, f"Page {page_no}", 7)

    def stream(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1")


def overview_page() -> PdfPage:
    p = PdfPage()
    p.title("LangGraph Agent Architecture", "Understanding document for the Main HR Orchestrator and role-specific agents")
    y = 504
    p.text(MARGIN, y, "Purpose", 13, "F2")
    y -= 22
    y = p.wrapped_text(
        MARGIN,
        y,
        "This backend uses LangGraph as the orchestration framework. A single Main HR Orchestrator creates an agent run, invokes a compiled StateGraph, and returns a stable API response. The graph uses one LLM Router Agent plus deterministic fallback routing to send requests into specialized role paths.",
        118,
        10,
        14,
    )
    y -= 6
    p.text(MARGIN, y, "Implemented shape", 13, "F2")
    y -= 22
    bullets = [
        "API entrypoint: routes/agentic_routes.py receives JSON or multipart requests.",
        "Main orchestrator: orchestration/main_orchestrator.py creates run_id and records running/completed/failed state.",
        "LangGraph graph: orchestration/hr_graph.py builds StateGraph nodes and conditional edges.",
        "Router: agents/router_agent.py returns one route from screening, chat, jd, candidate, interview, dashboard, reports, unsupported.",
        "Screening path: JD Agent -> Resume Agent -> Matching Agent -> Ranking Agent -> Summary Agent -> Final Response.",
        "Application paths: JD, candidate, interview, dashboard, reports use app_role_agent -> run_app_workflow.",
        "Chat path: recruiter_context -> recruiter_chat_agent -> Final Response.",
    ]
    for item in bullets:
        y = p.wrapped_text(MARGIN + 12, y, f"- {item}", 116, 9, 13)
        y -= 2
    y -= 4
    p.text(MARGIN, y, "Important concept", 13, "F2")
    y -= 22
    p.wrapped_text(
        MARGIN,
        y,
        "LangGraph is used for stateful orchestration and routing. LangChain is present as a dependency, but the implemented graph nodes call local Python agents, workflows, services, database helpers, and the existing OpenAI helper instead of LangChain runnable chains.",
        118,
        10,
        14,
    )
    p.footer(1)
    return p


def architecture_page() -> PdfPage:
    p = PdfPage()
    p.title("Architecture Diagram", "Runtime components and boundaries")
    p.box(45, 455, 118, 54, "Frontend UI", ["Dashboard, Jobs", "Analyze, Talent"])
    p.box(205, 455, 136, 54, "Flask API", ["/api/agentic/run", "/api/compare"])
    p.box(383, 455, 155, 54, "Main HR Orchestrator", ["new run_id", "agent_runs status"])
    p.box(580, 455, 158, 54, "LangGraph StateGraph", ["router node", "conditional edges"])
    p.arrow(163, 482, 205, 482)
    p.arrow(341, 482, 383, 482)
    p.arrow(538, 482, 580, 482)

    p.box(75, 345, 132, 54, "LLM Router Agent", ["strict JSON route", "fallback enabled"], "0.98 0.98 0.92")
    p.box(252, 345, 132, 54, "Screening Path", ["JD, Resume", "Match, Rank, Summary"], "0.95 0.99 0.95")
    p.box(429, 345, 132, 54, "Chat Path", ["Context validate", "Recruiter chat"], "0.95 0.98 1.00")
    p.box(606, 345, 132, 54, "App Role Path", ["JD, candidate", "interview, dashboard"], "0.98 0.96 1.00")
    p.arrow(659, 455, 141, 399)
    p.arrow(141, 345, 318, 399)
    p.arrow(141, 345, 495, 399)
    p.arrow(141, 345, 672, 399)

    p.box(86, 225, 170, 62, "Role Agents", ["jd_agent.py", "resume_agent.py", "matching/ranking/summary"])
    p.box(318, 225, 170, 62, "Workflows", ["app_workflow.py", "recruiter_chat_workflow.py"])
    p.box(550, 225, 170, 62, "Services and DB", ["services/*.py", "database.py, MongoDB"])
    p.arrow(318, 345, 171, 287)
    p.arrow(495, 345, 403, 287)
    p.arrow(672, 345, 403, 287)
    p.arrow(256, 256, 318, 256)
    p.arrow(488, 256, 550, 256)

    p.box(245, 120, 155, 54, "OpenAI Helper", ["llm_extraction.py", "router LLM call"])
    p.box(465, 120, 155, 54, "Trace Metadata", ["trace_start/end", "agent_runs output"])
    p.arrow(171, 225, 245, 174)
    p.arrow(403, 225, 465, 174)
    p.arrow(635, 225, 543, 174)
    p.footer(2)
    return p


def use_case_page() -> PdfPage:
    p = PdfPage()
    p.title("Use Case Diagram", "Actors and LangGraph-backed capabilities")
    p.box(55, 400, 115, 48, "Recruiter", ["Primary user"])
    p.box(55, 285, 115, 48, "Admin/User", ["Profile, reports"])
    p.box(642, 400, 115, 48, "OpenAI API", ["Router/extraction"])
    p.box(642, 285, 115, 48, "MongoDB", ["HR data, runs"])

    use_cases = [
        (260, 466, "Run resume screening"),
        (260, 415, "Ask recruiter chat question"),
        (260, 364, "Manage job descriptions"),
        (260, 313, "View/manage candidates"),
        (260, 262, "Schedule interview"),
        (260, 211, "View dashboard and reports"),
        (260, 160, "Audit agent run state"),
    ]
    for x, y, label in use_cases:
        p.rect(x, y, 260, 35, "0.98 0.98 0.95")
        p.text(x + 16, y + 13, label, 10, "F2")

    for _, y, _ in use_cases[:6]:
        p.arrow(170, 424, 260, y + 17)
    p.arrow(170, 309, 260, 177)
    p.arrow(520, 467, 642, 424)
    p.arrow(520, 364, 642, 309)
    p.arrow(520, 177, 642, 309)
    p.text(76, 103, "Use case boundary: users still call the same Flask APIs; LangGraph is an internal orchestration layer.", 10, "F2")
    p.text(76, 85, "The Router Agent is the only component that decides the global route.", 10)
    p.footer(3)
    return p


def flow_page() -> PdfPage:
    p = PdfPage()
    p.title("Flow Diagram", "End-to-end graph execution flow")
    x = 320
    steps = [
        (505, "API request", "JSON or multipart form data"),
        (455, "Main HR Orchestrator", "create run_id and running status"),
        (405, "router_node", "LLM Router Agent + deterministic fallback"),
        (355, "conditional edge", "screening, chat, app role, unsupported"),
        (285, "specialized path", "execute role-specific graph nodes"),
        (215, "final_response", "normalize output shape"),
        (165, "agent_run update", "completed or failed"),
        (115, "API response", "frontend receives stable response"),
    ]
    previous = None
    for y, title, note in steps:
        p.box(x, y, 230, 38, title, [note])
        if previous is not None:
            p.arrow(x + 115, previous, x + 115, y + 38)
        previous = y

    p.box(60, 270, 180, 76, "Screening Branch", ["JD Agent", "Resume Agent", "Matching Agent", "Ranking Agent", "Summary Agent"])
    p.box(600, 270, 180, 76, "Other Branches", ["Chat path", "JD path", "Candidate path", "Interview path", "Dashboard/reports"])
    p.arrow(320, 374, 240, 325)
    p.arrow(550, 374, 600, 325)
    p.arrow(240, 270, 320, 234)
    p.arrow(600, 270, 550, 234)

    p.box(60, 145, 180, 56, "Unsupported/Error", ["raise ValueError", "mark run failed"])
    p.arrow(320, 374, 240, 173)
    p.footer(4)
    return p


def sequence_page() -> PdfPage:
    p = PdfPage()
    p.title("UML Sequence Diagram", "Request lifecycle through the graph")
    lanes = [
        (48, "Frontend"),
        (170, "API Route"),
        (292, "Orchestrator"),
        (414, "LangGraph"),
        (536, "Agents"),
        (658, "DB/Services"),
    ]
    for x, title in lanes:
        p.lane(x, title)

    messages = [
        (470, 48, 170, "POST /api/agentic/run"),
        (430, 170, 292, "run_main_orchestrator"),
        (390, 292, 658, "create_agent_run running"),
        (350, 292, 414, "invoke StateGraph"),
        (310, 414, 536, "router_node route_request"),
        (270, 414, 536, "execute selected path nodes"),
        (230, 536, 658, "load/persist data"),
        (190, 414, 292, "final_response"),
        (150, 292, 658, "update_agent_run completed"),
        (110, 292, 170, "return result"),
        (80, 170, 48, "JSON response"),
    ]
    for y, x1, x2, label in messages:
        p.arrow(x1 + 52, y, x2 + 52, y)
        p.text(min(x1, x2) + 58, y + 8, label, 7)
    p.footer(5)
    return p


def class_state_page() -> PdfPage:
    p = PdfPage()
    p.title("UML State and Class View", "Shared state object and graph node responsibilities")

    p.text(64, 500, "StateGraph state model", 13, "F2")
    p.box(64, 330, 275, 142, "HRGraphState", [
        "payload: request payload",
        "username, run_id, task_type",
        "route, route_decision",
        "jd_id, jd_context, resume_context",
        "match_context, ranked_context",
        "summary, errors",
        "path_result, final_response",
    ], "0.96 0.98 1.00")

    p.text(430, 500, "State transitions", 13, "F2")
    p.box(430, 448, 150, 36, "START")
    p.box(430, 395, 150, 36, "router")
    p.box(250, 315, 150, 45, "screening nodes", ["JD -> Resume -> Match"])
    p.box(430, 315, 150, 45, "chat nodes", ["context -> chat"])
    p.box(610, 315, 150, 45, "app_role_agent", ["workflow dispatch"])
    p.box(430, 230, 150, 36, "final_response")
    p.box(430, 175, 150, 36, "END")
    p.arrow(505, 448, 505, 431)
    p.arrow(430, 395, 325, 360)
    p.arrow(505, 395, 505, 360)
    p.arrow(580, 395, 685, 360)
    p.arrow(325, 315, 505, 266)
    p.arrow(505, 315, 505, 266)
    p.arrow(685, 315, 505, 266)
    p.arrow(505, 230, 505, 211)

    p.text(64, 270, "Node rule", 12, "F2")
    y = 248
    for item in [
        "Each graph node receives HRGraphState and returns a partial state update.",
        "Only router_node chooses the global route.",
        "final_response_node creates the API-facing response shape.",
        "Fatal exceptions are caught by the main orchestrator and mark the run failed.",
    ]:
        y = p.wrapped_text(76, y, f"- {item}", 58, 9, 13)
    p.footer(6)
    return p


def write_pdf(path: Path, pages: list[PdfPage]) -> None:
    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    font1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    page_refs: list[int] = []
    content_refs: list[int] = []

    for page in pages:
        stream = page.stream()
        content_refs.append(add(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"))
        page_refs.append(0)

    pages_ref = len(objects) + len(pages) + 1
    for i, content_ref in enumerate(content_refs):
        page_obj = (
            f"<< /Type /Page /Parent {pages_ref} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /Font << /F1 {font1} 0 R /F2 {font2} 0 R >> >> "
            f"/Contents {content_ref} 0 R >>"
        ).encode("ascii")
        page_refs[i] = add(page_obj)

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
    output = root / "docs" / "langgraph_agent_architecture_understanding.pdf"
    pages = [
        overview_page(),
        architecture_page(),
        use_case_page(),
        flow_page(),
        sequence_page(),
        class_state_page(),
    ]
    write_pdf(output, pages)
    print(output)


if __name__ == "__main__":
    main()
