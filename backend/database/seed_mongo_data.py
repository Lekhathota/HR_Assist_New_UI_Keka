# Backend file purpose: Database migration, import, or seed utility for seed mongo data.
"""
Seed MongoDB Atlas with sample Recruitment Assist data.

Usage from project root:
  npm run seed:backend
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv

load_dotenv(os.path.join(BACKEND_DIR, ".env"))

import database as db  # noqa: E402


# Purpose: Implements the jd seed rows backend behavior.
def _jd_seed_rows() -> list[dict]:
    return [
        {
            "title": "Frontend React Developer",
            "department": "Engineering",
            "location": "Hyderabad",
            "experience_required": "3-5 years",
            "skills": ["React", "JavaScript", "HTML", "CSS", "REST APIs"],
            "responsibilities": [
                "Build responsive recruiting dashboards",
                "Integrate frontend screens with Flask APIs",
                "Improve UI performance and accessibility",
            ],
            "structured_data": {
                "job_title": "Frontend React Developer",
                "industry": "Engineering",
                "location": "Hyderabad",
                "experience_range": "3-5 years",
                "required_skills": ["React", "JavaScript", "HTML", "CSS", "REST APIs"],
            },
            "raw_text": "Frontend React Developer requiring React, JavaScript, HTML, CSS, and REST API experience.",
            "file_name": "frontend-react-developer.pdf",
            "status": "Active",
        },
        {
            "title": "Python Backend Engineer",
            "department": "Platform",
            "location": "Bengaluru",
            "experience_required": "4-7 years",
            "skills": ["Python", "Flask", "MongoDB", "APIs", "Cloud"],
            "responsibilities": [
                "Develop Flask APIs",
                "Design MongoDB data models",
                "Build secure authentication flows",
            ],
            "structured_data": {
                "job_title": "Python Backend Engineer",
                "industry": "Platform",
                "location": "Bengaluru",
                "experience_range": "4-7 years",
                "required_skills": ["Python", "Flask", "MongoDB", "APIs", "Cloud"],
            },
            "raw_text": "Python Backend Engineer requiring Flask, MongoDB, APIs, and cloud experience.",
            "file_name": "python-backend-engineer.pdf",
            "status": "Active",
        },
        {
            "title": "HR Talent Acquisition Specialist",
            "department": "Human Resources",
            "location": "Remote",
            "experience_required": "2-4 years",
            "skills": ["Recruiting", "Sourcing", "Screening", "ATS", "Communication"],
            "responsibilities": [
                "Source qualified candidates",
                "Coordinate screening pipelines",
                "Maintain hiring reports",
            ],
            "structured_data": {
                "job_title": "HR Talent Acquisition Specialist",
                "industry": "Human Resources",
                "location": "Remote",
                "experience_range": "2-4 years",
                "required_skills": ["Recruiting", "Sourcing", "Screening", "ATS", "Communication"],
            },
            "raw_text": "Talent Acquisition Specialist requiring sourcing, screening, ATS, and communication skills.",
            "file_name": "talent-acquisition-specialist.pdf",
            "status": "Active",
        },
    ]


# Purpose: Implements the candidate rows backend behavior.
def _candidate_rows(jd_ids: dict[str, int]) -> list[dict]:
    return [
        {
            "name": "Aarav Sharma",
            "email": "aarav.sharma@example.com",
            "phone": "+91-90000-10001",
            "applied_roles": ["Frontend React Developer"],
            "structured_data": {
                "candidate_name": "Aarav Sharma",
                "email": "aarav.sharma@example.com",
                "phone": "+91-90000-10001",
                "skills": ["React", "JavaScript", "CSS", "Redux", "REST APIs"],
                "technical_skills": ["React", "JavaScript", "Redux"],
                "total_experience_years": 4,
                "education": {"degree": "B.Tech", "field": "Computer Science", "institution": "JNTU", "graduation_year": "2020"},
                "work_experience": [{"company": "BrightApps", "position": "Frontend Developer", "start_date": "2021", "end_date": "Present"}],
            },
            "match_score": 88,
            "status": "Selected",
            "screening_summary": "Strong React and REST API experience. Recommended for recruiter review.",
            "rejection_reason": "",
            "hiring_stage": "Recruiter Review",
            "resume_file": "aarav-sharma.pdf",
            "jd_id": jd_ids["Frontend React Developer"],
        },
        {
            "name": "Meera Iyer",
            "email": "meera.iyer@example.com",
            "phone": "+91-90000-10002",
            "applied_roles": ["Python Backend Engineer"],
            "structured_data": {
                "candidate_name": "Meera Iyer",
                "email": "meera.iyer@example.com",
                "phone": "+91-90000-10002",
                "skills": ["Python", "Flask", "MongoDB", "Docker", "AWS"],
                "technical_skills": ["Python", "Flask", "MongoDB"],
                "total_experience_years": 6,
                "education": {"degree": "MCA", "field": "Software Engineering", "institution": "PES University", "graduation_year": "2018"},
                "work_experience": [{"company": "CloudNest", "position": "Backend Engineer", "start_date": "2019", "end_date": "Present"}],
            },
            "match_score": 92,
            "status": "Selected",
            "screening_summary": "Excellent match for Flask, MongoDB, and cloud backend requirements.",
            "rejection_reason": "",
            "hiring_stage": "Technical Interview",
            "resume_file": "meera-iyer.pdf",
            "jd_id": jd_ids["Python Backend Engineer"],
        },
        {
            "name": "Rohan Gupta",
            "email": "rohan.gupta@example.com",
            "phone": "+91-90000-10003",
            "applied_roles": ["Frontend React Developer"],
            "structured_data": {
                "candidate_name": "Rohan Gupta",
                "email": "rohan.gupta@example.com",
                "phone": "+91-90000-10003",
                "skills": ["HTML", "CSS", "WordPress", "Basic JavaScript"],
                "technical_skills": ["HTML", "CSS", "WordPress"],
                "total_experience_years": 2,
                "education": {"degree": "B.Sc", "field": "IT", "institution": "Osmania University", "graduation_year": "2022"},
                "work_experience": [{"company": "SiteCraft", "position": "Web Designer", "start_date": "2022", "end_date": "Present"}],
            },
            "match_score": 54,
            "status": "Rejected",
            "screening_summary": "Limited React experience for this role.",
            "rejection_reason": "React and API integration experience is below requirement.",
            "hiring_stage": "Rejected",
            "resume_file": "rohan-gupta.pdf",
            "jd_id": jd_ids["Frontend React Developer"],
        },
        {
            "name": "Sneha Reddy",
            "email": "sneha.reddy@example.com",
            "phone": "+91-90000-10004",
            "applied_roles": ["HR Talent Acquisition Specialist"],
            "structured_data": {
                "candidate_name": "Sneha Reddy",
                "email": "sneha.reddy@example.com",
                "phone": "+91-90000-10004",
                "skills": ["Recruiting", "Sourcing", "Screening", "ATS", "Stakeholder Management"],
                "technical_skills": ["ATS", "LinkedIn Recruiter"],
                "total_experience_years": 3,
                "education": {"degree": "MBA", "field": "Human Resources", "institution": "ICFAI", "graduation_year": "2021"},
                "work_experience": [{"company": "PeopleWorks", "position": "Recruiter", "start_date": "2021", "end_date": "Present"}],
            },
            "match_score": 84,
            "status": "Selected",
            "screening_summary": "Good sourcing and screening background. Recommended for manager review.",
            "rejection_reason": "",
            "hiring_stage": "Manager Review",
            "resume_file": "sneha-reddy.pdf",
            "jd_id": jd_ids["HR Talent Acquisition Specialist"],
        },
    ]


# Purpose: Coordinates the main routine for this module.
def main() -> int:
    db.init_pool()

    if db.get_all_jds() or db.get_all_candidates():
        print("Seed skipped: database already has jobs or candidates.")
        print("Existing jobs:", len(db.get_all_jds()))
        print("Existing candidates:", len(db.get_all_candidates()))
        return 0

    jd_ids: dict[str, int] = {}
    for jd in _jd_seed_rows():
        jd_id = db.create_jd(jd)
        jd_ids[jd["title"]] = jd_id

    comparison_date = datetime.now(timezone.utc)
    candidate_count = 0
    for candidate in _candidate_rows(jd_ids):
        candidate_id = db.create_candidate(candidate)
        candidate_count += 1
        selected = candidate["status"] == "Selected"
        db.upsert_comparison(
            {
                "jd_id": candidate["jd_id"],
                "candidate_id": candidate_id,
                "match_score": candidate["match_score"],
                "status": candidate["status"],
                "strengths": candidate["structured_data"].get("skills", [])[:3],
                "gaps": [] if selected else ["React depth", "API project experience"],
                "recommendation": candidate["screening_summary"],
                "failure_reason": candidate["rejection_reason"],
                "comparison_date": comparison_date,
            }
        )

    db.log_audit(
        "Sample Data Seeded",
        "system",
        f"Seeded {len(jd_ids)} job descriptions and {candidate_count} candidates.",
        None,
    )

    print("Seed complete.")
    print("Jobs:", len(jd_ids))
    print("Candidates:", candidate_count)
    print("Login: admin / admin123")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
