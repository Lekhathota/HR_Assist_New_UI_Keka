# Backend file purpose: Core parsing, extraction, matching, or utility logic for regex extractor.
"""
Rule-based extraction using regex and pattern matching
Fallback for when LLM API is unavailable
"""

import re
from datetime import datetime
from app.utils import normalize_list, extract_years_experience


_BULLET_SPLIT_RE = r"(?:[\u2022*\-]|\d+[.)])"
_SECTION_BREAK_RE = (
    r"\n\s*(?:work|professional|employment|education|academic|projects?|summary|profile|"
    r"experience|certifications?|languages?|achievements?|awards?)\b"
)


# Purpose: Cleans and normalizes text value values.
def _clean_text_value(value: str) -> str:
    text = str(value or "").replace("\ufb01", "fi").replace("\ufb02", "fl")
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n:-|,")
    return "" if text.lower() in {"not specified", "unknown", "n/a", "na", "none"} else text


# Purpose: Implements the dedupe backend behavior.
def _dedupe(values: list[str]) -> list[str]:
    out = []
    seen = set()
    for value in values:
        cleaned = _clean_text_value(value)
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            out.append(cleaned)
    return out


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


# Purpose: Cleans and normalizes education field values.
def _clean_education_field(value: str) -> str:
    field = _clean_text_value(value)
    if not field:
        return ""
    field = re.sub(r"\b(?:from|at|with|during)\b.*$", "", field, flags=re.IGNORECASE).strip(" ,-")
    if len(field) > 60 or len(field.split()) > 6:
        return ""
    lowered = field.lower()
    skill_pollution = {"python", "html", "css", "javascript", "java script", "docker", "postman", "github", "git"}
    if any(skill in lowered for skill in skill_pollution):
        return ""
    if any(bad in lowered for bad in ("agile", "outcome", "environment", "project", "experience", "intern", "responsibil")):
        return ""
    if any(hint in lowered for hint in _EDUCATION_FIELD_HINTS):
        return field
    if re.fullmatch(r"(cse|cs|it|ece|eee|me|ce|ai|ml|bca|mca|mba)", lowered):
        return field.upper()
    return ""


# Purpose: Extracts education field from input data.
def _extract_education_field(text: str) -> str:
    patterns = (
        r"(?:bachelor(?:'s)?|master(?:'s)?|b\.?\s?tech|m\.?\s?tech|b\.?\s?e|m\.?\s?e|bca|mca|mba)\s+(?:in|of)\s+([^\n,.;|]+)",
        r"(?:b\.?\s?tech|m\.?\s?tech|b\.?\s?e|m\.?\s?e|bca|mca|mba)\s*[-:,]?\s+([^\n,.;|]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            field = _clean_education_field(match.group(1))
            if field:
                return field
    return ""


# Purpose: Cleans and normalizes institution name values.
def _clean_institution_name(value: str) -> str:
    institution = _clean_text_value(value)
    if not institution:
        return ""
    institution = re.sub(r"\s+(?:-|,|\|).*$", "", institution).strip()
    lowered = institution.lower()
    if len(institution) > 90 or len(institution.split()) > 10:
        return ""
    if any(bad in lowered for bad in ("agile", "outcome", "environment", "project", "experience", "intern", "responsibil")):
        return ""
    return institution


# Purpose: Extracts education institution from input data.
def _extract_education_institution(text: str) -> str:
    section_match = re.search(
        r"(?:education|academic(?:s| background)?|qualification(?:s)?)\s*:?\s*(.*?)(?=\n\s*(?:skills|projects?|work|professional|experience|certifications?)\b|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    search_text = section_match.group(1) if section_match else text
    pattern = (
        r"([A-Z][A-Za-z&.\- ]{2,}?"
        r"(?:University|College|Institute(?:\s+of\s+[A-Z][A-Za-z&.\- ]+)?|School)"
        r"(?:\s+of\s+[A-Z][A-Za-z&.\- ]+)?)"
    )
    matches = [_clean_institution_name(match) for match in re.findall(pattern, search_text)]
    matches = [match for match in matches if match]
    return matches[0] if matches else ""


# Purpose: Implements the degree from text backend behavior.
def _degree_from_text(value: str) -> tuple[str, int]:
    text = str(value or "").lower()
    if re.search(r"\b(ph\.?\s?d|doctorate)\b", text):
        return "PhD", 4
    if re.search(r"\b(m\.?\s?tech|m\.?\s?e|m\.?\s?s|msc|m\.sc|masters?|master'?s|mca|mba)\b", text):
        return "Master's", 3
    if re.search(r"\b(b\.?\s?tech|b\.?\s?e|b\.?\s?s|bsc|b\.sc|bachelor(?:'s)?|ba|b\.a|bca|bba|bcom|b\.com)\b", text):
        return "Bachelor's", 2
    if "continuing education" in text or "executive program" in text or "advanced" in text:
        return "Continuing Education", 1
    return "", 0


# Purpose: Extracts year from input data.
def _extract_year(value: str) -> str:
    years = re.findall(r"\b(19\d{2}|20\d{2})\b", value or "")
    return years[-1] if years else ""


# Purpose: Implements the field from education line backend behavior.
def _field_from_education_line(line: str, degree: str) -> str:
    patterns = (
        r"\bMSc\s+in\s+([^,|:]+)",
        r"\bM\.?Sc\.?\s+in\s+([^,|:]+)",
        r"\bMSc\s+([^,|:]+)",
        r"\bM\.?Sc\.?\s+([^,|:]+)",
        r"\bMasters?\s+in\s+([^,|:.]+)",
        r"\bMaster'?s\s+in\s+([^,|:.]+)",
        r"\bBachelor\s+of\s+Technology\.?\s+([^,|:.]+)",
        r"\bBA\s*\([^)]*\)\s+([^,|:.]+)",
        r"\bB\.?A\.?\s*\([^)]*\)\s+([^,|:.]+)",
        r"\bBachelor'?s\s+(?:in|of)\s+([^,|:.]+)",
        r"\bB\.?Tech\s+(?:in\s+)?([^,|:.]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            field = _clean_text_value(match.group(1))
            field = re.sub(r"^(?:in|of)\s+", "", field, flags=re.IGNORECASE)
            field = re.split(
                r"\b(?:19\d{2}|20\d{2}|\d{1,2}/\d{4}|university|college|institute|school)\b",
                field,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip(" ,-–")
            field = re.sub(r"\s+[A-Z][A-Za-z]+-[A-Z][A-Za-z]+$", "", field).strip(" ,-–")
            field = _clean_education_field(field)
            if field and len(field) <= 80:
                return field
    if degree == "Continuing Education":
        match = re.search(r"Continuing Education:?\s*([^,\n|:]+)", line, re.IGNORECASE)
        if match:
            return _clean_text_value(match.group(1))
    return ""


# Purpose: Extracts education details from input data.
def _extract_education_details(text: str) -> dict:
    section_match = re.search(
        r"(?:education|academic(?:s| background)?|qualification(?:s)?|education\s*&\s*advanced\s*specializations)\s*:?\s*(.*?)(?=\n\s*(?:research|publications?|work|professional|experience|certifications?|technical skills)\b|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    section = section_match.group(1) if section_match else text
    entries = []
    pending_detail = ""
    pending_field_fragment = ""
    for raw_line in section.splitlines():
        line = _clean_text_value(raw_line)
        if not line:
            continue
        has_institution = re.search(r"(university|college|institute|school|iim|isi|lse|stanford|oxford)", line, re.IGNORECASE)
        degree, priority = _degree_from_text(line)
        if degree and not has_institution:
            pending_detail = line
            continue
        if entries and not entries[-1].get("field") and not has_institution:
            combined = f"{pending_field_fragment} {line}".strip()
            if re.search(r"\band$", combined, re.IGNORECASE):
                pending_field_fragment = combined
                continue
            field = _clean_education_field(combined)
            if field:
                entries[-1]["field"] = field
                pending_field_fragment = ""
                continue
            if re.search(r"\b(artificial|computer|information|data|machine|business|systems|science|technology)\b", line, re.IGNORECASE):
                pending_field_fragment = combined
                continue
        if not has_institution:
            continue
        institution = ""
        if "|" in line:
            institution = _clean_institution_name(line.split("|", 1)[0])
            detail = line.split("|", 1)[1]
        else:
            institution = _extract_education_institution(line)
            detail = f"{pending_detail} {line}".strip() if pending_detail else line
        degree, priority = _degree_from_text(detail)
        if not degree and institution:
            degree, priority = _degree_from_text(line)
        if not institution:
            continue
        pending_detail = ""
        pending_field_fragment = ""
        entries.append(
            {
                "degree": degree,
                "field": _field_from_education_line(detail, degree),
                "institution": institution,
                "graduation_year": _extract_year(detail) or _extract_year(line),
                "priority": priority,
            }
        )
    if not entries:
        return {
            "degree": "",
            "field": _extract_education_field(text),
            "institution": _extract_education_institution(text),
            "graduation_year": _extract_year(text),
        }
    entries.sort(key=lambda item: (item["priority"], item["graduation_year"]), reverse=True)
    best = entries[0]
    best.pop("priority", None)
    return best


# Purpose: Implements the strip contact noise backend behavior.
def _strip_contact_noise(value: str) -> str:
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", " ", value or "")
    text = re.sub(r"https?://\S+|(?:www\.)?(?:linkedin|github)\.com/\S+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)", " ", text)
    return _clean_text_value(text)


# Purpose: Extracts url from input data.
def _extract_url(text: str, domain: str) -> str:
    pattern = rf"(https?://(?:www\.)?{re.escape(domain)}/[A-Za-z0-9_./%+\- \n]+|{re.escape(domain)}/[A-Za-z0-9_./%+\- \n]+)"
    match = re.search(pattern, text or "", re.IGNORECASE)
    if not match:
        return ""
    url = re.sub(r"\s+", "", match.group(1)).strip(".,;)")
    url = re.split(
        r"(?:TECHNICALSKILLS|WORKEXPERIENCE|PROFESSIONALEXPERIENCE|EDUCATION|PROJECTS|SUMMARY|PROFILE)",
        url,
        maxsplit=1,
    )[0]
    if not url.startswith("http"):
        url = f"https://www.{url}" if url.startswith(domain) else f"https://{url}"
    return url


# Purpose: Normalizes resume date into the app's expected format.
def _normalize_resume_date(value: str) -> str:
    text = _clean_text_value(value)
    if not text:
        return ""
    if text.lower() in {"present", "current", "now"}:
        return "Present"
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
    year_match = re.fullmatch(r"(19\d{2}|20\d{2})", text)
    if year_match:
        return f"{year_match.group(1)}-01-01"
    short_month = re.fullmatch(r"([A-Za-z]{3,9})[’']?(\d{2})", text)
    if short_month:
        month = month_map.get(short_month.group(1).lower())
        year = int(short_month.group(2))
        year += 2000 if year < 50 else 1900
        return f"{year}-{month or '01'}-01"
    long_month = re.fullmatch(r"([A-Za-z]{3,9})\s+(19\d{2}|20\d{2})", text)
    if long_month:
        return f"{long_month.group(2)}-{month_map.get(long_month.group(1).lower(), '01')}-01"
    return text


# Purpose: Implements the date to month backend behavior.
def _date_to_month(value: str) -> int | None:
    text = _normalize_resume_date(value)
    if not text:
        return None
    if text == "Present":
        now = datetime.now()
        return now.year * 12 + now.month
    match = re.match(r"^(19\d{2}|20\d{2})-(\d{2})", text)
    if match:
        return int(match.group(1)) * 12 + int(match.group(2))
    return None


# Purpose: Implements the estimate experience years backend behavior.
def _estimate_experience_years(work_experience: list[dict]) -> float:
    ranges = []
    for row in work_experience:
        start = _date_to_month(str(row.get("start_date") or ""))
        end = _date_to_month(str(row.get("end_date") or ""))
        if start and end and end >= start:
            ranges.append((start, end))
    if not ranges:
        return 0.0
    ranges.sort()
    merged = []
    for start, end in ranges:
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    months = sum(end - start + 1 for start, end in merged)
    return round(months / 12, 1)


# Purpose: Extracts jd regex from input data.
def extract_jd_regex(text: str) -> dict:
    """
    Extract JD information using regex patterns (no API needed).

    Args:
        text: Raw JD text

    Returns:
        Extracted JD JSON structure
    """

    # Clean text
    text_lower = text.lower()
    text_clean = text.strip()

    # Extract Job Title
    job_title = ""
    jd_title_match = re.search(r'job\s*title\s*:?\s*([^\n]+)', text_lower)
    if jd_title_match:
        job_title = jd_title_match.group(1).strip()
    else:
        # Fallback: look in first few lines
        lines = text.split('\n')
        for line in lines[:10]:
            if 'engineer' in line.lower() or 'developer' in line.lower():
                job_title = line.strip()
                break

    # Extract Department
    department = ""
    dept_match = re.search(r'department\s*:?\s*([^\n]+)', text_lower)
    if dept_match:
        department = dept_match.group(1).strip()

    # Extract Location
    location = ""
    loc_match = re.search(r'location\s*:?\s*([^\n]+)', text_lower)
    if loc_match:
        location = loc_match.group(1).strip()

    # Extract Company Name
    company_name = ""
    company_match = re.search(r'company\s*:?\s*([^\n]+)|zelis|our company', text_lower)
    if company_match:
        company_name = company_match.group(1).strip() if company_match.group(1) else "Zelis"

    # Extract Required Skills
    required_skills = []

    # Look for "required skills:" section
    skills_match = re.search(
        r'required\s*skills?\s*:?\s*(.*?)(?=preferred|nice|nice-to-have|education|bachelor)',
        text_lower,
        re.DOTALL
    )

    if skills_match:
        skills_text = skills_match.group(1)
        # Extract bullet points
        skill_items = re.findall(r'[•\-\*]\s*([^\n]+)', skills_text)
        for item in skill_items:
            skill = item.strip()
            # Clean up skill text
            skill = re.sub(r'\([^)]*\)', '', skill)  # Remove parentheses
            if skill and len(skill) > 2:
                required_skills.append(skill)

    # Additional skill extraction patterns
    skill_keywords = [
        'azure', 'aws', 'docker', 'kubernetes', 'python', 'bash', 'powershell',
        'terraform', 'ansible', 'jenkins', 'git', 'github', 'prometheus', 'grafana',
        'ci/cd', 'devops', 'linux', 'windows', 'java', 'javascript', 'react',
        'mongodb', 'postgres', 'mysql', 'redis', 'elasticsearch',
        'microservices', 'serverless', 'api', 'rest', 'graphql'
    ]

    for keyword in skill_keywords:
        if keyword in text_lower and keyword not in ' '.join(required_skills).lower():
            # Capitalize first letter
            required_skills.append(keyword.title())

    # Extract Preferred Skills
    preferred_skills = []
    pref_match = re.search(
        r'preferred.*?(?=education|bachelor|disclaimer|$)',
        text_lower,
        re.DOTALL
    )

    if pref_match:
        pref_text = pref_match.group(0)
        pref_items = re.findall(r'[•\-\*]\s*([^\n]+)', pref_text)
        for item in pref_items:
            skill = item.strip()
            skill = re.sub(r'\([^)]*\)', '', skill)
            if skill and len(skill) > 2:
                preferred_skills.append(skill)

    # Extract Experience Years
    experience_years_min = 0
    exp_match = re.search(r'(\d+)\s*-\s*(\d+)\s*years?|(\d+)\+?\s*years?', text_lower)
    if exp_match:
        if exp_match.group(1):
            experience_years_min = int(exp_match.group(1))
        elif exp_match.group(3):
            experience_years_min = int(exp_match.group(3))

    # Extract Education
    education_required = ""
    edu_match = re.search(
        r"bachelor'?s?\s*(?:degree)?\s*(?:in)?\s*([^\n.]+)|college|university",
        text_lower
    )
    if edu_match:
        education_required = "Bachelor's degree"
        if edu_match.group(1) and len(edu_match.group(1)) > 2:
            education_required = f"Bachelor's in {edu_match.group(1).strip()}"

    # Extract Job Type
    job_type = "Full-time"

    # Extract Salary Range (if present)
    salary_range = ""
    salary_match = re.search(r'\$[\d,]+\s*-\s*\$[\d,]+|\$[\d,]+k', text)
    if salary_match:
        salary_range = salary_match.group(0)

    # Extract Responsibilities
    responsibilities = []
    resp_match = re.search(
        r'(?:key\s*)?responsibilities?\s*:?\s*(.*?)(?=required|skills)',
        text_lower,
        re.DOTALL
    )

    if resp_match:
        resp_text = resp_match.group(1)
        resp_items = re.findall(r'[•\-\*]\s*([^\n]+)', resp_text)
        for item in resp_items[:8]:  # Limit to 8
            resp = item.strip()
            if resp and len(resp) > 10:
                responsibilities.append(resp)

    # Extract Industry
    industry = ""
    if 'healthcare' in text_lower:
        industry = "Healthcare"
    elif 'finance' in text_lower:
        industry = "Finance"
    elif 'tech' in text_lower or 'software' in text_lower:
        industry = "Technology"

    return {
        "job_title": job_title.title() if job_title else "Unknown Position",
        "required_skills": required_skills[:10],  # Limit to 10
        "preferred_skills": preferred_skills[:5],  # Limit to 5
        "experience_range": f"{experience_years_min}+ years" if experience_years_min > 0 else "Not specified",
        "experience_years_min": experience_years_min,
        "education_required": education_required if education_required else "Not specified",
        "location": location.title() if location else "Not specified",
        "job_type": job_type,
        "salary_range": salary_range if salary_range else "Not specified",
        "responsibilities": responsibilities,
        "industry": industry if industry else "Not specified",
        "company_name": company_name if company_name else "Not specified"
    }


# Purpose: Extracts resume regex from input data.
def extract_resume_regex(text: str) -> dict:
    """
    Extract resume information using regex patterns (no API needed).

    Args:
        text: Raw resume text

    Returns:
        Extracted resume JSON structure
    """
    return _extract_resume_regex_v2(text)

    text_lower = text.lower()

    # Extract Name (usually at top)
    candidate_name = ""
    lines = text.split('\n')
    for line in lines[:5]:
        if len(line.strip()) > 3 and not any(x in line.lower() for x in ['email', 'phone', 'address']):
            candidate_name = line.strip()
            break

    # Extract Skills
    skills = []
    known_skills = {
        "python", "java", "javascript", "typescript", "react", "node", "fastapi", "flask", "django",
        "sql", "postgresql", "mysql", "mongodb", "redis", "docker", "kubernetes", "aws", "azure",
        "gcp", "git", "jenkins", "terraform", "ansible", "linux", "html", "css", "rest", "graphql",
        "pandas", "numpy", "spark", "tableau", "power bi", "excel",
    }
    stop_words = {"strong", "eager", "innovative", "solid", "project", "work", "development", "have"}

    skills_match = re.search(
        r"(?:technical\s+)?skills?\s*:?\s*(.*?)(?=\n(?:work|professional|education|projects|summary|experience)|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if skills_match:
        skills_text = skills_match.group(1)
        tokens = re.split(r"[,|\n;/•\-]+", skills_text)
        for tok in tokens:
            skill = re.sub(r"[^A-Za-z0-9\+\#\.\-/ ]+", "", tok).strip().lower()
            skill = re.sub(r"\s+", " ", skill)
            if not skill or len(skill) < 2:
                continue
            if skill in stop_words:
                continue
            if skill in known_skills or (" " in skill and len(skill.split()) <= 3):
                skills.append(skill)

    # Extract Total Experience
    total_experience_years = 0
    exp_match = re.search(r'(\d+)\s*[\+]?\s*years?\s*(?:of\s*)?experience', text_lower)
    if exp_match:
        total_experience_years = int(exp_match.group(1))

    # Extract Education
    education = {"degree": "Not specified", "field": "Not specified"}
    edu_match = re.search(
        r"(?:bachelor'?s?|master'?s?|phd|b\.s\.|m\.s\.)\s*(?:in|of)?\s*([^\n.]+)",
        text,
        re.IGNORECASE
    )

    if edu_match:
        if "bachelor" in text_lower[:edu_match.start()]:
            education["degree"] = "Bachelor's"
        elif "master" in text_lower[:edu_match.start()]:
            education["degree"] = "Master's"
        elif "phd" in text_lower[:edu_match.start()]:
            education["degree"] = "PhD"

        education["field"] = edu_match.group(1).strip()

    # Extract Work Experience
    work_experience = []

    # Look for company/role patterns
    company_role_pattern = r'(?:company|position|role)?\s*([^\n]+?)(?:\s+[-–]\s+|,\s*)([^\n]+)\s+\(([0-9\/]+)\s*(?:[-–]\s*|to\s+)([0-9\/]*)\)'
    matches = re.finditer(company_role_pattern, text, re.IGNORECASE)

    for match in matches:
        work_experience.append({
            "company": match.group(1).strip(),
            "position": match.group(2).strip(),
            "start_date": match.group(3).strip(),
            "end_date": match.group(4).strip() if match.group(4) else "Present"
        })

    # If not found with above pattern, try simpler pattern
    if not work_experience:
        exp_section = re.search(
            r'(?:work\s*)?experience\s*:?\s*(.*?)(?=education|skills|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )

        if exp_section:
            exp_text = exp_section.group(1)
            # Look for company names and dates
            companies = re.findall(r'^([^,\n]+)(?:\n|,)', exp_text, re.MULTILINE)
            dates = re.findall(r'(\d{1,2}/\d{4}|\d{4})', exp_text)

            for company in companies[:3]:  # Limit to 3
                work_experience.append({
                    "company": company.strip(),
                    "position": "Not specified",
                    "start_date": dates[0] if dates else "Not specified",
                    "end_date": dates[1] if len(dates) > 1 else "Present"
                })

    # Extract Current Role
    current_role = "Not specified"
    if work_experience:
        current_role = work_experience[0].get("position", "Not specified")

    # Extract Location
    location = ""
    loc_match = re.search(r'(?:location|city|based in)\s*:?\s*([^\n,]+)', text, re.IGNORECASE)
    if loc_match:
        location = loc_match.group(1).strip()

    # Willing to Relocate
    willing_to_relocate = "open to relocation" in text_lower or "willing to relocate" in text_lower

    # Extract Contact Information
    email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
    phone_match = re.search(r"(?<!\d)(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{3,5}\)?[\s\-]?)\d{3,5}[\s\-]?\d{3,5}(?!\d)", text)
    linkedin_match = re.search(r"(https?://(?:www\.)?linkedin\.com/[^\s]+)", text, re.IGNORECASE)
    github_match = re.search(r"(https?://(?:www\.)?github\.com/[^\s]+)", text, re.IGNORECASE)

    email = email_match.group(0).strip() if email_match else ""
    phone = phone_match.group(0).strip() if phone_match else ""
    linkedin_url = linkedin_match.group(1).strip() if linkedin_match else ""
    github_url = github_match.group(1).strip() if github_match else ""

    # Extract Certifications
    certifications = []
    cert_match = re.search(
        r"(?:certifications?|certificates?|licenses?)\s*:?\s*(.*?)(?=languages|projects|$)",
        text,
        re.IGNORECASE | re.DOTALL
    )
    if cert_match:
        cert_text = cert_match.group(1)
        cert_items = re.findall(r"[•\-\*]?\s*([^\n]+)", cert_text)
        for item in cert_items[:10]:  # Limit to 10
            cert = item.strip()
            if cert and len(cert) > 3:
                certifications.append(cert)

    # Extract Languages
    languages = []
    lang_match = re.search(
        r"(?:languages?|linguistic|fluency)\s*:?\s*(.*?)(?=certifications|projects|$)",
        text,
        re.IGNORECASE | re.DOTALL
    )
    if lang_match:
        lang_text = lang_match.group(1)
        lang_items = re.findall(r"[•\-\*]?\s*([^\n,]+)", lang_text)
        for item in lang_items[:10]:  # Limit to 10
            lang = item.strip()
            if lang and len(lang) > 1:
                languages.append(lang)

    return {
        "candidate_name": candidate_name if candidate_name else "Unknown",
        "email": email,
        "phone": phone,
        "linkedin_url": linkedin_url,
        "github_url": github_url,
        "skills": list(dict.fromkeys(skills))[:20],
        "current_role": current_role,
        "total_experience_years": total_experience_years if total_experience_years > 0 else 0,
        "education": education,
        "work_experience": work_experience,
        "location": location if location else "Not specified",
        "willing_to_relocate": willing_to_relocate,
        "certifications": certifications,
        "languages": languages,
    }


# Purpose: Extracts resume regex v2 from input data.
def _extract_resume_regex_v2(text: str) -> dict:
    text = str(text or "")
    text_lower = text.lower()
    lines = [_clean_text_value(line) for line in text.splitlines()]
    lines = [line for line in lines if line]

    email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
    phone_match = re.search(r"(?<!\d)(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{3,5}\)?[\s\-]?)\d{3,5}[\s\-]?\d{3,5}(?!\d)", text)
    linkedin_url = _extract_url(text, "linkedin.com")
    github_url = _extract_url(text, "github.com")
    portfolio_match = re.search(r"(https?://(?!.*(?:linkedin|github))[^\s]+)", text, re.IGNORECASE)

    # Purpose: Implements the looks like name backend behavior.
    def _looks_like_name(value: str) -> bool:
        value = _strip_contact_noise(value)
        low = value.lower()
        if "@" in value or re.search(r"\d", value):
            return False
        if any(word in low for word in ("resume", "curriculum", "developer", "engineer", "skills", "experience", "education", "profile", "summary")):
            return False
        words = re.findall(r"[A-Za-z][A-Za-z'\-]*", value)
        return 2 <= len(words) <= 5 and len(" ".join(words)) <= 60

    candidate_name = ""
    single_name_parts = []
    for line in lines[:12]:
        name_line = _strip_contact_noise(line)
        if _looks_like_name(name_line):
            candidate_name = " ".join(part[:1].upper() + part[1:] for part in re.findall(r"[A-Za-z][A-Za-z'\-]*", name_line))
            break
        words = re.findall(r"[A-Za-z][A-Za-z'\-]*", name_line)
        if len(words) == 1 and not re.search(r"\d|@|phone|email|linkedin|github", name_line, re.IGNORECASE):
            single_name_parts.append(words[0])
            if len(single_name_parts) >= 2:
                joined = " ".join(single_name_parts[:3])
                if _looks_like_name(joined):
                    candidate_name = joined.title()
                    break
        else:
            single_name_parts = []

    known_skills = {
        "python", "java", "javascript", "typescript", "react", "node.js", "node", "fastapi", "flask", "django",
        "sql", "postgresql", "postgres", "mysql", "mongodb", "redis", "docker", "kubernetes", "aws", "azure",
        "gcp", "git", "github", "jenkins", "terraform", "ansible", "linux", "html", "css", "rest", "graphql",
        "pandas", "numpy", "spark", "tableau", "power bi", "excel", "selenium", "manual testing",
        "automation testing", "pytest", "junit", "cypress", "postman", "machine learning", "deep learning",
        "generative ai", "nlp", "llm", "scikit-learn", "tensorflow", "pytorch", "jira", "figma", "ci/cd",
    }
    skill_aliases = {"node": "node.js", "postgres": "postgresql", "reactjs": "react", "nodejs": "node.js"}
    skills = []

    skills_match = re.search(
        rf"(?:technical\s+)?skills?\s*:?\s*(.*?)(?={_SECTION_BREAK_RE}|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    skill_sources = [skills_match.group(1)] if skills_match else []
    skill_sources.append(text)
    for source in skill_sources:
        for skill in sorted(known_skills, key=len, reverse=True):
            if re.search(rf"(?<![a-z0-9]){re.escape(skill)}(?![a-z0-9])", source, re.IGNORECASE):
                skills.append(skill_aliases.get(skill, skill))

    total_experience_years = 0.0
    exp_patterns = (
        r"\b(\d+(?:\.\d+)?)\s*\+?\s*years?\s*(?:of\s*)?(?:professional\s*)?(?:work\s*)?experience\b",
        r"\bexperience\s*(?:of|:)?\s*(\d+(?:\.\d+)?)\s*\+?\s*years?\b",
    )
    for pattern in exp_patterns:
        exp_match = re.search(pattern, text, re.IGNORECASE)
        if exp_match:
            total_experience_years = float(exp_match.group(1))
            break

    education = _extract_education_details(text)

    date_range = re.compile(
        r"\(?(?P<start>(?:\d{4}|\d{1,2}/\d{4}|[A-Za-z]{3,9}[’']?\d{2}|[A-Za-z]{3,9}\s+\d{4}))\s*(?:-|–|—|to)\s*(?P<end>(?:Present|Current|Now|\d{4}|\d{1,2}/\d{4}|[A-Za-z]{3,9}[’']?\d{2}|[A-Za-z]{3,9}\s+\d{4}))\)?",
        re.IGNORECASE,
    )
    role_words = r"developer|engineer|analyst|administrator|architect|consultant|designer|intern|trainee|lead|manager|specialist|tester|qa|sde|associate|executive|scientist|devops|frontend|backend|full stack|data"
    work_experience = []
    current_section = ""
    for idx, line in enumerate(lines):
        low = line.lower().rstrip(":")
        if low in {"work experience", "professional experience", "experience", "employment history", "internship", "internships"}:
            current_section = "work"
            continue
        if low in {"education", "projects", "skills", "technical skills", "certifications", "languages", "summary", "profile"}:
            current_section = "other"
            continue
        match = date_range.search(line)
        if not match or current_section == "other":
            continue
        prev = lines[idx - 1] if idx > 0 else ""
        next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
        role_company = line[: match.start()].strip(" -,@|")
        if (not role_company or not re.search(role_words, role_company, re.IGNORECASE)) and prev and len(prev) < 180:
            role_company = prev
        if not role_company and current_section == "work" and next_line and len(next_line) < 100:
            role_company = next_line
        role_company = re.sub(r"^[•*\-\s]+", "", role_company).strip()
        parts = re.split(r"\s+@\s+|(?<!\d)\s*[-–—]\s*(?!\d)|:\s+|,\s*", role_company, maxsplit=1)
        position = _clean_text_value(parts[0] if parts else "")
        company = _clean_text_value(parts[1] if len(parts) > 1 else "")
        if company and re.search(role_words, company, re.IGNORECASE) and not re.search(role_words, position, re.IGNORECASE):
            company, position = position, company
        after_date = _clean_text_value(line[match.end():])
        if not company and after_date and len(after_date) < 80:
            company = after_date
        if not re.search(role_words, position, re.IGNORECASE) and re.search(role_words, company, re.IGNORECASE):
            position, company = company, position
        if not position and not company:
            continue
        if current_section != "work" and not re.search(role_words, position, re.IGNORECASE):
            continue
        work_experience.append(
            {
                "company": company,
                "position": position,
                "job_title": position,
                "start_date": _normalize_resume_date(match.group("start")),
                "end_date": "Present" if match.group("end").lower() in {"present", "current", "now"} else match.group("end"),
                "responsibilities": [],
            }
        )
        if len(work_experience) >= 8:
            break

    for row in work_experience:
        row["end_date"] = "Present" if str(row["end_date"]).lower() in {"present", "current", "now"} else _normalize_resume_date(row["end_date"])
    if not total_experience_years:
        total_experience_years = _estimate_experience_years(work_experience)

    current_role = work_experience[0]["position"] if work_experience else ""
    location_match = re.search(r"\b(?:location|city|current location)\s*:?\s*([^\n|]+)", text, re.IGNORECASE)
    location = _clean_text_value(location_match.group(1)) if location_match else ""

    certifications = []
    cert_match = re.search(rf"(?:certifications?|certificates?|licenses?)\s*:?\s*(.*?)(?={_SECTION_BREAK_RE}|$)", text, re.IGNORECASE | re.DOTALL)
    if cert_match:
        certifications = _dedupe(re.split(rf"{_BULLET_SPLIT_RE}|[,;\n]", cert_match.group(1)))[:10]

    languages = []
    lang_match = re.search(rf"(?:languages?|linguistic|fluency)\s*:?\s*(.*?)(?={_SECTION_BREAK_RE}|$)", text, re.IGNORECASE | re.DOTALL)
    if lang_match:
        languages = _dedupe(re.split(rf"{_BULLET_SPLIT_RE}|[,;\n]", lang_match.group(1)))[:10]

    normalized_skills = _dedupe(skills)[:30]
    return {
        "candidate_name": candidate_name,
        "email": email_match.group(0).strip() if email_match else "",
        "phone": phone_match.group(0).strip() if phone_match else "",
        "linkedin_url": linkedin_url,
        "github_url": github_url,
        "portfolio_url": portfolio_match.group(1).strip() if portfolio_match else "",
        "skills": normalized_skills,
        "technical_skills": normalized_skills,
        "current_role": current_role,
        "total_experience_years": total_experience_years,
        "education": education,
        "work_experience": work_experience,
        "location": location,
        "current_location": location,
        "willing_to_relocate": bool(re.search(r"\b(open to|willing to)\s+relocat", text_lower)),
        "relocation_willing": bool(re.search(r"\b(open to|willing to)\s+relocat", text_lower)),
        "certifications": certifications,
        "languages": languages,
        "projects": [],
        "summary": "",
        "file_type_detected": "txt",
    }
 
