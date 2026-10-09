"""JD-only generation validation. No candidate data enters this module."""
import json
import re
import random
from difflib import SequenceMatcher
from collections import Counter
from assessment.models import TOTAL_GENERATED_QUESTIONS, MCQ_COUNT, CODING_COUNT, SQL_COUNT, MCQ_MEDIUM_COUNT, MCQ_HARD_COUNT

_rng = random.SystemRandom()

METADATA = ("difficulty", "scenario_type", "explanation", "evaluation_focus", "jd_requirement")

def normalized_jd(jd):
    structured = jd.get("structured_data") or {}
    if isinstance(structured, str):
        try:
            structured = json.loads(structured)
        except (ValueError, TypeError):
            structured = {}
    return {
        "posted_jd_text": jd.get("raw_text") or "",
        "job_title": jd.get("title") or "",
        "experience_required": jd.get("experience_required") or "",
        "skills": jd.get("skills") or [],
        "responsibilities": jd.get("responsibilities") or [],
        "structured_requirements": structured if isinstance(structured, dict) else {},
    }

def _text(value):
    return " ".join(str(value).lower().split())

def _source_values(value):
    if isinstance(value, dict):
        return " ".join(_source_values(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_source_values(v) for v in value)
    return str(value or "")

def requirement_catalog(jd):
    """Number original JD fragments so the model need not retype evidence."""
    fragments = []
    def collect(value):
        if isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
        elif isinstance(value, str):
            for line in value.splitlines():
                line = line.strip()
                if len(line) >= 4 and line not in fragments:
                    fragments.append(line)
    collect(jd)
    return {f"R{i+1:03d}": line for i, line in enumerate(fragments)}


def shuffle_mcq_options(rows, rng=None):
    """Place each MCQ's correct option at an independently random position.

    Models tend to list the best answer first, so the generated order is never
    trusted. Target slots are a shuffled, near-even spread of A-D (no fixed
    cycle, no long same-letter run); the distractors are shuffled around it.
    correct_answer holds the option text, so it moves with its option.
    """
    rng = rng or _rng
    mcqs = [row for row in rows if row["question_type"] == "mcq"]
    slots = [i % 4 for i in range(len(mcqs))]
    rng.shuffle(slots)
    for row, slot in zip(mcqs, slots):
        correct = row["correct_answer"]
        distractors = [option for option in row["options"] if option != correct]
        rng.shuffle(distractors)
        row["options"] = distractors[:slot] + [correct] + distractors[slot:]
        if row["options"].count(correct) != 1 or len(row["options"]) != 4:
            raise ValueError("MCQ options lost their correct-answer mapping while shuffling.")
    return rows


def validate_exam(exam, jd, total=TOTAL_GENERATED_QUESTIONS, previous_questions=()):
    if not isinstance(exam, dict):
        raise ValueError("Exam must be a JSON object.")
    items = exam.get("questions")
    if not isinstance(items, list) or len(items) != total or exam.get("total_questions") != total:
        raise ValueError(f"Exam must contain exactly {total} questions.")
    source = _text(_source_values(jd))
    if not exam.get("job_title") or not exam.get("experience_required") or not isinstance(exam.get("skills_covered"), list) or not exam["skills_covered"]:
        raise ValueError("Exam must include JD title, experience and skills covered.")
    for key in ("exam_title", "job_title", "experience_required"):
        if not isinstance(exam.get(key), str) or not exam[key].strip():
            raise ValueError(f"{key} must be nonempty text.")
    for skill in exam["skills_covered"]:
        if not _text(skill) or _text(skill) not in source:
            raise ValueError("skills_covered must come from the JD.")
    seen = [_text(t) for t in previous_questions]
    rows = []
    difficulties = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError("Each question must be an object.")
        text = str(item.get("question") or "").strip()
        qtype = str(item.get("question_type") or "").lower()
        if qtype not in {"mcq", "coding", "sql"}:
            raise ValueError("Unsupported question type.")
        if len(text.split()) < 15 or re.match(r"^(what is|what are|define|name|list|which tool is commonly)\b", text, re.I):
            raise ValueError(f"Q{index+1} must describe a practical scenario.")
        for key in METADATA:
            if not item.get(key):
                raise ValueError(f"Q{index+1} requires {key}.")
        for key in ("difficulty", "scenario_type", "explanation", "jd_requirement"):
            if not isinstance(item[key], str) or not item[key].strip():
                raise ValueError(f"Q{index+1} requires a text {key}.")
        if item["difficulty"] not in {"Easy", "Medium", "Hard"}:
            raise ValueError("Difficulty must be Easy, Medium or Hard.")
        difficulties.add(item["difficulty"])
        if not isinstance(item["evaluation_focus"], list) or not all(isinstance(v, str) and v.strip() for v in item["evaluation_focus"]):
            raise ValueError("evaluation_focus must be a nonempty list of strings.")
        skill = str(item.get("skill") or "").strip()
        evidence = str(item["jd_requirement"]).strip()
        if not skill or _text(skill) not in source or len(evidence) < 4 or _text(evidence) not in source:
            raise ValueError(f"Q{index+1}: skill {skill!r} or JD excerpt {evidence!r} is not verbatim in the JD. Use a numbered requirement and copy its exact skill wording.")
        canonical = _text(text)
        if any(canonical == other or SequenceMatcher(None, canonical, other).ratio() >= .88 for other in seen):
            raise ValueError(f"Q{index+1} repeats an existing question.")
        seen.append(canonical)
        answer = str(item.get("correct_answer") or "").strip()
        options = item.get("options") or []
        if not answer or not isinstance(options, list):
            raise ValueError("A correct answer and valid options are required.")
        # Some models return a letter instead of option text. Convert only an
        # unambiguous label or whitespace-equivalent answer; never guess content.
        if qtype == "mcq" and len(options) == 4 and answer not in options:
            matching = [v for v in options if isinstance(v, str) and _text(v) == _text(answer)]
            label = re.fullmatch(r"(?:option\s+)?([A-D])[.)]?", answer, re.I)
            if len(matching) == 1:
                answer = matching[0]
            elif label:
                answer = options[ord(label.group(1).upper()) - ord("A")]
        if qtype == "mcq" and (len(options) != 4 or not all(isinstance(v, str) and v.strip() for v in options) or len({_text(v) for v in options}) != 4 or answer not in options):
            raise ValueError(f"Q{index+1}: MCQ requires four distinct options and correct_answer must be the full text of exactly one option.")
        points = int(item.get("points") or (5 if qtype == "mcq" else 15))
        if not 1 <= points <= 100:
            raise ValueError("Question points must be between 1 and 100.")
        rows.append({"question_text": text, "question_type": qtype, "options": options if qtype == "mcq" else [],
                     "correct_answer": answer, "starter_code": str(item.get("starter_code") or ""),
                     "points": points, "skill_tag": skill, "sort_order": index,
                     "question_id": f"Q{index+1:03d}", **{k: item[k] for k in METADATA}})
    counts = Counter(q["question_type"] for q in rows)
    if counts != {"mcq": MCQ_COUNT, "coding": CODING_COUNT, "sql": SQL_COUNT}:
        raise ValueError("Every exam must contain exactly 10 MCQs, 2 coding questions and 2 SQL questions.")
    mcq_levels = Counter(q["difficulty"] for q in rows if q["question_type"] == "mcq")
    if mcq_levels != {"Medium": MCQ_MEDIUM_COUNT, "Hard": MCQ_HARD_COUNT}:
        raise ValueError("The 10 MCQs must contain 4 moderate (Medium) and 6 Hard scenarios; no Easy questions.")
    if any(q["difficulty"] != "Medium" for q in rows if q["question_type"] in {"coding", "sql"}):
        raise ValueError("Both coding and both SQL questions must be moderate (Medium).")
    order = {"mcq": 0, "coding": 1, "sql": 2}
    rows.sort(key=lambda q: order[q["question_type"]])
    for index, row in enumerate(rows):
        row["sort_order"] = index
        row["question_id"] = f"Q{index+1:03d}"
    return shuffle_mcq_options(rows)
