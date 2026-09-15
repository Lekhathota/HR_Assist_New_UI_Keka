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

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.ops.append(f"q 0.8 w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S Q")

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

    def title(self, title: str, subtitle: str) -> float:
        self.text(MARGIN, PAGE_H - 45, title, 19, "F2")
        self.text(MARGIN, PAGE_H - 65, subtitle, 9)
        self.line(MARGIN, PAGE_H - 80, PAGE_W - MARGIN, PAGE_H - 80)
        return PAGE_H - 110

    def section(self, y: float, title: str) -> float:
        self.text(MARGIN, y, title, 13, "F2")
        return y - 20

    def bullet(self, y: float, text: str) -> float:
        return self.wrap(MARGIN + 12, y, f"- {text}") - 3

    def footer(self, page_no: int) -> None:
        self.line(MARGIN, 34, PAGE_W - MARGIN, 34)
        self.text(MARGIN, 19, "RecruitmentAssist Fix Report", 8)
        self.text(PAGE_W - MARGIN - 42, 19, f"Page {page_no}", 8)

    def stream(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1")


def page_one() -> Page:
    page = Page()
    y = page.title("RecruitmentAssist Project Fix Report", f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    y = page.section(y, "Summary")
    for item in [
        "Completed a backend/frontend health sweep after the LangGraph migration.",
        "Fixed verified data-count, response-shape, profile update, and Jobs refresh issues.",
        "Validated backend compilation, frontend production build, and key LangGraph route response shapes.",
    ]:
        y = page.bullet(y, item)

    y -= 8
    y = page.section(y, "Issues Fixed")
    fixes = [
        "Jobs page counts for candidates screened against multiple JDs: JD counts now use comparison rows instead of the candidate table's single jd_id field.",
        "ServiceNow Developer card: verified it now reports total_resumes=2, selected_count=0, rejected_count=2 from comparison data.",
        "Candidate queries for a specific JD: candidates_payload({jd_id}) now uses get_candidates_for_jd(), so JD details and interview eligibility see comparison-backed candidates.",
        "Dashboard team data crash: preserved empty list responses and guarded the frontend before calling filter().",
        "Jobs stale values: cleared the JD session cache after create, delete, and screening actions; Jobs page also refreshes on focus/pageshow.",
        "List response robustness: guarded JD, candidate, comparison, and dashboard list consumers against malformed non-array responses.",
        "Profile password form: added current-password verification and password update support instead of silently ignoring password fields.",
        "Profile error display: frontend now respects failed profile update responses instead of always showing a success-style message.",
    ]
    for item in fixes:
        y = page.bullet(y, item)
    page.footer(1)
    return page


def page_two() -> Page:
    page = Page()
    y = page.title("Verification Results", "Commands and smoke checks run after fixes")
    y = page.section(y, "Passed Checks")
    checks = [
        "Backend compile: python -m compileall -q RecruitmentAssist/backend passed.",
        "Frontend production build: npm --prefix RecruitmentAssist/frontend run build passed.",
        "LangGraph route shapes: dashboard=dict, dashboard_team=list, jd_list=list, candidate_list=list, reports=dict, jd_performance=list.",
        "Candidate profile via graph: candidate 52 returned name=NISHIT MITTAL, jd_history=4, screening_summaries=4.",
        "ServiceNow JD list via graph: JD id 10 returned total_resumes=2, selected_count=0, rejected_count=2.",
        "Router safety: explicit known task_type values bypass LLM routing and use deterministic route mapping.",
    ]
    for item in checks:
        y = page.bullet(y, item)

    y -= 8
    y = page.section(y, "Files Touched")
    files = [
        "backend/services/jd_service.py",
        "backend/services/candidate_service.py",
        "backend/database.py",
        "backend/routes/profile_routes.py",
        "backend/workflows/app_workflow.py",
        "frontend/src/api.js",
        "frontend/src/pages/JdList.jsx",
        "frontend/src/pages/Dashboard.jsx",
        "frontend/src/pages/Comparison.jsx",
        "frontend/src/pages/Candidates.jsx",
        "frontend/src/pages/Profile.jsx",
    ]
    for item in files:
        y = page.bullet(y, item)
    page.footer(2)
    return page


def page_three() -> Page:
    page = Page()
    y = page.title("Remaining Notes", "Items to watch during manual testing")
    y = page.section(y, "Recommended Manual Tests")
    tests = [
        "Restart backend and frontend, then hard-refresh the browser.",
        "Open Jobs and confirm ServiceNow Developer shows Total Resumes 2, Selected 0, Rejected 2.",
        "Run a new screening against any JD and confirm the Jobs card updates after returning to /jobs.",
        "Open a candidate profile and confirm Applied Roles and Screening Summaries render.",
        "Try profile email-only update and password update with both wrong and correct current password.",
        "Create and delete a JD, then confirm the Jobs list cache updates correctly.",
    ]
    for item in tests:
        y = page.bullet(y, item)

    y -= 8
    y = page.section(y, "Known Constraints")
    constraints = [
        "This was a practical health sweep, not a formal exhaustive QA certification of every workflow.",
        "No destructive database migrations were run.",
        "Frontend build output changed because the production build was regenerated.",
        "LLM routing remains safely bypassed for explicit task_type values; ambiguous natural-language routing still depends on OPENAI_API_KEY.",
    ]
    for item in constraints:
        y = page.bullet(y, item)
    page.footer(3)
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
    output = root / "docs" / "project_fix_report.pdf"
    write_pdf(output, [page_one(), page_two(), page_three()])
    print(output)


if __name__ == "__main__":
    main()
