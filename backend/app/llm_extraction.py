# Backend file purpose: Core parsing, extraction, matching, or utility logic for llm extraction.
"""
LLM-based extraction and processing utilities
"""

import json
import re
import os
from datetime import datetime
from typing import Any
import openai
from dotenv import load_dotenv
from app.regex_extractor import extract_jd_regex, extract_resume_regex


load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
SELECTION_MATCH_THRESHOLD = 75


# Purpose: Implements the configure openai api key backend behavior.
def _configure_openai_api_key() -> str:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if api_key in {"", "your_api_key_here", "sk-dummy-key-for-testing"}:
        return ""
    openai.api_key = api_key
    return api_key


api_key = _configure_openai_api_key()

_SKILL_STOPWORDS = {
    "strong",
    "eager",
    "innovative",
    "solid",
    "project",
    "work",
    "development",
    "contribute",
    "foundation",
    "management",
    "analysis",
    "ethic",
    "data",
    "technology",
    "software",
    "skills",
    "skill",
    "team player",
    "hardworking",
    "leadership",
    "responsible",
    "excellent",
    "good",
    "ability",
    "knowledge",
    "understanding",
    "hands-on",
    "hands on",
}

_NAME_REJECT_WORDS = {
    "experience",
    "postgraduate",
    "graduate",
    "developer",
    "engineer",
    "science",
    "python",
    "java",
    "react",
    "machine",
    "learning",
    "generative",
    "nlp",
    "resume",
    "curriculum",
    "vitae",
    "profile",
    "summary",
    "executive",
    "leadership",
    "strategy",
    "director",
    "skills",
    "project",
    "internship",
}

_SECTION_HEADINGS = {
    "work history",
    "work experience",
    "professional experience",
    "experience",
    "employment history",
    "education",
    "academic history",
    "skills",
    "technical skills",
    "projects",
    "certifications",
    "certificates",
    "summary",
    "profile",
}

_NON_WORK_SECTION_HINTS = {
    "education",
    "academic",
    "academics",
    "qualification",
    "qualifications",
    "coursework",
    "training",
    "project",
    "projects",
    "skills",
    "skill set",
    "tech stack",
    "certification",
    "certificate",
    "certifications",
    "achievements",
    "awards",
    "research",
    "publications",
    "summary",
    "profile",
    "objective",
    "career objective",
    "contact",
    "personal details",
    "portfolio",
    "links",
    "gpa",
    "cgpa",
}

_WORK_SECTION_HINTS = {
    "work history",
    "work experience",
    "professional experience",
    "employment history",
    "employment",
    "career history",
    "career summary",
    "experience summary",
    "professional background",
    "relevant experience",
    "industry experience",
    "internship experience",
    "internship",
    "internships",
    "apprenticeship",
    "apprenticeships",
    "job history",
    "positions held",
    "roles and responsibilities",
}

_ROLE_HINTS = {
    "developer",
    "engineer",
    "analyst",
    "administrator",
    "architect",
    "consultant",
    "designer",
    "intern",
    "trainee",
    "lead",
    "manager",
    "specialist",
    "tester",
    "qa",
    "sde",
    "associate",
    "executive",
    "officer",
    "coordinator",
    "scientist",
    "programmer",
    "owner",
    "founder",
    "principal",
    "head",
    "director",
    "supervisor",
    "representative",
    "support",
    "operator",
    "technician",
    "admin",
    "devops",
    "frontend",
    "backend",
    "software",
    "web",
    "mobile",
    "data",
    "ai",
    "ml",
    "cloud",
    "platform",
    "product",
    "business analyst",
    "data analyst",
    "data engineer",
    "software engineer",
    "frontend developer",
    "backend developer",
    "full stack developer",
    "project manager",
    "scrum master",
}

_EDUCATION_HINTS = {
    "university",
    "college",
    "institute",
    "school",
    "campus",
    "academy",
    "polytechnic",
    "faculty",
    "department",
    "bachelor",
    "master",
    "doctorate",
    "phd",
    "b.tech",
    "m.tech",
    "btech",
    "mtech",
    "be",
    "b.e",
    "me",
    "m.e",
    "b.sc",
    "m.sc",
    "bca",
    "mca",
    "degree",
    "gpa",
    "higher secondary",
    "secondary",
    "intermediate",
    "ssc",
    "engineering",
    "bachelor's",
    "undergraduate",
    "postgraduate",
    "graduation",
    "major",
    "minor",
    "branch",
    "specialization",
    "course",
    "diploma",
    "b.com",
    "m.com",
    "bba",
    "mba",
    "cgpa",
}

_SKILL_REJECT_PATTERNS = (
    r"^(and|or|with|in|of|for|to|on|using)\s+",
    r"\s+(and|or|with|in|in order to)\s+",
    r"\b(projects?|experience|internships?|responsibilities|summary|profile|driven)\b",
    r"\b(skilled|hands[- ]?on|worked|developed|built|created)\b",
)

_KNOWN_SKILL_HINTS = {
    "python", "java", "javascript", "typescript", "react", "node.js", "sql", "mysql", "postgresql", "mongodb",
    "selenium", "manual testing", "automation testing", "pytest", "junit", "cypress", "postman", "aws",
    "azure", "docker", "kubernetes", "git", "html", "css", "fastapi", "flask", "django", "rest", "graphql",
    "nlp", "machine learning", "deep learning", "generative ai", "llm", "pandas", "numpy", "scikit-learn",
    "tensorflow", "pytorch", "spark", "tableau", "power bi", "excel", "linux", "jenkins", "terraform",
    "ansible", "redis", "elasticsearch", "api", "ci/cd", "gcp", "azure devops", "jira", "figma",
}

_SKILL_SYNONYMS = {
    "js": "javascript",
    "node": "node.js",
    "nodejs": "node.js",
    "node.js": "node.js",
    "reactjs": "react",
    "react.js": "react",
    "ts": "typescript",
    "py": "python",
    "postgres": "postgresql",
    "postgre sql": "postgresql",
    "mongo": "mongodb",
    "ms sql": "sql",
    "mssql": "sql",
    "rest api": "rest",
    "restful api": "rest",
    "ci cd": "ci/cd",
    "cicd": "ci/cd",
}

_EDUCATION_FIELD_HINTS = {
    "computer science",
    "information technology",
    "software engineering",
    "electronics",
    "communication",
    "electrical",
    "mechanical",
    "civil",
    "data science",
    "artificial intelligence",
    "machine learning",
    "business administration",
    "commerce",
    "mathematics",
    "statistics",
    "physics",
    "chemistry",
}


# Purpose: Normalizes skill token into the app's expected format.
def _normalize_skill_token(skill: str) -> str:
    s = re.sub(r"[^a-z0-9\+\#\.\-/ ]+", "", str(skill or "").lower()).strip()
    s = s.strip(" .,-;/")
    s = re.sub(r"\s+", " ", s)
    return _SKILL_SYNONYMS.get(s, s)


# Purpose: Checks whether probable skill is true.
def _is_probable_skill(token: str) -> bool:
    if token in _KNOWN_SKILL_HINTS:
        return True
    if any(re.search(pattern, token) for pattern in _SKILL_REJECT_PATTERNS):
        return False
    words = token.split()
    if len(words) > 3:
        return False
    if len(words) == 1:
        return bool(re.search(r"[a-z]", token)) and len(token) <= 25
    return all(len(word) > 1 for word in words)


# Purpose: Cleans and normalizes skills values.
def _clean_skills(skills: list) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in skills or []:
        raw_items = re.split(r"[,|;]+", raw) if isinstance(raw, str) else [raw]
        for item in raw_items:
            token = _normalize_skill_token(item)
            if not token or len(token) < 2:
                continue
            if token in _SKILL_STOPWORDS:
                continue
            if token.isdigit():
                continue
            if not _is_probable_skill(token):
                continue
            if token in seen:
                continue
            seen.add(token)
            cleaned.append(token)
    return cleaned


# Purpose: Implements the looks like person name backend behavior.
def _looks_like_person_name(value: str) -> bool:
    text = str(value or "").strip()
    if not text or len(text) > 60:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'\-]*", text)
    if not 2 <= len(words) <= 5:
        return False
    lowered = {word.lower() for word in words}
    if lowered.intersection(_NAME_REJECT_WORDS):
        return False
    if re.search(r"[@:/\\0-9]", text):
        return False
    return len(" ".join(words)) >= 5


# Purpose: Cleans and normalizes person name values.
def _clean_person_name(value: str) -> str:
    text = " ".join(re.findall(r"[A-Za-z][A-Za-z'\-]*", str(value or "")))
    if not _looks_like_person_name(text):
        return ""
    return " ".join(part[:1].upper() + part[1:] for part in text.split())


# Purpose: Implements the strip contact noise backend behavior.
def _strip_contact_noise(value: str) -> str:
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", " ", str(value or ""))
    text = re.sub(r"https?://\S+|(?:www\.)?(?:linkedin|github)\.com/\S+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)", " ", text)
    return re.sub(r"\s+", " ", text).strip(" .,-:;|")


# Purpose: Cleans and normalizes education field values.
def _clean_education_field(value: str) -> str:
    field = re.sub(r"\s+", " ", str(value or "")).strip(" .,-:;|")
    if not field or field.lower() in {"not specified", "n/a", "na", "none", "null", "unknown"}:
        return ""
    field = re.sub(r"\b(?:from|at|with|during)\b.*$", "", field, flags=re.IGNORECASE).strip(" ,-")
    lowered = field.lower()
    if len(field) > 60 or len(field.split()) > 6:
        return ""
    if any(bad in lowered for bad in ("agile", "outcome", "environment", "project", "experience", "intern", "responsibil")):
        return ""
    if any(hint in lowered for hint in _EDUCATION_FIELD_HINTS):
        return field
    if re.fullmatch(r"(cse|cs|it|ece|eee|me|ce|ai|ml|bca|mca|mba)", lowered):
        return field.upper()
    return ""


# Purpose: Cleans and normalizes institution name values.
def _clean_institution_name(value: str) -> str:
    institution = re.sub(r"\s+", " ", str(value or "")).strip(" .,-:;|")
    if not institution or institution.lower() in {"not specified", "n/a", "na", "none", "null", "unknown"}:
        return ""
    institution = re.sub(r"\s+(?:-|,|\|).*$", "", institution).strip()
    lowered = institution.lower()
    if len(institution) > 90 or len(institution.split()) > 10:
        return ""
    if any(bad in lowered for bad in ("agile", "outcome", "environment", "project", "experience", "intern", "responsibil")):
        return ""
    return institution


# Purpose: Extracts institution from text from input data.
def _extract_institution_from_text(text: str) -> str:
    section_match = re.search(
        r"(?:education|academic(?:s| background)?|qualification(?:s)?)\s*:?\s*(.*?)(?=\n\s*(?:skills|projects?|work|professional|experience|certifications?)\b|$)",
        text or "",
        re.IGNORECASE | re.DOTALL,
    )
    search_text = section_match.group(1) if section_match else text or ""
    pattern = (
        r"([A-Z][A-Za-z&.\- ]{2,}?"
        r"(?:University|College|Institute(?:\s+of\s+[A-Z][A-Za-z&.\- ]+)?|School)"
        r"(?:\s+of\s+[A-Z][A-Za-z&.\- ]+)?)"
    )
    for match in re.findall(pattern, search_text):
        institution = _clean_institution_name(match)
        if institution:
            return institution
    return ""


# Purpose: Implements the line token backend behavior.
def _line_token(value: str) -> str:
    text = re.sub(r"[^a-z0-9 .+/&-]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", text).strip(" .-/")


# Purpose: Checks whether section heading is true.
def _is_section_heading(value: str) -> bool:
    token = _line_token(value)
    if not token:
        return False
    return token in _SECTION_HEADINGS or token.rstrip(":") in _SECTION_HEADINGS


# Purpose: Checks whether work section heading is true.
def _is_work_section_heading(value: str) -> bool:
    token = _line_token(value).rstrip(":")
    return token in _WORK_SECTION_HINTS


# Purpose: Checks whether non work section heading is true.
def _is_non_work_section_heading(value: str) -> bool:
    token = _line_token(value)
    if not token:
        return False
    return any(hint in token for hint in _NON_WORK_SECTION_HINTS) and not _is_work_section_heading(value)


# Purpose: Implements the looks like education line backend behavior.
def _looks_like_education_line(value: str) -> bool:
    token = _line_token(value)
    if not token or _looks_like_role_line(value):
        return False
    return any(re.search(rf"(?<![a-z0-9]){re.escape(hint)}(?![a-z0-9])", token) for hint in _EDUCATION_HINTS)


# Purpose: Implements the looks like role line backend behavior.
def _looks_like_role_line(value: str) -> bool:
    token = _line_token(value)
    return bool(token and any(re.search(rf"\b{re.escape(hint)}\b", token) for hint in _ROLE_HINTS))


# Purpose: Implements the looks like bad work text backend behavior.
def _looks_like_bad_work_text(value: str) -> bool:
    token = _line_token(value)
    if not token:
        return True
    if "http" in token or "github.com" in token or "linkedin.com" in token:
        return True
    if _is_section_heading(token) or _looks_like_education_line(token):
        return True
    if any(hint in token for hint in {"kaggle", "visualization", "dashboard", "portfolio"}):
        return True
    if re.search(r"\b(gpa|cgpa|percentage|grade|intermediate|secondary)\b", token):
        return True
    if re.search(r"\b(driven|built|created|developed|implemented|designed)\b", token) and not _looks_like_role_line(token):
        return True
    return False


# Purpose: Normalizes experience years into the app's expected format.
def _normalize_experience_years(value: Any) -> float:
    try:
        years = float(value or 0)
    except Exception:
        return 0.0
    if years < 1:
        return 0.0
    return round(years, 1)


# Purpose: Implements the date year backend behavior.
def _date_year(value: str) -> int:
    if str(value or "").lower() == "present":
        return 9999
    match = re.search(r"\b(19\d{2}|20\d{2})\b", str(value or ""))
    return int(match.group(1)) if match else 0


# Purpose: Cleans and normalizes work rows values.
def _clean_work_rows(work_rows: list[dict]) -> list[dict]:
    cleaned = []
    seen = set()
    for row in work_rows or []:
        if not isinstance(row, dict):
            continue
        position = str(row.get("position") or row.get("job_title") or row.get("designation") or "").strip()
        company = str(row.get("company") or "").strip()
        start = _normalize_date_to_iso(row.get("start_date") or "")
        end = _normalize_date_to_iso(row.get("end_date") or "")
        pos_token = _normalize_skill_token(position)
        comp_token = _normalize_skill_token(company)
        if not position and not company:
            continue
        if pos_token in _SKILL_STOPWORDS or comp_token in _SKILL_STOPWORDS:
            continue
        if _looks_like_bad_work_text(position):
            continue
        if company and _looks_like_bad_work_text(company):
            continue
        if any(word in comp_token.split() for word in {"in", "and", "or", "with"}):
            continue
        sy = _date_year(start)
        ey = _date_year(end)
        if sy and ey and ey != 9999 and sy > ey:
            continue
        key = (position.lower(), company.lower(), start, end)
        if key in seen:
            continue
        seen.add(key)
        responsibilities = row.get("responsibilities")
        cleaned.append(
            {
                "company": company,
                "position": position,
                "start_date": start,
                "end_date": end,
                "responsibilities": responsibilities if isinstance(responsibilities, list) else [],
            }
        )
    return cleaned[:8]


# Purpose: Normalizes date to iso into the app's expected format.
def _normalize_date_to_iso(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.lower() in {"present", "current", "now"}:
        return "Present"

    # Already ISO-like
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    if re.match(r"^\d{4}-\d{2}$", text):
        return f"{text}-01"
    if re.match(r"^\d{4}$", text):
        return f"{text}-01-01"

    month_map = {
        "jan": "01", "january": "01",
        "feb": "02", "february": "02",
        "mar": "03", "march": "03",
        "apr": "04", "april": "04",
        "may": "05",
        "jun": "06", "june": "06",
        "jul": "07", "july": "07",
        "aug": "08", "august": "08",
        "sep": "09", "sept": "09", "september": "09",
        "oct": "10", "october": "10",
        "nov": "11", "november": "11",
        "dec": "12", "december": "12",
    }
    m = re.match(r"^([a-zA-Z]+)\s+(\d{4})$", text)
    if m:
        mm = month_map.get(m.group(1).lower())
        if mm:
            return f"{m.group(2)}-{mm}-01"
    return text


# Purpose: Implements the flatten skill payload backend behavior.
def _flatten_skill_payload(skills_raw: Any) -> list[str]:
    if isinstance(skills_raw, list):
        return _clean_skills(skills_raw)
    if isinstance(skills_raw, dict):
        flat = []
        for key in ("technical", "soft", "languages"):
            vals = skills_raw.get(key)
            if isinstance(vals, list):
                flat.extend(vals)
        # Also include any additional list-like groups
        for _, vals in skills_raw.items():
            if isinstance(vals, list):
                flat.extend(vals)
        return _clean_skills(flat)
    return []


# Purpose: Normalizes resume output into the app's expected format.
def _normalize_resume_output(raw_resume: dict) -> dict:
    # Purpose: Cleans and normalizes text values.
    def _clean_text(v: Any) -> str:
        text = str(v or "").strip()
        if text.lower() in {"not specified", "n/a", "na", "none", "null", "unknown"}:
            return ""
        return text

    # Support both old and new prompt shapes.
    full_name = _clean_person_name(raw_resume.get("full_name") or raw_resume.get("candidate_name") or "")
    email = _clean_text(raw_resume.get("email") or "")
    phone = _clean_text(raw_resume.get("phone_number") or raw_resume.get("phone") or "")
    location = _clean_text(raw_resume.get("location") or raw_resume.get("current_location") or "")
    total_exp = raw_resume.get("total_years_experience", raw_resume.get("total_experience_years", 0))
    try:
        total_exp_num = float(total_exp or 0)
    except Exception:
        total_exp_num = 0.0
    total_exp_num = _normalize_experience_years(total_exp_num)

    skills = _flatten_skill_payload(raw_resume.get("skills"))
    technical = _clean_skills(raw_resume.get("technical_skills") or skills)

    work_src = raw_resume.get("work_experience") if isinstance(raw_resume.get("work_experience"), list) else []
    work_experience = _clean_work_rows(work_src)

    edu_src = raw_resume.get("education")
    edu = {"degree": "", "field": "", "institution": "", "graduation_year": ""}
    if isinstance(edu_src, list) and edu_src:
        first = edu_src[0] if isinstance(edu_src[0], dict) else {}
        end_date = _normalize_date_to_iso(first.get("end_date") or first.get("graduation_year") or "")
        edu = {
            "degree": _clean_text(first.get("degree") or ""),
            "field": _clean_education_field(first.get("field") or first.get("major") or ""),
            "institution": _clean_institution_name(first.get("institution") or ""),
            "graduation_year": end_date[:4] if end_date and end_date != "Present" else "",
        }
    elif isinstance(edu_src, dict):
        edu = {
            "degree": _clean_text(edu_src.get("degree") or ""),
            "field": _clean_education_field(edu_src.get("field") or ""),
            "institution": _clean_institution_name(edu_src.get("institution") or ""),
            "graduation_year": _clean_text(edu_src.get("graduation_year") or ""),
        }

    languages = raw_resume.get("languages") if isinstance(raw_resume.get("languages"), list) else []
    certifications = raw_resume.get("certifications") if isinstance(raw_resume.get("certifications"), list) else []

    return {
        "candidate_name": full_name,
        "email": email,
        "phone": phone,
        "current_location": location,
        "relocation_willing": bool(raw_resume.get("relocation_willing", False)),
        "total_experience_years": total_exp_num,
        "skills": skills,
        "technical_skills": technical if technical else skills,
        "education": edu,
        "certifications": certifications,
        "work_experience": work_experience,
        "projects": raw_resume.get("projects") if isinstance(raw_resume.get("projects"), list) else [],
        "languages": languages,
        "linkedin_url": _clean_text(raw_resume.get("linkedin_url") or ""),
        "github_url": _clean_text(raw_resume.get("github_url") or ""),
        "portfolio_url": _clean_text(raw_resume.get("portfolio_url") or ""),
        "summary": _clean_text(raw_resume.get("summary") or ""),
        "file_type_detected": _clean_text(raw_resume.get("file_type_detected") or ""),
    }


# Purpose: Extracts contact from text from input data.
def _extract_contact_from_text(text: str) -> dict[str, str]:
    compact_text = str(text or "")
    compact_text = re.sub(r"(?i)\s*(?:\[at\]|\(at\)|\bat\b)\s*", "@", compact_text)
    compact_text = re.sub(r"(?i)\s*(?:\[dot\]|\(dot\)|\bdot\b)\s*", ".", compact_text)
    compact_text = re.sub(r"\s*([@.])\s*", r"\1", compact_text)
    email_match = re.search(r"\b[A-Za-z0-9._%+-]+(?:\s+)?@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", compact_text)
    if not email_match:
        for around_at in re.findall(r"[A-Za-z0-9._%+\-\s]{1,80}@[A-Za-z0-9.\-\s]{1,80}", compact_text):
            candidate = re.sub(r"\s+", "", around_at)
            email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", candidate)
            if email_match:
                break
    phone_match = re.search(r"(?<!\d)(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{3,5}\)?[\s\-]?)\d{3,5}[\s\-]?\d{3,5}(?!\d)", text)
    linkedin_match = re.search(r"(https?://(?:www\.)?linkedin\.com/[^\s]+)", text, re.IGNORECASE)
    github_match = re.search(r"(https?://(?:www\.)?github\.com/[^\s]+)", text, re.IGNORECASE)
    return {
        "email": email_match.group(0).strip() if email_match else "",
        "phone": phone_match.group(0).strip() if phone_match else "",
        "linkedin_url": linkedin_match.group(1).strip() if linkedin_match else "",
        "github_url": github_match.group(1).strip() if github_match else "",
    }


# Purpose: Extracts name from text from input data.
def _extract_name_from_text(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    name_candidates = []
    for line in lines[:10]:
        line = _strip_contact_noise(line)
        low = line.lower()
        if "@" in line or any(k in low for k in ["phone", "email", "linkedin", "github", "summary", "experience", "education", "skills"]):
            continue
        if re.search(r"\d", line):
            continue
        words = re.findall(r"[A-Za-z][A-Za-z'\-]*", line)
        if len(words) == 1 and len(words[0]) >= 2:
            name_candidates.append(words[0])
            if len(name_candidates) >= 2:
                name = _clean_person_name(" ".join(name_candidates[:3]))
                if name:
                    return name
            continue
        name_candidates = []
        name = _clean_person_name(line)
        if name:
            return name
    for line in lines[:12]:
        line = _strip_contact_noise(line)
        low = line.lower()
        if "@" in line or any(k in low for k in ["phone", "email", "linkedin", "github", "summary", "experience", "education", "skills"]):
            continue
        if re.search(r"\d", line):
            continue
        name = _clean_person_name(line)
        if name:
            return name
    return ""


# Purpose: Extracts education from text from input data.
def _extract_education_from_text(text: str) -> dict[str, str]:
    degree_match = re.search(
        r"\b(bachelor(?:'s)?|master(?:'s)?|b\.?tech|m\.?tech|b\.?e|m\.?e|b\.?s|m\.?s|bca|mca|phd)\b",
        text,
        re.IGNORECASE,
    )
    grad_year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    degree = degree_match.group(0).strip() if degree_match else ""
    if degree:
        degree = degree.replace(".", "").title()
    return {
        "degree": degree,
        "institution": _extract_institution_from_text(text),
        "graduation_year": grad_year_match.group(1) if grad_year_match else "",
    }


# Purpose: Extracts skills from text from input data.
def _extract_skills_from_text(text: str) -> list[str]:
    lowered = text.lower()
    out = []
    for k in sorted(_KNOWN_SKILL_HINTS, key=len, reverse=True):
        if k in lowered:
            out.append(k)
    return _clean_skills(out)


# Purpose: Implements the date to month backend behavior.
def _date_to_month(value: str, *, for_end: bool = False) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.lower() in {"present", "current", "now"}:
        now = datetime.now()
        return now.year * 12 + now.month
    normalized = _normalize_date_to_iso(text)
    patterns = (
        r"^(?P<year>\d{4})-(?P<month>\d{1,2})(?:-\d{1,2})?$",
        r"^(?P<month>\d{1,2})/(?P<year>\d{4})$",
        r"^(?P<year>\d{4})$",
    )
    for pattern in patterns:
        match = re.match(pattern, normalized)
        if not match:
            continue
        year = int(match.group("year"))
        month = int(match.groupdict().get("month") or (12 if for_end else 1))
        return year * 12 + max(1, min(12, month))
    return None


# Purpose: Implements the estimate years from work backend behavior.
def _estimate_years_from_work(work: list[dict]) -> float:
    months = 0
    for row in work:
        start = str(row.get("start_date") or "")
        end = str(row.get("end_date") or "")
        start_month = _date_to_month(start)
        end_month = _date_to_month(end, for_end=True)
        if start_month is None:
            continue
        if end_month is None:
            end_month = datetime.now().year * 12 + datetime.now().month
        if end_month >= start_month:
            months += max(0, end_month - start_month + 1)
    return _normalize_experience_years(round(months / 12, 1) if months else 0.0)


# Purpose: Implements the explicit years from text backend behavior.
def _explicit_years_from_text(text: str) -> float:
    patterns = (
        r"\b(\d+(?:\.\d+)?)\s*\+?\s*years?\s*(?:of\s*)?(?:professional\s*)?(?:work\s*)?experience\b",
        r"\bexperience\s*(?:of|:)?\s*(\d+(?:\.\d+)?)\s*\+?\s*years?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            try:
                return _normalize_experience_years(float(match.group(1)))
            except Exception:
                return 0.0
    if re.search(r"\bfresher\b|\bentry[- ]level\b", text or "", re.IGNORECASE):
        return 0.0
    return 0.0


# Purpose: Extracts work from text from input data.
def _extract_work_from_text(text: str) -> list[dict]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    out: list[dict] = []
    date_range = re.compile(
        r"(?P<start>(?:\d{4}|\d{1,2}/\d{4}|[A-Za-z]{3,9}\s+\d{4}))\s*(?:-|–|—|to)\s*(?P<end>(?:Present|Current|Now|\d{4}|\d{1,2}/\d{4}|[A-Za-z]{3,9}\s+\d{4}))",
        re.IGNORECASE,
    )

    section = ""
    for idx, line in enumerate(lines):
        if _is_work_section_heading(line):
            section = "work"
            continue
        if _is_non_work_section_heading(line):
            section = "non-work"
            continue

        m = date_range.search(line)
        if not m:
            continue
        if section == "non-work":
            continue

        prev = lines[idx - 1] if idx - 1 >= 0 else ""
        nxt = lines[idx + 1] if idx + 1 < len(lines) else ""
        context = " ".join(x for x in (prev, line, nxt) if x)
        if _looks_like_education_line(context):
            continue

        before_date = line[: m.start()].strip(" -,@|")
        after_date = line[m.end() :].strip(" -,@|")

        role_company = before_date
        if not role_company or len(role_company) < 3:
            role_company = prev if prev and len(prev) < 100 else ""
        if _is_section_heading(role_company):
            role_company = ""
        if not role_company and section == "work" and nxt and len(nxt) < 100 and not date_range.search(nxt):
            role_company = nxt
        parts = re.split(r"\s+@\s+|\s+-\s+|,\s*", role_company, maxsplit=1)
        position = parts[0].strip() if parts else ""
        company = parts[1].strip() if len(parts) > 1 else ""
        if not company and after_date and len(after_date) < 80:
            company = after_date
        if not company and nxt and len(nxt) < 80 and not date_range.search(nxt) and not _is_section_heading(nxt):
            company = nxt.strip()
        if not _looks_like_role_line(position) and _looks_like_role_line(company):
            position, company = company, position
        if not _looks_like_role_line(position) and section != "work":
            continue

        out.append(
            {
                "company": company,
                "position": position,
                "start_date": _normalize_date_to_iso(m.group("start")),
                "end_date": _normalize_date_to_iso(m.group("end")),
                "responsibilities": [],
            }
        )
        if len(out) >= 5:
            break
    return out


# Purpose: Implements the enrich resume from text backend behavior.
def _enrich_resume_from_text(resume_json: dict, resume_text: str) -> dict:
    resume_json["candidate_name"] = _clean_person_name(resume_json.get("candidate_name") or "")
    if not resume_json.get("candidate_name"):
        name = _extract_name_from_text(resume_text)
        if name:
            resume_json["candidate_name"] = name

    contact = _extract_contact_from_text(resume_text)
    if not resume_json.get("email") and contact["email"]:
        resume_json["email"] = contact["email"]
    if not resume_json.get("phone") and contact["phone"]:
        resume_json["phone"] = contact["phone"]
    if not resume_json.get("linkedin_url") and contact["linkedin_url"]:
        resume_json["linkedin_url"] = contact["linkedin_url"]
    if not resume_json.get("github_url") and contact["github_url"]:
        resume_json["github_url"] = contact["github_url"]

    ed = resume_json.get("education") or {}
    edu_fill = _extract_education_from_text(resume_text)
    if isinstance(ed, dict):
        if not ed.get("degree"):
            ed["degree"] = edu_fill["degree"]
        if not ed.get("institution"):
            ed["institution"] = edu_fill["institution"]
        if not ed.get("graduation_year"):
            ed["graduation_year"] = edu_fill["graduation_year"]
        resume_json["education"] = ed

    skills = _clean_skills((resume_json.get("skills") or []) + _extract_skills_from_text(resume_text))
    resume_json["skills"] = skills
    if not (resume_json.get("technical_skills") or []):
        resume_json["technical_skills"] = skills

    cleaned_work = _clean_work_rows(resume_json.get("work_experience") or [])
    if not cleaned_work:
        cleaned_work = _extract_work_from_text(resume_text)
    resume_json["work_experience"] = _clean_work_rows(cleaned_work)

    explicit_years = _explicit_years_from_text(resume_text)
    work_years = _estimate_years_from_work(resume_json.get("work_experience") or [])
    try:
        parsed_years = float(resume_json.get("total_experience_years") or 0)
    except Exception:
        parsed_years = 0.0

    if explicit_years:
        resume_json["total_experience_years"] = _normalize_experience_years(explicit_years)
    elif work_years:
        resume_json["total_experience_years"] = _normalize_experience_years(work_years)
    elif parsed_years > 3 and not resume_json.get("work_experience"):
        resume_json["total_experience_years"] = 0
    elif parsed_years > 3 and len(resume_json.get("work_experience") or []) <= 1:
        resume_json["total_experience_years"] = work_years or 0
    else:
        resume_json["total_experience_years"] = _normalize_experience_years(parsed_years)
    return resume_json


# Purpose: Builds fallback comparison used by downstream code.
def _build_fallback_comparison(jd_data: dict, resume_data: dict) -> dict:
    jd_required = _clean_skills(jd_data.get("required_skills") or [])
    jd_preferred = _clean_skills(jd_data.get("preferred_skills") or [])
    resume_skills = _clean_skills((resume_data.get("skills") or []) + (resume_data.get("technical_skills") or []))

    resume_set = set(resume_skills)
    req_set = set(jd_required)
    pref_set = set(jd_preferred)

    matched_required = sorted(req_set.intersection(resume_set))
    matched_preferred = sorted(pref_set.intersection(resume_set))
    matched_all = matched_required + [s for s in matched_preferred if s not in matched_required]
    missing_required = sorted(req_set.difference(resume_set))

    if req_set:
        skills_match = int(round((len(matched_required) / max(1, len(req_set))) * 100))
    elif pref_set:
        skills_match = int(round((len(matched_preferred) / max(1, len(pref_set))) * 100))
    else:
        skills_match = 50 if resume_set else 0

    min_exp = int(jd_data.get("experience_years_min") or 0)
    total_exp = float(resume_data.get("total_experience_years") or 0)
    experience_match = 100 if min_exp <= 0 else int(max(0, min(100, round((total_exp / min_exp) * 100))))

    education_required = str(jd_data.get("education_required") or "").strip().lower()
    if education_required in {"not specified", "n/a", "na", "none", "null", "unknown"}:
        education_required = ""
    resume_degree = str((resume_data.get("education") or {}).get("degree") or "").strip().lower()
    if not education_required:
        education_match = 70
    elif resume_degree and any(k in resume_degree for k in ["b", "m", "phd", "degree", "bachelor", "master"]):
        education_match = 100
    else:
        education_match = 40

    match_score = int(round((skills_match * 0.6) + (experience_match * 0.25) + (education_match * 0.15)))
    status = "Selected" if match_score >= SELECTION_MATCH_THRESHOLD else "Rejected"

    strengths = [f"Matched skills: {', '.join(matched_all[:8])}"] if matched_all else []
    gaps = [f"Missing required skills: {', '.join(missing_required[:8])}"] if missing_required else []

    return {
        "match_score": max(0, min(100, match_score)),
        "status": status,
        "skills_match": skills_match,
        "experience_match": experience_match,
        "education_match": education_match,
        "matched_skills": matched_all,
        "missing_skills": missing_required,
        "strengths": strengths,
        "gaps": gaps,
        "recommendation": "Proceed to next round" if status == "Selected" else "Needs stronger role alignment",
        "failure_reason": "" if status == "Selected" else ("Insufficient required skill match" if missing_required else "Low overall match"),
    }


# Purpose: Implements the llm call backend behavior.
def llm_call(prompt: str, temperature: float = 0.0) -> str:
    """
    Make a call to OpenAI LLM.
    
    Args:
        prompt: The prompt to send to the LLM
        temperature: Temperature for response randomness
        
    Returns:
        LLM response text
    """
    if not _configure_openai_api_key():
        print("[WARN] OPENAI_API_KEY is not configured; LLM extraction/scoring will return empty results.")
        return "{}"

    try:
        messages = [
            {"role": "system", "content": "You are an expert recruiter and HR analyst. Return ONLY valid JSON when requested."},
            {"role": "user", "content": prompt},
        ]
        # Newer OpenAI SDK style
        if hasattr(openai, "chat") and hasattr(openai.chat, "completions"):
            response = openai.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=temperature,
            )
            content = response.choices[0].message.content
            return (content or "").strip()

        # Backward-compatible style
        response = openai.ChatCompletion.create(
            model=MODEL,
            messages=messages,
            temperature=temperature,
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"LLM call error: {str(e)}")
        return "{}"


# Purpose: Implements the llm json backend behavior.
def llm_json(prompt: str) -> dict:
    """
    Make an LLM call and parse the response as JSON.
    
    Args:
        prompt: The prompt to send
        
    Returns:
        Parsed JSON response as dictionary
    """
    raw = llm_call(prompt)
    
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from response
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    
    return {}


# Purpose: Extracts jd json from input data.
def extract_jd_json(jd_text: str) -> dict:
    """
    Extract structured JSON from a Job Description using LLM or regex fallback.
    
    Args:
        jd_text: Cleaned JD text
        
    Returns:
        Structured JD JSON
    """
    # Try LLM extraction first
    prompt = f"""
Analyze this Job Description and extract all relevant information into structured JSON format.

Job Description Text:
---
{jd_text}
---

Return ONLY valid JSON in this format (empty fields should be empty strings or empty arrays, NO null values):
{{
  "job_title": "",
  "required_skills": [],
  "preferred_skills": [],
  "experience_range": "",
  "experience_years_min": 0,
  "education_required": "",
  "location": "",
  "job_type": "",
  "salary_range": "",
  "responsibilities": [],
  "must_haves": [],
  "nice_to_haves": [],
  "industry": "",
  "company_name": ""
}}

Rules:
- Extract ALL required skills mentioned in the JD
- Extract preferred skills separately
- Include only concrete, role-relevant skills/tools/technologies (e.g., python, sql, fastapi, aws)
- Do NOT include generic traits (e.g., strong, eager, innovative, hardworking, team player)
- If not mentioned, use empty values
- Do NOT invent or assume information
- Keep extracted values exact and concise
"""
    
    jd_json = llm_json(prompt)
    
    # If LLM extraction failed or returned empty, use regex fallback
    if not jd_json or not jd_json.get("job_title"):
        print(f"[INFO] LLM extraction empty, using regex fallback for JD extraction")
        jd_json = extract_jd_regex(jd_text)
    
    # Ensure all required fields exist
    default_fields = {
        "job_title": "",
        "required_skills": [],
        "preferred_skills": [],
        "experience_range": "",
        "experience_years_min": 0,
        "education_required": "",
        "location": "",
        "job_type": "",
        "salary_range": "",
        "responsibilities": [],
        "must_haves": [],
        "nice_to_haves": [],
        "industry": "",
        "company_name": ""
    }
    
    for key, default_value in default_fields.items():
        if key not in jd_json:
            jd_json[key] = default_value

    jd_json["required_skills"] = _clean_skills(jd_json.get("required_skills") or [])
    jd_json["preferred_skills"] = _clean_skills(jd_json.get("preferred_skills") or [])
    # Backward-compatible key consumed elsewhere.
    jd_json["experience_required"] = jd_json.get("experience_range") or ""

    return jd_json


# Purpose: Extracts resume json from input data.
def extract_resume_json(resume_text: str) -> dict:
    """
    Extract structured JSON from a Resume using LLM or regex fallback.
    
    Args:
        resume_text: Cleaned resume text
        
    Returns:
        Structured resume JSON
    """
    prompt = f"""
You are an expert resume parser for an ATS. Extract facts from the resume text and return ONLY valid JSON.

Resume Text:
---
{resume_text}
---

Return strictly this JSON shape:
{{
  "full_name": "",
  "email": "",
  "phone_number": "",
  "location": "",
  "linkedin_url": "",
  "github_url": "",
  "portfolio_url": "",
  "summary": "",
  "skills": [],
  "technical_skills": [],
  "work_experience": [
    {{
      "job_title": "",
      "company": "",
      "start_date": "",
      "end_date": "",
      "responsibilities": []
    }}
  ],
  "education": [
    {{
      "degree": "",
      "field": "",
      "institution": "",
      "start_date": "",
      "end_date": "",
      "gpa": ""
    }}
  ],
  "certifications": [],
  "languages": [],
  "total_years_experience": 0,
  "file_type_detected": "txt",
  "confidence": {{
    "full_name": 0,
    "skills": 0,
    "work_experience": 0,
    "education": 0
  }},
  "warnings": []
}}

Rules:
- Parse accurately and do not hallucinate missing information.
- full_name must be a real person's name only. Do not use resume headline, summary, job title, degree, or phrase as name.
- Extract work_experience only from employment/internship sections. Do not turn projects, summaries, or skill sentences into jobs.
- Each work_experience item must have at least a real job_title or real company.
- If a date range is unclear, leave dates empty rather than guessing.
- Normalize dates to YYYY-MM-DD where possible (example: "May 2020" -> "2020-05-01").
- For missing values use "" for strings and [] for arrays.
- Extract concrete skills/tools/domains only. Avoid sentence fragments like "ed in python", "or nlp", "driven projects".
- Do NOT invent information
- Use "Present" for ongoing roles end_date.
"""
    
    resume_json = llm_json(prompt)

    # If LLM extraction failed or returned empty identity fields, use regex fallback.
    llm_name = str((resume_json or {}).get("full_name") or (resume_json or {}).get("candidate_name") or "").strip()
    llm_has_signal = bool(llm_name or (resume_json or {}).get("email") or (resume_json or {}).get("skills"))
    if not resume_json or not llm_has_signal:
        print(f"[INFO] LLM extraction empty, using regex fallback for resume extraction")
        regex_result = extract_resume_regex(resume_text)
        # Convert regex result into the same external shape, then normalize once.
        resume_json = {
            "full_name": regex_result.get("candidate_name", ""),
            "email": regex_result.get("email", ""),
            "phone_number": regex_result.get("phone", ""),
            "location": regex_result.get("current_location") or regex_result.get("location", ""),
            "linkedin_url": regex_result.get("linkedin_url", ""),
            "github_url": regex_result.get("github_url", ""),
            "portfolio_url": regex_result.get("portfolio_url", ""),
            "summary": "",
            "skills": regex_result.get("skills", []),
            "technical_skills": regex_result.get("technical_skills") or regex_result.get("skills", []),
            "work_experience": [
                {
                    "job_title": x.get("position", ""),
                    "company": x.get("company", ""),
                    "start_date": x.get("start_date", ""),
                    "end_date": x.get("end_date", ""),
                    "responsibilities": x.get("responsibilities", []) if isinstance(x.get("responsibilities"), list) else [],
                }
                for x in (regex_result.get("work_experience") or [])
                if isinstance(x, dict)
            ],
            "education": [
                {
                    "degree": (regex_result.get("education") or {}).get("degree", ""),
                    "field": (regex_result.get("education") or {}).get("field", ""),
                    "institution": (regex_result.get("education") or {}).get("institution", ""),
                    "start_date": "",
                    "end_date": (regex_result.get("education") or {}).get("graduation_year", ""),
                    "gpa": "",
                }
            ],
            "certifications": regex_result.get("certifications", []),
            "languages": regex_result.get("languages", []),
            "total_years_experience": regex_result.get("total_experience_years", 0),
            "file_type_detected": "txt",
            "relocation_willing": regex_result.get("willing_to_relocate", False),
        }

    resume_json = _normalize_resume_output(resume_json)
    resume_json = _enrich_resume_from_text(resume_json, resume_text)
    
    # Ensure all required fields exist
    default_fields = {
        "candidate_name": "",
        "email": "",
        "phone": "",
        "current_location": "",
        "relocation_willing": False,
        "total_experience_years": 0,
        "skills": [],
        "technical_skills": [],
        "education": {
            "degree": "",
            "field": "",
            "institution": "",
            "graduation_year": ""
        },
        "certifications": [],
        "work_experience": [],
        "projects": [],
        "languages": [],
        "linkedin_url": "",
        "github_url": "",
        "portfolio_url": "",
        "summary": "",
        "file_type_detected": "",
        "confidence": {},
        "warnings": [],
    }
    
    for key, default_value in default_fields.items():
        if key not in resume_json:
            resume_json[key] = default_value

    skills = _clean_skills(resume_json.get("skills") or [])
    technical = _clean_skills(resume_json.get("technical_skills") or [])
    merged = skills + [s for s in technical if s not in skills]
    resume_json["skills"] = merged
    resume_json["technical_skills"] = technical if technical else merged
    resume_json["candidate_name"] = _clean_person_name(resume_json.get("candidate_name") or "")
    resume_json["work_experience"] = _clean_work_rows(resume_json.get("work_experience") or [])
    if not resume_json["candidate_name"]:
        warnings = resume_json.get("warnings") if isinstance(resume_json.get("warnings"), list) else []
        if "candidate_name_needs_review" not in warnings:
            warnings.append("candidate_name_needs_review")
        resume_json["warnings"] = warnings

    return resume_json


# Purpose: Compares resume with jd and returns the match result.
def compare_resume_with_jd(jd_data: dict, resume_data: dict) -> dict:
    """
    Use LLM to compare a resume with a job description.
    Returns comprehensive comparison results including match score and detailed analysis.
    
    Args:
        jd_data: Structured job description data
        resume_data: Structured resume data
        
    Returns:
        Dictionary with comparison results including match_score, status, and detailed analysis
    """
    try:
        jd_payload = {
            "job_title": jd_data.get("job_title", ""),
            "required_skills": _clean_skills(jd_data.get("required_skills") or []),
            "preferred_skills": _clean_skills(jd_data.get("preferred_skills") or []),
            "experience_range": jd_data.get("experience_required") or jd_data.get("experience_range", ""),
            "experience_years_min": jd_data.get("experience_years_min", 0),
            "education_required": jd_data.get("education_required", ""),
            "responsibilities": jd_data.get("responsibilities") or [],
            "must_haves": jd_data.get("must_haves") or [],
            "nice_to_haves": jd_data.get("nice_to_haves") or [],
        }
        resume_payload = {
            "candidate_name": resume_data.get("candidate_name", ""),
            "education": resume_data.get("education") or {},
            "total_experience_years": resume_data.get("total_experience_years", 0),
            "skills": _clean_skills((resume_data.get("skills") or []) + (resume_data.get("technical_skills") or [])),
            "work_experience": resume_data.get("work_experience") or [],
            "projects": resume_data.get("projects") or [],
            "certifications": resume_data.get("certifications") or [],
            "summary": resume_data.get("summary", ""),
            "warnings": resume_data.get("warnings") or [],
        }

        # Prepare the comparison prompt. The LLM owns the score; code only validates shape/range.
        prompt = f"""
You are an expert recruiter and HR analyst. Compare the structured resume against the structured job description.

JOB_DESCRIPTION_JSON:
{json.dumps(jd_payload, ensure_ascii=False)}

RESUME_JSON:
{json.dumps(resume_payload, ensure_ascii=False)}

Please analyze the match and return ONLY a valid JSON object with this exact structure:
{{
    "match_score": <integer 0-100>,
    "status": "<'Selected' or 'Rejected'>",
    "skills_match": <integer 0-100>,
    "experience_match": <integer 0-100>,
    "education_match": <integer 0-100>,
    "matched_skills": [<list of matched skills>],
    "missing_skills": [<list of critical missing skills>],
    "strengths": [<list of candidate strengths>],
    "gaps": [<list of capability gaps>],
    "recommendation": "<brief hiring recommendation>",
    "failure_reason": "<if rejected, reason why>"
}}

Hard rules:
- You are responsible for the final match_score. Use 0-100 and be strict.
- Weight required skills most heavily, then experience, then education, then role/project relevance.
- Score must reflect actual overlap between JD required_skills and resume skills/work/projects.
- Do not award high scores for generic skills only.
- matched_skills must be skill names present or clearly evidenced in BOTH JD and resume.
- missing_skills must list JD required skills not found or not evidenced in the resume.
- If extraction warnings indicate missing candidate identity or weak extraction, reduce confidence and score conservatively.
- status must be "Selected" only when match_score >= 75 and critical required skills are mostly covered.
- Keep `strengths`, `gaps`, and `recommendation` concise and role-specific.
"""
        
        result = llm_json(prompt)
        if not result:
            fallback = _build_fallback_comparison(jd_payload, resume_payload)
            print(
                f"[INFO] LLM comparison empty; used fallback scorer. "
                f"Match score: {fallback['match_score']}, Status: {fallback['status']}"
            )
            return fallback
        
        # Validate and ensure required fields
        if not isinstance(result, dict):
            result = {}
        
        # Set defaults for missing fields
        defaults = {
            "match_score": 0,
            "status": "Rejected",
            "skills_match": 0,
            "experience_match": 0,
            "education_match": 0,
            "matched_skills": [],
            "missing_skills": [],
            "strengths": [],
            "gaps": [],
            "recommendation": "Not enough information for decision",
            "failure_reason": "Unable to complete evaluation"
        }
        
        for key, default_value in defaults.items():
            if key not in result:
                result[key] = default_value
        
        # Ensure match_score is within range
        if not isinstance(result["match_score"], int):
            try:
                result["match_score"] = int(result["match_score"])
            except:
                result["match_score"] = 0
        result["match_score"] = max(0, min(100, result["match_score"]))

        # Ensure status is valid and consistent with the LLM score.
        if result["status"] not in ["Selected", "Rejected"]:
            result["status"] = "Rejected" if result["match_score"] < SELECTION_MATCH_THRESHOLD else "Selected"
        if result["match_score"] < SELECTION_MATCH_THRESHOLD:
            result["status"] = "Rejected"

        for score_key in ("skills_match", "experience_match", "education_match"):
            try:
                result[score_key] = max(0, min(100, int(result.get(score_key) or 0)))
            except Exception:
                result[score_key] = 0

        result["matched_skills"] = _clean_skills(result.get("matched_skills") or [])
        result["missing_skills"] = _clean_skills(result.get("missing_skills") or [])
        
        print(f"[INFO] LLM comparison completed. Match score: {result['match_score']}, Status: {result['status']}")
        
        return result
        
    except Exception as e:
        print(f"[ERROR] LLM comparison failed: {str(e)}")
        try:
            return _build_fallback_comparison(jd_data, resume_data)
        except Exception:
            return {
                "match_score": 0,
                "status": "Rejected",
                "skills_match": 0,
                "experience_match": 0,
                "education_match": 0,
                "matched_skills": [],
                "missing_skills": [],
                "strengths": [],
                "gaps": [],
                "recommendation": "Evaluation error occurred",
                "failure_reason": str(e)
            }
 
