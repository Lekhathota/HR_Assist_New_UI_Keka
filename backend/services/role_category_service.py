# Backend file purpose: Broad role category categorization for candidates and JDs.
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import database as db


ROLE_CATEGORIES = [
    "Developer",
    "Tester",
    "PMO",
    "PM",
    "TL",
    "Business Analyst",
    "DevOps / Cloud",
    "Data",
    "Support",
    "Others",
]

DEFAULT_CATEGORY_MAPPINGS = [
    ("technical lead", "TL", 105),
    ("tech lead", "TL", 100),
    ("team lead", "TL", 100),
    ("lead engineer", "TL", 98),
    ("module lead", "TL", 95),
    ("delivery lead", "TL", 92),
    ("pmo", "PMO", 100),
    ("project coordinator", "PMO", 95),
    ("program coordinator", "PMO", 95),
    ("governance", "PMO", 85),
    ("reporting analyst", "PMO", 85),
    ("project manager", "PM", 100),
    ("program manager", "PM", 100),
    ("delivery manager", "PM", 98),
    ("scrum master", "PM", 95),
    ("product manager", "PM", 90),
    ("business analyst", "Business Analyst", 100),
    ("ba", "Business Analyst", 80),
    ("business systems analyst", "Business Analyst", 95),
    ("devops developer", "Developer", 104),
    ("developer", "Developer", 90),
    ("software engineer", "Developer", 90),
    ("engineer", "Developer", 78),
    ("programmer", "Developer", 88),
    ("full stack", "Developer", 95),
    ("fullstack", "Developer", 95),
    ("frontend", "Developer", 90),
    ("front end", "Developer", 90),
    ("backend", "Developer", 90),
    ("back end", "Developer", 90),
    ("mobile developer", "Developer", 90),
    ("java", "Developer", 82),
    ("python", "Developer", 82),
    ("react", "Developer", 82),
    ("angular", "Developer", 82),
    ("javascript", "Developer", 80),
    ("typescript", "Developer", 80),
    ("node", "Developer", 82),
    (".net", "Developer", 82),
    ("spring boot", "Developer", 82),
    ("microservices", "Developer", 78),
    ("flask", "Developer", 80),
    ("django", "Developer", 80),
    ("api developer", "Developer", 84),
    ("qa", "Tester", 95),
    ("tester", "Tester", 95),
    ("test engineer", "Tester", 95),
    ("quality analyst", "Tester", 92),
    ("quality assurance", "Tester", 92),
    ("testing", "Tester", 90),
    ("automation testing", "Tester", 95),
    ("automation engineer", "Tester", 90),
    ("manual testing", "Tester", 92),
    ("sdet", "Tester", 95),
    ("selenium", "Tester", 90),
    ("uat", "Tester", 86),
    ("devops", "DevOps / Cloud", 100),
    ("cloud", "DevOps / Cloud", 92),
    ("aws", "DevOps / Cloud", 86),
    ("azure", "DevOps / Cloud", 86),
    ("gcp", "DevOps / Cloud", 86),
    ("kubernetes", "DevOps / Cloud", 84),
    ("docker", "DevOps / Cloud", 82),
    ("data engineer", "Data", 100),
    ("data scientist", "Data", 100),
    ("data analyst", "Data", 96),
    ("machine learning", "Data", 90),
    ("sql", "Data", 78),
    ("etl", "Data", 84),
    ("support engineer", "Support", 94),
    ("technical support", "Support", 94),
    ("application support", "Support", 92),
    ("helpdesk", "Support", 90),
]

SOURCE_WEIGHTS = {
    "JD title": 20,
    "JD skills": 12,
    "JD responsibilities": 8,
    "JD text": 6,
    "Resume title": 18,
    "Current designation": 18,
    "Previous designation": 9,
    "Skills": 6,
    "Resume summary": 7,
    "Resume projects": 5,
    "Screening notes": 8,
    "Recruiter feedback": 10,
    "Total experience": 2,
}


def role_category_options() -> list[str]:
    return list(ROLE_CATEGORIES)


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return []


def _text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(_text(x) for x in value)
    if isinstance(value, dict):
        return " ".join(_text(x) for x in value.values())
    return str(value or "")


def _role_text_from_work_row(row: dict[str, Any]) -> str:
    return _text(
        [
            row.get("position"),
            row.get("job_title"),
            row.get("designation"),
            row.get("title"),
            row.get("role"),
        ]
    )


def _contains_keyword(text: str, keyword: str) -> bool:
    haystack = f" {text.lower()} "
    needle = " ".join(keyword.lower().split())
    if not needle:
        return False
    if re.search(r"\w", needle[0]) and re.search(r"\w", needle[-1]):
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None
    return needle in haystack


def _candidate_evidence(candidate: dict[str, Any], extra: dict[str, Any] | None = None) -> list[tuple[str, str]]:
    extra = extra or {}
    structured = candidate.get("structured_data") if isinstance(candidate.get("structured_data"), dict) else {}
    work = structured.get("work_experience") if isinstance(structured.get("work_experience"), list) else []
    current = ""
    previous: list[str] = []
    for index, row in enumerate(work):
        if not isinstance(row, dict):
            continue
        role = _role_text_from_work_row(row).strip()
        if not role:
            continue
        end_date = str(row.get("end_date") or "").strip().lower()
        if not current and (index == 0 or end_date == "present"):
            current = role
        else:
            previous.append(role)

    evidence = [
        (
            "Resume title",
            _text(
                [
                    structured.get("title"),
                    structured.get("resume_title"),
                    structured.get("headline"),
                    structured.get("role"),
                    structured.get("job_title"),
                    structured.get("current_role"),
                ]
            ),
        ),
        (
            "Current designation",
            current
            or _text(
                [
                    structured.get("current_designation"),
                    structured.get("designation"),
                    structured.get("current_position"),
                    structured.get("current_job_title"),
                ]
            ),
        ),
        ("Previous designation", " ".join(previous)),
        ("Skills", " ".join(_list(structured.get("skills")) + _list(structured.get("technical_skills")))),
        ("Total experience", str(structured.get("total_experience_years") or "")),
        ("Resume summary", _text([structured.get("summary"), structured.get("profile"), structured.get("objective")])),
        ("Resume projects", _text(structured.get("projects"))),
        ("Screening notes", " ".join([_text(candidate.get("screening_summary")), _text(extra.get("screening_notes"))])),
        ("Recruiter feedback", _text(candidate.get("recruiter_feedback") or extra.get("recruiter_feedback"))),
    ]
    return [(source, value) for source, value in evidence if value.strip()]


def _jd_evidence(jd: dict[str, Any]) -> list[tuple[str, str]]:
    structured = jd.get("structured_data") if isinstance(jd.get("structured_data"), dict) else {}
    evidence = [
        (
            "JD title",
            _text(
                [
                    jd.get("title"),
                    structured.get("job_title"),
                    structured.get("title"),
                    structured.get("role"),
                    structured.get("position"),
                ]
            ),
        ),
        (
            "JD skills",
            _text(
                [
                    jd.get("skills"),
                    structured.get("required_skills"),
                    structured.get("preferred_skills"),
                    structured.get("technical_skills"),
                ]
            ),
        ),
        ("JD responsibilities", _text([jd.get("responsibilities"), structured.get("responsibilities")])),
        (
            "JD text",
            _text(
                [
                    jd.get("raw_text"),
                    structured.get("summary"),
                    structured.get("description"),
                    structured.get("requirements"),
                ]
            ),
        ),
    ]
    return [(source, value) for source, value in evidence if value.strip()]


def _sub_tags(candidate: dict[str, Any], matched_keywords: list[str]) -> list[str]:
    structured = candidate.get("structured_data") if isinstance(candidate.get("structured_data"), dict) else {}
    tags = []
    for value in matched_keywords:
        tags.append(value.title() if value.islower() else value)
    tags.extend(_list(structured.get("skills"))[:10])
    years = 0.0
    try:
        years = float(structured.get("total_experience_years") or 0)
    except Exception:
        years = 0.0
    if years >= 8:
        tags.append("Senior")
    return list(dict.fromkeys(x for x in tags if x))[:16]


def _jd_sub_tags(jd: dict[str, Any], matched_keywords: list[str]) -> list[str]:
    structured = jd.get("structured_data") if isinstance(jd.get("structured_data"), dict) else {}
    tags = []
    for value in matched_keywords:
        tags.append(value.title() if value.islower() else value)
    tags.extend(_list(jd.get("skills"))[:10])
    tags.extend(_list(structured.get("required_skills"))[:10])
    return list(dict.fromkeys(x for x in tags if x))[:16]


def _categorization_source_label(sources: list[str]) -> str:
    labels = []
    source_set = set(sources)
    if "JD title" in source_set:
        labels.append("JD")
    if source_set.intersection({"JD skills", "JD responsibilities", "JD text"}):
        labels.append("uploaded JD")
    if source_set.intersection({"Resume title", "Current designation", "Previous designation", "Skills", "Total experience"}):
        labels.append("resume")
    if "Screening notes" in source_set:
        labels.append("screening result")
    if "Recruiter feedback" in source_set:
        labels.append("recruiter feedback")
    return ", ".join(labels) or "resume"


def _score_evidence(evidence: list[tuple[str, str]]) -> tuple[list[tuple[str, int]], dict[str, list[str]], list[str], list[str]]:
    mappings = [
        {"keyword": keyword, "category": category, "priority": priority}
        for keyword, category, priority in DEFAULT_CATEGORY_MAPPINGS
    ]
    category_scores: dict[str, int] = defaultdict(int)
    category_hits: dict[str, list[str]] = defaultdict(list)
    matched_keywords: list[str] = []
    matched_sources: list[str] = []

    suppress_generic_engineer_categories = {"Tester", "DevOps / Cloud", "Data", "Support"}

    for source, value in evidence:
        source_hits: list[tuple[str, str, int]] = []
        for mapping in mappings:
            keyword = str(mapping.get("keyword") or "").strip()
            category = str(mapping.get("category") or "").strip()
            if not keyword or not category or not _contains_keyword(value, keyword):
                continue
            priority = int(mapping.get("priority") or 0)
            source_hits.append((keyword, category, priority))

        has_specific_engineer_category = any(
            category in suppress_generic_engineer_categories for keyword, category, _priority in source_hits if keyword != "engineer"
        )
        for keyword, category, priority in source_hits:
            if keyword == "engineer" and category == "Developer" and has_specific_engineer_category:
                continue
            category_scores[category] += priority + SOURCE_WEIGHTS.get(source, 0)
            category_hits[category].append(keyword)
            matched_keywords.append(keyword)
            matched_sources.append(source)
    ranked = sorted(category_scores.items(), key=lambda item: (-item[1], ROLE_CATEGORIES.index(item[0])))
    return ranked, category_hits, matched_keywords, matched_sources


def _ranked_for_sources(evidence: list[tuple[str, str]], sources: set[str]) -> list[tuple[str, int]]:
    ranked, _category_hits, _matched_keywords, _matched_sources = _score_evidence(
        [(source, value) for source, value in evidence if source in sources]
    )
    return ranked


def categorize_candidate(candidate: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence = _candidate_evidence(candidate, extra)
    ranked, category_hits, matched_keywords, matched_sources = _score_evidence(evidence)

    if not ranked:
        return {
            "primary_category": "Others",
            "secondary_categories": [],
            "matched_keywords": [],
            "categorization_source": _categorization_source_label([src for src, _ in evidence]),
            "confidence_score": 30,
            "categorized_date": datetime.now(timezone.utc).isoformat(),
            "category_reason": "No configured category keyword matched; grouped under Others.",
            "sub_tags": _sub_tags(candidate, []),
        }

    title_ranked = _ranked_for_sources(evidence, {"Resume title", "Current designation", "Previous designation"})
    primary = (title_ranked[0][0] if title_ranked else ranked[0][0])
    unique_keywords = list(dict.fromkeys(matched_keywords))
    primary_hits = list(dict.fromkeys(category_hits.get(primary) or []))
    primary_score = next((score for category, score in ranked if category == primary), ranked[0][1])
    secondary = [category for category, score in ranked if category != primary and score >= max(70, int(primary_score * 0.45))][:3]
    confidence = min(98, max(45, int(45 + primary_score / 4)))
    reason = f"Matched {', '.join(primary_hits[:5])} for {primary}."
    if secondary:
        reason += f" Also matched secondary category evidence for {', '.join(secondary)}."

    return {
        "primary_category": primary,
        "secondary_categories": secondary,
        "matched_keywords": unique_keywords[:20],
        "categorization_source": _categorization_source_label(matched_sources),
        "confidence_score": confidence,
        "categorized_date": datetime.now(timezone.utc).isoformat(),
        "category_reason": reason,
        "sub_tags": _sub_tags(candidate, unique_keywords),
    }


def auto_categorize_candidate(candidate_id: int, extra: dict[str, Any] | None = None) -> dict[str, Any] | None:
    candidate = db.get_candidate_by_id(candidate_id)
    if not candidate:
        return None
    payload = categorize_candidate(candidate, extra)
    db.update_candidate(candidate_id, payload)
    return {**candidate, **payload}


def categorize_jd(jd: dict[str, Any]) -> dict[str, Any]:
    evidence = _jd_evidence(jd)
    ranked, category_hits, matched_keywords, matched_sources = _score_evidence(evidence)

    if not ranked:
        return {
            "job_category": "Others",
            "secondary_categories": [],
            "matched_keywords": [],
            "categorization_source": _categorization_source_label([src for src, _ in evidence]).replace("resume", "uploaded JD"),
            "confidence_score": 30,
            "categorized_date": datetime.now(timezone.utc).isoformat(),
            "category_reason": "No configured category keyword matched in the uploaded JD; grouped under Others.",
            "sub_tags": _jd_sub_tags(jd, []),
        }

    title_ranked = _ranked_for_sources(evidence, {"JD title"})
    primary = (title_ranked[0][0] if title_ranked else ranked[0][0])
    unique_keywords = list(dict.fromkeys(matched_keywords))
    primary_hits = list(dict.fromkeys(category_hits.get(primary) or []))
    primary_score = next((score for category, score in ranked if category == primary), ranked[0][1])
    secondary = [category for category, score in ranked if category != primary and score >= max(70, int(primary_score * 0.45))][:3]
    confidence = min(98, max(45, int(45 + primary_score / 4)))
    reason = f"Matched {', '.join(primary_hits[:5])} in JD information for {primary}."
    if secondary:
        reason += f" Also matched secondary category evidence for {', '.join(secondary)}."

    return {
        "job_category": primary,
        "secondary_categories": secondary,
        "matched_keywords": unique_keywords[:20],
        "categorization_source": _categorization_source_label(matched_sources).replace("resume", "uploaded JD"),
        "confidence_score": confidence,
        "categorized_date": datetime.now(timezone.utc).isoformat(),
        "category_reason": reason,
        "sub_tags": _jd_sub_tags(jd, unique_keywords),
    }
