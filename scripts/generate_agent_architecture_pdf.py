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

    def text(self, x: float, y: float, value: str, size: int = 11, font: str = "F1") -> None:
        self.ops.append(f"BT /{font} {size} Tf {x:.1f} {y:.1f} Td ({esc(value)}) Tj ET")

    def wrapped_text(self, x: float, y: float, value: str, width_chars: int = 95, size: int = 10, leading: int = 14) -> float:
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

    def line(self, x1: float, y1: float, x2: float, y2: float, width: float = 1.2) -> None:
        self.ops.append(f"q {width:.1f} w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S Q")

    def arrow(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.line(x1, y1, x2, y2)
        if abs(x2 - x1) >= abs(y2 - y1):
            direction = 1 if x2 >= x1 else -1
            self.line(x2, y2, x2 - 8 * direction, y2 + 5, 1.0)
            self.line(x2, y2, x2 - 8 * direction, y2 - 5, 1.0)
        else:
            direction = 1 if y2 >= y1 else -1
            self.line(x2, y2, x2 - 5, y2 - 8 * direction, 1.0)
            self.line(x2, y2, x2 + 5, y2 - 8 * direction, 1.0)

    def rect(self, x: float, y: float, w: float, h: float, fill: str = "0.96 0.98 1.00") -> None:
        self.ops.append(f"q {fill} rg 0.20 0.28 0.35 RG 1.2 w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re B Q")

    def box(self, x: float, y: float, w: float, h: float, title: str, lines: list[str] | None = None) -> None:
        self.rect(x, y, w, h)
        self.text(x + 10, y + h - 19, title, 11, "F2")
        cursor = y + h - 36
        for line in lines or []:
            self.text(x + 10, cursor, line, 8)
            cursor -= 11

    def title(self, value: str, subtitle: str | None = None) -> None:
        self.text(MARGIN, PAGE_H - 46, value, 20, "F2")
        if subtitle:
            self.text(MARGIN, PAGE_H - 67, subtitle, 10)
        self.line(MARGIN, PAGE_H - 82, PAGE_W - MARGIN, PAGE_H - 82, 1.0)

    def footer(self, page_no: int) -> None:
        self.line(MARGIN, 34, PAGE_W - MARGIN, 34, 0.8)
        self.text(MARGIN, 19, "RecruitmentAssist - Agentic Screening Feature", 8)
        self.text(PAGE_W - MARGIN - 42, 19, f"Page {page_no}", 8)

    def stream(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1")


def overview_page() -> PdfPage:
    p = PdfPage()
    p.title("Agentic Screening Feature", "Custom Python orchestration for HR resume screening")
    y = 500
    p.text(MARGIN, y, "What this feature does", 14, "F2")
    y -= 24
    bullets = [
        "Recruiter submits a JD and resumes or existing candidate IDs through Flask APIs.",
        "Main HR Orchestrator creates a run record and routes the task to the correct workflow.",
        "Screening Workflow runs specialized agents in sequence: JD, Resume, Matching, Ranking, Summary.",
        "OpenAI is used through the local llm_extraction helper where extraction or scoring needs LLM support.",
        "LangChain and LangGraph are listed as dependencies, but this code path is a custom Python pipeline.",
    ]
    for item in bullets:
        y = p.wrapped_text(MARGIN + 12, y, f"- {item}", 104, 10)
        y -= 4
    y -= 8
    p.text(MARGIN, y, "Key modules", 14, "F2")
    y -= 23
    modules = [
        "routes/agentic_routes.py: API layer for /api/agentic/run and /api/agentic/screening.",
        "orchestration/main_orchestrator.py: creates run IDs, stores status, and dispatches task types.",
        "workflows/screening_workflow.py: sequential screening pipeline.",
        "agents/*.py: role-specific Python agents.",
        "tools/*.py and services/*.py: reusable database, extraction, matching, and persistence logic.",
    ]
    for item in modules:
        y = p.wrapped_text(MARGIN + 12, y, f"- {item}", 104, 10)
        y -= 4
    p.footer(1)
    return p


def architecture_page() -> PdfPage:
    p = PdfPage()
    p.title("Architecture Diagram", "Runtime structure of the custom agent pipeline")
    p.box(48, 455, 130, 54, "Recruiter UI", ["Uploads JD/resumes", "Starts screening"])
    p.box(226, 455, 150, 54, "Flask API Routes", ["/api/agentic/run", "/api/agentic/screening"])
    p.box(424, 455, 165, 54, "Main HR Orchestrator", ["Detects task type", "Creates agent_run"])
    p.box(638, 455, 130, 54, "MongoDB", ["agent_runs", "candidates, JDs"])
    p.arrow(178, 482, 226, 482)
    p.arrow(376, 482, 424, 482)
    p.arrow(589, 482, 638, 482)

    p.box(70, 330, 120, 62, "JD Agent", ["Loads JD row", "Normalizes JD JSON"])
    p.box(220, 330, 130, 62, "Resume Agent", ["Existing candidates", "Uploaded resumes", "Extracts JSON"])
    p.box(380, 330, 130, 62, "Matching Agent", ["Compares JD/resume", "Persists match"])
    p.box(540, 330, 125, 62, "Ranking Agent", ["Sorts by score", "Splits selected/rejected"])
    p.box(695, 330, 110, 62, "Summary Agent", ["Builds recruiter", "summary"])

    p.arrow(506, 455, 130, 392)
    p.arrow(190, 361, 220, 361)
    p.arrow(350, 361, 380, 361)
    p.arrow(510, 361, 540, 361)
    p.arrow(665, 361, 695, 361)

    p.box(145, 205, 170, 60, "Tools Layer", ["jd_tools.py", "resume_tools.py", "matching_tools.py"])
    p.box(385, 205, 170, 60, "Service Layer", ["candidate_service.py", "matching_service.py", "jd_service.py"])
    p.box(625, 205, 145, 60, "OpenAI Helper", ["llm_extraction.py", "gpt-4o-mini default"])

    p.arrow(285, 330, 235, 265)
    p.arrow(445, 330, 470, 265)
    p.arrow(285, 205, 385, 235)
    p.arrow(555, 235, 625, 235)

    p.text(70, 150, "Note: This architecture is agentic by design, but it is not implemented with LangGraph nodes or LangChain runnables.", 10, "F2")
    p.text(70, 132, "The agents are normal Python functions with tracing and shared helper tools.", 10)
    p.footer(2)
    return p


def use_case_page() -> PdfPage:
    p = PdfPage()
    p.title("Use Case Diagram", "Main actors and system responsibilities")
    p.box(56, 392, 112, 55, "Recruiter", ["Primary user"])
    p.box(56, 285, 112, 55, "Admin/User", ["Views data", "Manages app"])
    p.box(650, 392, 112, 55, "OpenAI API", ["LLM extraction", "LLM scoring"])
    p.box(650, 285, 112, 55, "MongoDB", ["Stores runs", "Stores HR data"])

    use_cases = [
        (270, 455, "Start Agentic Screening"),
        (270, 398, "Upload Resumes"),
        (270, 341, "Screen Candidate Against JD"),
        (270, 284, "Rank Candidates"),
        (270, 227, "View Screening Summary"),
        (270, 170, "Audit Agent Run"),
    ]
    for x, y, title in use_cases:
        p.rect(x, y, 245, 38, "0.98 0.98 0.95")
        p.text(x + 16, y + 14, title, 11, "F2")

    for _, y, _ in use_cases[:5]:
        p.arrow(168, 420, 270, y + 19)
    p.arrow(168, 312, 270, 189)
    p.arrow(515, 360, 650, 420)
    p.arrow(515, 303, 650, 312)
    p.arrow(515, 189, 650, 312)

    p.text(72, 110, "Recruiter goal: quickly identify selected, rejected, and top-ranked candidates for a JD.", 10)
    p.text(72, 92, "System goal: keep every run traceable with run_id, task_type, input, output, status, and errors.", 10)
    p.footer(3)
    return p


def flow_chart_page() -> PdfPage:
    p = PdfPage()
    p.title("Flow Chart Diagram", "Detailed screening flow from request to result")
    x = 322
    boxes = [
        (500, "Request received", "Flask route collects form/json and files"),
        (440, "Create run_id", "Main orchestrator stores running status"),
        (380, "JD Agent", "Load JD and normalized JD JSON"),
        (320, "Resume Agent", "Load existing candidates and extract uploaded resumes"),
        (260, "Matching Agent", "Compare each profile against the JD and persist comparison"),
        (200, "Ranking Agent", "Sort by match_score descending"),
        (140, "Summary Agent", "Create recruiter-facing summary and attach errors"),
        (80, "Return response", "Update agent_run as completed or failed"),
    ]
    prev_y = None
    for y, title, note in boxes:
        p.box(x, y, 220, 42, title, [note])
        if prev_y is not None:
            p.arrow(x + 110, prev_y, x + 110, y + 42)
        prev_y = y

    p.box(80, 246, 160, 78, "Error Handling", ["Resume errors collected", "Matching errors collected", "Fatal errors mark run failed"])
    p.arrow(322, 281, 240, 281)
    p.arrow(240, 281, 322, 160)

    p.box(610, 246, 150, 78, "Database Writes", ["candidate records", "comparison rows", "agent_runs output"])
    p.arrow(542, 281, 610, 281)
    p.arrow(610, 281, 542, 101)

    p.text(72, 48, "Ranking detail: the current Ranking Agent uses deterministic sorting by match_score, not an LLM call.", 10, "F2")
    p.footer(4)
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
    output = root / "docs" / "agentic_screening_feature_architecture.pdf"
    pages = [overview_page(), architecture_page(), use_case_page(), flow_chart_page()]
    write_pdf(output, pages)
    print(output)


if __name__ == "__main__":
    main()
