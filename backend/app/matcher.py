# Backend file purpose: Core parsing, extraction, matching, or utility logic for matcher.
"""
Rule-based resume screening matcher with mandatory eligibility rules
"""

from app.utils import normalize_list, is_recent, extract_years_experience
from datetime import datetime, timedelta


# Class purpose: Defines the ScreeningRules data structure or configuration used by the backend.
class ScreeningRules:
    """
    Rule-based screening engine for resume-to-JD matching.
    Uses deterministic logic with mandatory eligibility rules.
    """
    
    # Configuration
    SKILL_RECENCY_MONTHS = 12  # Skills must be used in last 12 months
    MIN_YEARS_PER_JOB = 1  # Minimum years per job for stability
    MIN_MATCH_SCORE_SELECTED = 75  # Min score to be Selected
    
    # Purpose: Implements the init backend behavior.
    def __init__(self, jd_json: dict, resume_json: dict):
        """
        Initialize matcher with JD and resume JSONs.
        
        Args:
            jd_json: Structured job description
            resume_json: Structured resume
        """
        self.jd = jd_json
        self.resume = resume_json
        self.eligibility_failures = []
        self.match_details = {}
    
    # Purpose: Implements the screen backend behavior.
    def screen(self) -> dict:
        """
        Run the complete screening logic.
        
        Returns:
            Screening result with score, status, and details
        """
        # Step 1: Check mandatory eligibility rules
        if not self._check_mandatory_rules():
            return {
                "eligible": False,
                "match_score": 0,
                "status": "Rejected",
                "eligibility_failures": self.eligibility_failures,
                "match_details": self.match_details,
                "failure_reason": "; ".join(self.eligibility_failures)
            }
        
        # Step 2: Calculate match score
        match_score = self._calculate_match_score()
        
        # Step 3: Determine selection status
        status = "Selected" if match_score >= self.MIN_MATCH_SCORE_SELECTED else "Rejected"
        
        return {
            "eligible": True,
            "match_score": int(match_score),
            "status": status,
            "eligibility_failures": [],
            "match_details": self.match_details,
            "failure_reason": None
        }
    
    # Purpose: Implements the check mandatory rules backend behavior.
    def _check_mandatory_rules(self) -> bool:
        """
        Check all mandatory eligibility rules.
        
        Returns:
            True if all rules pass, False otherwise
        """
        rules_pass = True
        
        # Rule 1: Required skills with recency
        if not self._check_required_skills_recency():
            rules_pass = False
        
        # Rule 2: Education requirement
        if not self._check_education():
            rules_pass = False
        
        # Rule 3: Location / relocation
        if not self._check_location():
            rules_pass = False
        
        # Rule 4: Employment stability
        if not self._check_employment_stability():
            rules_pass = False
        
        return rules_pass
    
    # Purpose: Implements the check required skills recency backend behavior.
    def _check_required_skills_recency(self) -> bool:
        """
        Check if candidate has all required skills with recent usage.
        """
        required_skills = normalize_list(self.jd.get("required_skills", []))
        
        if not required_skills:
            self.match_details["required_skills"] = {"status": "N/A"}
            return True
        
        resume_skills = normalize_list(self.resume.get("skills", []))
        resume_work_exp = self.resume.get("work_experience", [])
        
        # Build a map of skills to their most recent usage date
        skill_dates = {}
        for skill in resume_skills:
            skill_lower = skill.lower()
            for exp in resume_work_exp:
                if skill_lower in exp.get("responsibilities", []):
                    end_date = exp.get("end_date", "")
                    if end_date:
                        skill_dates[skill] = end_date
                        break
        
        # Check each required skill
        missing_or_old = []
        for req_skill in required_skills:
            req_skill_lower = req_skill.lower()
            
            # Find matching skill in resume
            matched_skill = None
            for resume_skill in resume_skills:
                if req_skill_lower in resume_skill.lower() or resume_skill.lower() in req_skill_lower:
                    matched_skill = resume_skill
                    break
            
            if not matched_skill:
                missing_or_old.append(f"{req_skill} (Missing)")
                continue
            
            # Check recency
            last_used = skill_dates.get(matched_skill, "")
            if last_used and not is_recent(last_used, self.SKILL_RECENCY_MONTHS):
                missing_or_old.append(f"{req_skill} (Not recent)")
        
        self.match_details["required_skills"] = {
            "status": "PASS" if not missing_or_old else "FAIL",
            "matched": len(required_skills) - len(missing_or_old),
            "total": len(required_skills),
            "missing_or_old": missing_or_old
        }
        
        if missing_or_old:
            self.eligibility_failures.append(f"Missing or outdated required skills: {', '.join(missing_or_old)}")
            return False
        
        return True
    
    # Purpose: Implements the check education backend behavior.
    def _check_education(self) -> bool:
        """
        Check if candidate has ANY graduation/degree (B.Tech, B.S., Master's, etc.).
        Accepts any type of graduation - no specific degree type required.
        """
        education = self.resume.get("education", {})
        degree = education.get("degree", "").lower()
        field = education.get("field", "").lower()
        graduation_year = education.get("graduation_year", "")
        
        # Accept ANY graduation - B.Tech, B.S., M.Tech, Master's, MBA, PhD, Diploma, etc.
        # Just needs to have some graduation/degree info
        acceptable_keywords = [
            "bachelor", "b.tech", "b.s", "b.a", "beng", "bsc",
            "master", "m.tech", "m.s", "m.a", "mba", "meng", "msc", 
            "phd", "doctorate",
            "diploma", "degree", "graduate", "graduated",
            "engineering", "science", "arts", "commerce"
        ]
        
        # Check if degree or field contains any graduation indicator
        has_graduation = any(keyword in degree or keyword in field for keyword in acceptable_keywords) if degree or field else False
        
        self.match_details["education"] = {
            "status": "PASS" if has_graduation else "FAIL",
            "degree": degree if degree else "(Not specified)",
            "field": field if field else "(Not specified)",
            "graduation_year": graduation_year if graduation_year else "(Not specified)"
        }
        
        if not has_graduation:
            self.eligibility_failures.append("Education requirement not met (No graduation/degree found)")
            return False
        
        return True
    
    # Purpose: Implements the check location backend behavior.
    def _check_location(self) -> bool:
        """
        Check if candidate is in required location or willing to relocate.
        """
        required_location = self.jd.get("location", "").lower().strip()
        candidate_location = self.resume.get("current_location", "").lower().strip()
        relocation_willing = self.resume.get("relocation_willing", False)
        
        # If no location specified in JD, pass
        if not required_location:
            self.match_details["location"] = {"status": "N/A"}
            return True
        
        # Check if candidate is in the location
        location_match = required_location in candidate_location or candidate_location in required_location
        
        self.match_details["location"] = {
            "status": "PASS" if (location_match or relocation_willing) else "FAIL",
            "required": required_location,
            "candidate_location": candidate_location if candidate_location else "(Not specified)",
            "relocation_willing": relocation_willing
        }
        
        if not location_match and not relocation_willing:
            self.eligibility_failures.append(f"Location mismatch: requires {required_location}, candidate is in {candidate_location or 'unknown location'} and not willing to relocate")
            return False
        
        return True
    
    # Purpose: Implements the check employment stability backend behavior.
    def _check_employment_stability(self) -> bool:
        """
        Check if candidate demonstrates job stability (min 1 year per job).
        """
        work_experience = self.resume.get("work_experience", [])
        
        if not work_experience:
            self.match_details["employment_stability"] = {
                "status": "FAIL",
                "reason": "No work experience found"
            }
            self.eligibility_failures.append("No work experience found")
            return False
        
        unstable_jobs = []
        
        for exp in work_experience:
            start_date = exp.get("start_date", "")
            end_date = exp.get("end_date", "Present")
            company = exp.get("company", "Unknown")
            
            if not start_date or not end_date:
                continue
            
            # Calculate years in this job
            try:
                start_mm, start_yy = start_date.split("/")
                start = datetime(int("20" + start_yy), int(start_mm), 1)
                
                if end_date == "Present":
                    end = datetime.now()
                else:
                    end_mm, end_yy = end_date.split("/")
                    end = datetime(int("20" + end_yy), int(end_mm), 1)
                
                years_in_job = (end - start).days / 365.25
                
                if years_in_job < self.MIN_YEARS_PER_JOB:
                    unstable_jobs.append(f"{company} ({years_in_job:.1f} years)")
            except (ValueError, AttributeError):
                continue
        
        self.match_details["employment_stability"] = {
            "status": "FAIL" if unstable_jobs else "PASS",
            "total_jobs": len(work_experience),
            "unstable_jobs": unstable_jobs
        }
        
        if unstable_jobs:
            self.eligibility_failures.append(f"Employment instability detected: {', '.join(unstable_jobs)}")
            return False
        
        return True
    
    # Purpose: Implements the calculate match score backend behavior.
    def _calculate_match_score(self) -> float:
        """
        Calculate match score based on predefined weights.
        Only called if candidate passes all mandatory rules.
        
        Returns:
            Match score (0-100)
        """
        score = 0.0
        
        # 1. Skill match (40%)
        skill_score = self._score_skills() * 0.40
        score += skill_score
        
        # 2. Experience alignment (30%)
        exp_score = self._score_experience() * 0.30
        score += exp_score
        
        # 3. Role relevance (20%)
        role_score = self._score_role_relevance() * 0.20
        score += role_score
        
        # 4. Employment stability (10%)
        stability_score = self._score_stability() * 0.10
        score += stability_score
        
        self.match_details["scoring"] = {
            "skill_score": int(skill_score),
            "experience_score": int(exp_score),
            "role_relevance_score": int(role_score),
            "stability_score": int(stability_score),
            "total_score": int(score)
        }
        
        return score
    
    # Purpose: Implements the score skills backend behavior.
    def _score_skills(self) -> float:
        """Score based on skill match."""
        required_skills = normalize_list(self.jd.get("required_skills", []))
        preferred_skills = normalize_list(self.jd.get("preferred_skills", []))
        resume_skills = normalize_list(self.resume.get("skills", []))
        
        if not required_skills and not preferred_skills:
            return 100.0
        
        # Calculate required skill matches
        required_matches = sum(
            1 for req in required_skills
            if any(req.lower() in res.lower() or res.lower() in req.lower() for res in resume_skills)
        )
        required_score = (required_matches / len(required_skills)) * 100 if required_skills else 0
        
        # Calculate preferred skill matches
        preferred_matches = sum(
            1 for pref in preferred_skills
            if any(pref.lower() in res.lower() or res.lower() in pref.lower() for res in resume_skills)
        )
        preferred_score = (preferred_matches / len(preferred_skills)) * 100 if preferred_skills else 0
        
        # 80% weight on required, 20% on preferred
        return (required_score * 0.8) + (preferred_score * 0.2)
    
    # Purpose: Implements the score experience backend behavior.
    def _score_experience(self) -> float:
        """Score based on experience alignment."""
        required_exp = self.jd.get("experience_years_min", 0)
        candidate_exp = self.resume.get("total_experience_years", 0)
        
        if required_exp == 0:
            return 100.0
        
        # Candidate has enough experience
        if candidate_exp >= required_exp:
            return 100.0
        
        # Partial credit for partial experience
        score = (candidate_exp / required_exp) * 100
        return min(score, 100.0)
    
    # Purpose: Implements the score role relevance backend behavior.
    def _score_role_relevance(self) -> float:
        """Score based on role relevance (past positions)."""
        jd_title = self.jd.get("job_title", "").lower()
        work_exp = self.resume.get("work_experience", [])
        
        if not jd_title or not work_exp:
            return 75.0  # Neutral score
        
        # Count roles that match the JD title
        matching_roles = sum(
            1 for exp in work_exp
            if jd_title in exp.get("position", "").lower() or
               any(word in exp.get("position", "").lower() for word in jd_title.split())
        )
        
        if matching_roles > 0:
            return 100.0
        
        return 60.0  # Lower score if no matching previous roles
    
    # Purpose: Implements the score stability backend behavior.
    def _score_stability(self) -> float:
        """Score based on employment stability."""
        work_experience = self.resume.get("work_experience", [])
        
        if not work_experience:
            return 0.0
        
        # Calculate average tenure
        total_years = 0.0
        for exp in work_experience:
            start_date = exp.get("start_date", "")
            end_date = exp.get("end_date", "Present")
            
            if not start_date:
                continue
            
            try:
                start_mm, start_yy = start_date.split("/")
                start = datetime(int("20" + start_yy), int(start_mm), 1)
                
                if end_date == "Present":
                    end = datetime.now()
                else:
                    end_mm, end_yy = end_date.split("/")
                    end = datetime(int("20" + end_yy), int(end_mm), 1)
                
                total_years += (end - start).days / 365.25
            except (ValueError, AttributeError):
                continue
        
        # Average tenure per job
        avg_tenure = total_years / len(work_experience) if work_experience else 0
        
        # Score: 100 if avg >= 3 years, scale down from there
        if avg_tenure >= 3:
            return 100.0
        elif avg_tenure >= 1:
            return (avg_tenure / 3) * 100
        else:
            return 50.0
