# Backend file purpose: Core parsing, extraction, matching, or utility logic for screening summary.
"""
LLM-assisted screening summary generator
"""

from app.llm_extraction import llm_call
import json


# Purpose: Generates screening summary from available context.
def generate_screening_summary(jd_json: dict, resume_json: dict, screening_result: dict) -> str:
    """
    Generate a human-readable screening summary explaining the decision.
    
    Args:
        jd_json: Structured JD
        resume_json: Structured resume
        screening_result: Result from rule-based matcher
        
    Returns:
        Screening summary text
    """
    decision = "SELECTED" if screening_result.get("status") == "Selected" else "REJECTED"
    match_score = screening_result.get("match_score", 0)
    details = screening_result.get("match_details", {})
    
    prompt = f"""
You are an expert recruiter. Generate a brief, professional screening summary based on the following resume evaluation against a job description.

Job Description:
Title: {jd_json.get('job_title', 'N/A')}
Required Skills: {', '.join(jd_json.get('required_skills', []))}
Experience Required: {jd_json.get('experience_years_min', 0)} years
Location: {jd_json.get('location', 'N/A')}

Candidate Resume:
Name: {resume_json.get('candidate_name', 'N/A')}
Skills: {', '.join(resume_json.get('skills', []))}
Total Experience: {resume_json.get('total_experience_years', 0)} years
Location: {resume_json.get('current_location', 'N/A')}
Education: {resume_json.get('education', {}).get('degree', 'N/A')}

Screening Decision: {decision}
Match Score: {match_score}%

Detailed Evaluation:
{json.dumps(details, indent=2)}

Write a concise screening summary (3-4 sentences) that explains:
1. Why the candidate was {decision}
2. Key strengths or gaps
3. Most relevant or missing skills
4. Any concerns or highlights

Be professional, fair, and objective. Focus on facts from the resume and JD only.
"""
    
    summary = llm_call(prompt)
    return summary if summary and summary != "{}" else f"Candidate was {decision.lower()} with a match score of {match_score}%."


# Purpose: Generates decision reasoning from available context.
def generate_decision_reasoning(screening_result: dict) -> dict:
    """
    Extract and structure the reasoning for the screening decision.
    
    Args:
        screening_result: Result from rule-based matcher
        
    Returns:
        Structured reasoning dictionary
    """
    status = screening_result.get("status", "Rejected")
    details = screening_result.get("match_details", {})
    
    reasoning = {
        "decision": status,
        "match_score": screening_result.get("match_score", 0),
        "eligibility": {
            "passed": screening_result.get("eligible", False),
            "failures": screening_result.get("eligibility_failures", [])
        },
        "skill_evaluation": {
            "status": details.get("required_skills", {}).get("status", "N/A"),
            "details": details.get("required_skills", {})
        },
        "education_evaluation": {
            "status": details.get("education", {}).get("status", "N/A"),
            "details": details.get("education", {})
        },
        "location_evaluation": {
            "status": details.get("location", {}).get("status", "N/A"),
            "details": details.get("location", {})
        },
        "stability_evaluation": {
            "status": details.get("employment_stability", {}).get("status", "N/A"),
            "details": details.get("employment_stability", {})
        }
    }
    
    return reasoning
