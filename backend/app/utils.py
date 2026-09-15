# Backend file purpose: Core parsing, extraction, matching, or utility logic for utils.
"""
Text cleaning and normalization utilities
"""

import re
from datetime import datetime, timedelta


IGNORE_PATTERNS = [
    r"DECLARATION",
    r"I hereby declare",
    r"Signature",
    r"Page \d+",
    r"^---",
    r"^\*\*\*",
]


# Purpose: Cleans and normalizes resume text values.
def clean_resume_text(text: str) -> str:
    """
    Clean and normalize resume text.
    
    Args:
        text: Raw resume text
        
    Returns:
        Cleaned text
    """
    lines = []
    for line in text.splitlines():
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
        
        # Skip lines matching ignore patterns
        if any(re.search(p, line, re.I) for p in IGNORE_PATTERNS):
            continue
        
        # Normalize whitespace
        line = re.sub(r"\s{2,}", " ", line)
        lines.append(line)
    
    return "\n".join(lines)


# Purpose: Cleans and normalizes jd text values.
def clean_jd_text(text: str) -> str:
    """
    Clean and normalize JD text.
    
    Args:
        text: Raw JD text
        
    Returns:
        Cleaned text
    """
    return clean_resume_text(text)


# Purpose: Normalizes list into the app's expected format.
def normalize_list(val) -> list:
    """
    Normalize various input types to a list of strings.
    
    Args:
        val: Value to normalize (string, list, etc.)
        
    Returns:
        Normalized list
    """
    if not val:
        return []
    if isinstance(val, str):
        return [v.strip() for v in val.split(",") if v.strip()]
    if isinstance(val, list):
        return [str(v).strip() for v in val if v and str(v).strip()]
    return []


# Purpose: Normalizes date into the app's expected format.
def normalize_date(date_str: str) -> str:
    """
    Normalize date string to MM/YYYY format.
    
    Args:
        date_str: Date string in various formats
        
    Returns:
        Normalized date (MM/YYYY) or 'Present' or empty string
    """
    if not date_str:
        return ""
    
    date_lower = date_str.lower().strip()
    
    # Check for "Present" or similar
    if any(word in date_lower for word in ["present", "current", "ongoing"]):
        return "Present"
    
    # Try MM/YYYY or MM-YYYY format
    match = re.search(r"(0?[1-9]|1[0-2])[/\-](\d{2,4})", date_str)
    if match:
        mm, yy = match.groups()
        return f"{int(mm):02d}/{yy[-2:]}"
    
    # Try just year format
    year_match = re.search(r"(19|20)\d{2}", date_str)
    if year_match:
        year = year_match.group()
        return f"01/{year[-2:]}"
    
    return ""


# Purpose: Implements the calculate years of experience backend behavior.
def calculate_years_of_experience(years: int) -> str:
    """
    Convert years count to human-readable format.
    
    Args:
        years: Number of years
        
    Returns:
        Formatted string
    """
    if years < 1:
        months = int(years * 12)
        return f"{months} months"
    elif years == 1:
        return "1 year"
    else:
        return f"{years} years"


# Purpose: Checks whether recent is true.
def is_recent(date_str: str, months: int = 12) -> bool:
    """
    Check if a date is within the last N months.
    
    Args:
        date_str: Date in MM/YYYY format
        months: Number of months to check back (default 12)
        
    Returns:
        True if date is within the specified months
    """
    if not date_str or date_str == "":
        return False
    
    if date_str == "Present":
        return True
    
    try:
        # Parse MM/YYYY format
        mm, yy = date_str.split("/")
        year = int("20" + yy) if len(yy) == 2 else int(yy)
        month = int(mm)
        
        # Create date object (use last day of the month)
        if month == 12:
            date_obj = datetime(year + 1, 1, 1)
        else:
            date_obj = datetime(year, month + 1, 1)
        
        # Check if within N months
        cutoff_date = datetime.now() - timedelta(days=months * 30)
        return date_obj >= cutoff_date
    except (ValueError, AttributeError):
        return False


# Purpose: Extracts years experience from input data.
def extract_years_experience(exp_str: str) -> float:
    """
    Extract years of experience from a string.
    
    Args:
        exp_str: Experience string (e.g., "5+ years", "3-5 years")
        
    Returns:
        Extracted years as float
    """
    if not exp_str:
        return 0.0
    
    # Try to find a number
    match = re.search(r"(\d+(?:\.\d+)?)", exp_str)
    if match:
        return float(match.group(1))
    
    return 0.0
