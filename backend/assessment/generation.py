"""JD-only generation validation. No candidate data enters this module."""
import json
import re
import random
from difflib import SequenceMatcher
from collections import Counter
from assessment.code_execution.preparation import validate_test_fields
from assessment.models import CODING_COUNT, MCQ_BATCH_SIZE, MCQ_COUNT, MCQ_HARD_COUNT, MCQ_MEDIUM_COUNT, SQL_COUNT

_rng = random.SystemRandom()

# The complete exam: question counts per type and the MCQ difficulty split.
FULL_MIX = {"mcq": MCQ_COUNT, "coding": CODING_COUNT, "sql": SQL_COUNT,
            "mcq_medium": MCQ_MEDIUM_COUNT, "mcq_hard": MCQ_HARD_COUNT}

# Each parallel MCQ batch takes a different angle on the JD so batches do not overlap.
MCQ_BATCH_FOCUS = (
    "troubleshooting, debugging and root-cause analysis of failures in the JD's systems and responsibilities",
    "design, architecture, scalability, performance and trade-off decisions within the JD's scope",
    "implementation practice, testing, security, data quality, deployment and day-to-day operations from the JD",
)
DUPLICATE_RATIO = .88
# A coding question must ask for a program, not a choice between approaches.
CODING_TASK = re.compile(r"\b(write|implement|build|develop|create|code)\b", re.I)

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


def mix_total(mix):
    return mix["mcq"] + mix["coding"] + mix["sql"]


def _split(total, parts):
    return [total // parts + (1 if i < total % parts else 0) for i in range(parts)]


def generation_sections(mix=FULL_MIX, batch_size=MCQ_BATCH_SIZE):
    """Split the exam into independently generated sections: coding+SQL, then MCQ batches."""
    sections = []
    if mix["coding"] or mix["sql"]:
        sections.append({"key": "coding_sql", "mcq": 0, "coding": mix["coding"], "sql": mix["sql"],
                         "mcq_medium": 0, "mcq_hard": 0, "focus": ""})
    batches = -(-mix["mcq"] // batch_size) if mix["mcq"] else 0
    for i, (size, medium) in enumerate(zip(_split(mix["mcq"], batches), _split(mix["mcq_medium"], batches))):
        sections.append({"key": f"mcq_{i + 1}", "mcq": size, "coding": 0, "sql": 0, "mcq_medium": medium,
                         "mcq_hard": size - medium, "focus": MCQ_BATCH_FOCUS[i % len(MCQ_BATCH_FOCUS)]})
    for section in sections:
        section["total"] = mix_total(section)
        section["optional_max"] = max(1, -(-section["total"] // 7))
    return sections


def is_duplicate(text, other):
    text, other = _text(text), _text(other)
    return bool(other) and (text == other or SequenceMatcher(None, text, other).ratio() >= DUPLICATE_RATIO)


def find_duplicate(rows):
    """Index pair (earlier, later) of the first two questions that repeat each other, or None."""
    for later in range(1, len(rows)):
        for earlier in range(later):
            if is_duplicate(rows[later]["question_text"], rows[earlier]["question_text"]):
                return earlier, later
    return None


def validate_exam(exam, jd, total=None, previous_questions=(), require_tests=True, mix=None):
    """Validate one generated exam (or one section of it, given its own mix) and return question rows."""
    mix = mix or FULL_MIX
    total = mix_total(mix) if total is None else total
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
        if any(is_duplicate(text, other) for other in seen):
            raise ValueError(f"Q{index+1} repeats an existing question.")
        seen.append(_text(text))
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
        if qtype == "coding" and not CODING_TASK.search(text):
            raise ValueError(f"Q{index+1} is a coding question but asks for a decision instead of a program. "
                             "State the task explicitly: 'Write a program that reads ... and prints ...'.")
        executable = {}
        if qtype in {"coding", "sql"}:
            try:
                executable = validate_test_fields(item, qtype, f"Q{index+1}")
            except ValueError:
                if require_tests:
                    raise
                # Last attempt: keep the question; it is graded by AI against its reference answer.
        points = int(item.get("points") or (5 if qtype == "mcq" else 15))
        if not 1 <= points <= 100:
            raise ValueError("Question points must be between 1 and 100.")
        rows.append({"question_text": text, "question_type": qtype, "options": options if qtype == "mcq" else [],
                     "correct_answer": answer, "starter_code": str(item.get("starter_code") or ""),
                     "points": points, "skill_tag": skill, "sort_order": index,
                     "question_id": f"Q{index+1:03d}", **{k: item[k] for k in METADATA}, **executable})
    counts = Counter(q["question_type"] for q in rows)
    if counts != Counter({key: mix[key] for key in ("mcq", "coding", "sql") if mix[key]}):
        raise ValueError(f"The exam must contain exactly {mix['mcq']} MCQs, {mix['coding']} coding questions "
                         f"and {mix['sql']} SQL questions.")
    mcq_levels = Counter(q["difficulty"] for q in rows if q["question_type"] == "mcq")
    if mcq_levels != Counter({k: v for k, v in (("Medium", mix["mcq_medium"]), ("Hard", mix["mcq_hard"])) if v}):
        raise ValueError(f"The {mix['mcq']} MCQs must contain {mix['mcq_medium']} moderate (Medium) and "
                         f"{mix['mcq_hard']} Hard scenarios; no Easy questions.")
    if any(q["difficulty"] != "Medium" for q in rows if q["question_type"] in {"coding", "sql"}):
        raise ValueError("Both coding and both SQL questions must be moderate (Medium).")
    order = {"mcq": 0, "coding": 1, "sql": 2}
    rows.sort(key=lambda q: order[q["question_type"]])
    for index, row in enumerate(rows):
        row["sort_order"] = index
        row["question_id"] = f"Q{index+1:03d}"
    return shuffle_mcq_options(rows)
