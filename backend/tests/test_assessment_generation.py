"""Regression coverage for JD-only generation and rejection paths; no external API calls."""
import copy
import json
import re
import sys
import threading
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assessment.generation import generation_sections, normalized_jd, requirement_catalog, validate_exam
from assessment.utilities import candidate_question_payload, recruiter_question_payload
from services import assessment_service as service

JD = {"title": "Python Developer", "experience_required": "3-5 years", "skills": ["Python"],
      "raw_text": "Python Developer. 3-5 years. Maintain Python services and investigate service failures.",
      "structured_data": {"required_skills": ["Python"]}}
SCENARIOS = [
    "A Python service rejects a valid customer request because an optional field is missing. Choose the safest change to accept this input while preserving validation.",
    "During maintenance, a Python worker gradually consumes more memory over several hours and stops processing tasks. Which investigation would best isolate the growing allocation?",
    "Your team must replace a heavily used Python service component while existing clients depend on its behavior. How should you plan compatibility checks, rollout and recovery?",
    "Requests with accented customer names are rejected after a text parsing change although ordinary names still pass validation. What should you inspect before changing the parser?",
    "Two services calculate different invoice totals for identical decimal inputs during reconciliation. How would you identify the numeric representation issue and prevent rounding drift?",
    "An asynchronous task acknowledges messages before transaction commits and customer records vanish following a restart. Which ordering change would preserve reliable processing without creating duplicates?",
    "Your application returns another user's cached report when simultaneous queries use similar filters. What cache isolation design would prevent cross-user results while retaining useful reuse?",
    "A database migration removes a field still read by older clients during a rolling deployment. How should you sequence compatibility changes and verify safe rollback?",
    "An endpoint becomes unresponsive only when two background workers acquire shared locks in opposite order. Which concurrency design resolves the deadlock without sacrificing transaction consistency?",
    "A large import produces duplicate records after a partial retry even though each source row has a stable identifier. What strategy guarantees idempotence across interrupted batches?",
    "Implement a Python function that preserves the order of unique request identifiers while rejecting missing values. Input contains repeated strings and empty entries; show normal and empty cases.",
    "Write a Python parser for customer transaction records that collects invalid entries separately and continues processing the remaining rows. Specify output for malformed numbers and an empty batch.",
    "A reporting table contains multiple status updates for each customer request with different timestamps. Write SQL to return only the latest update, resolving equal timestamps with a unique identifier.",
    "Operations needs a SQL report counting completed requests for every registered customer including customers with none. Given customer and request schemas, explain the join and filtering needed.",
]

# Each MCQ batch adds its own context, so the 30 MCQs stay distinct (the duplicate check compares whole texts).
CONTEXTS = [
    "This happened in the nightly settlement batch that finance reconciles before markets open each morning.",
    "The affected component is the public partner gateway, which several external integrators call at peak hours.",
    "It was reported by the support desk after a regional rollout reached roughly half of active enterprise tenants.",
]
MCQ_TEXTS = [f"{SCENARIOS[i]} {CONTEXTS[b]}" for b in range(3) for i in range(10)]
TECHNICAL = SCENARIOS[10:14]
TOTAL = len(MCQ_TEXTS) + len(TECHNICAL)  # 30 MCQs + 2 coding + 2 SQL
CODING, SQL = TOTAL - 4, TOTAL - 2  # indexes of the first coding and first SQL question

CODING_TESTS = [{"input": f"{n}\n", "expected_output": f"{n * 2}\n", "hidden": n > 2} for n in range(1, 7)]
SQL_SCHEMA = "CREATE TABLE requests (id INTEGER, customer_id INTEGER, status TEXT, updated_at TEXT);"
SQL_TESTS = [{"setup_sql": f"INSERT INTO requests VALUES ({n}, 1, 'done', '2026-01-0{n}'), ({n + 10}, 2, 'open', '2026-02-0{n}');",
              "hidden": n > 2} for n in range(1, 6)]
SQL_REFERENCE = "SELECT customer_id, MAX(updated_at) FROM requests GROUP BY customer_id"
REVIEW_OK = '{"valid": true, "issues": []}'
SECTION_KEYS = ("coding_sql", "mcq_1", "mcq_2", "mcq_3")


def _question(i, text, qtype):
    return {"question_id": f"Q{i+1:03d}", "question": text, "question_type": qtype,
            # Each batch of ten MCQs: 4 Medium then 6 Hard. Coding and SQL are Medium.
            "difficulty": "Hard" if qtype == "MCQ" and i % 10 >= 4 else "Medium", "skill": "Python",
            "jd_requirement": "Maintain Python services", "scenario_type": "Troubleshooting",
            "options": ["A", "B", "C", "D"] if qtype == "MCQ" else [], "correct_answer": "B",
            "explanation": "B addresses the stated failure with validation.",
            "evaluation_focus": ["Practical application"]}


def exam():
    """The complete model exam: MCQs at 0..29, coding at CODING..CODING+1, SQL at SQL..SQL+1."""
    questions = [_question(i, text, "MCQ") for i, text in enumerate(MCQ_TEXTS)]
    questions += [_question(len(questions) + i, text, "CODING" if i < 2 else "SQL") for i, text in enumerate(TECHNICAL)]
    for question in questions[CODING:SQL]:
        question.update(correct_answer="print(int(input()) * 2)", test_cases=copy.deepcopy(CODING_TESTS),
                        input_format="One integer n", output_format="2 * n", default_language="python")
    for question in questions[SQL:]:
        question.update(correct_answer=SQL_REFERENCE, sql_schema=SQL_SCHEMA, test_cases=copy.deepcopy(SQL_TESTS))
    return {"exam_title": "JD-Based Assessment", "job_title": "Python Developer", "experience_required": "3-5 years",
            "total_questions": TOTAL, "skills_covered": ["Python"], "questions": questions}


def section_exam(key, data=None):
    """What the model returns for one parallel section (see assessment.generation.generation_sections)."""
    data = copy.deepcopy(data or exam())
    if key == "coding_sql":
        questions = data["questions"][CODING:]
    else:
        batch = int(key.rsplit("_", 1)[1]) - 1
        questions = data["questions"][batch * 10:(batch + 1) * 10]
    for i, question in enumerate(questions):
        question["question_id"] = f"Q{i+1:03d}"
    return {**data, "total_questions": len(questions), "questions": questions}


def section_of(prompt):
    match = re.search(r"Section key: (\w+)", prompt)
    return match.group(1) if match else None


class FakeExamLLM:
    """Answers section prompts by key (they run in parallel, so call order is not fixed) and review prompts in order."""

    def __init__(self, reviews=(REVIEW_OK,), sections=None):
        self.reviews = list(reviews)
        self.sections = sections or {}  # key -> raw responses used before the default valid section
        self.prompts = []
        self.lock = threading.Lock()

    def invoke(self, prompt, temperature=None):
        with self.lock:
            self.prompts.append(prompt)
            key = section_of(prompt)
            if key is None:
                return self.reviews.pop(0) if len(self.reviews) > 1 else self.reviews[0]
            queued = self.sections.get(key)
            if queued:
                return queued.pop(0)
        return json.dumps(section_exam(key))

    def section_prompts(self, key):
        return [p for p in self.prompts if section_of(p) == key]

    def review_prompts(self):
        return [p for p in self.prompts if section_of(p) is None]


class GenerationTests(unittest.TestCase):
    def test_complete_jd_does_not_mutate_structured_data(self):
        before = copy.deepcopy(JD)
        context = normalized_jd(JD)
        self.assertIn("service failures", context["posted_jd_text"])
        self.assertEqual(JD, before)

    def test_valid_exam_preserves_grounding_and_metadata(self):
        rows = validate_exam(exam(), normalized_jd(JD), total=TOTAL)
        self.assertEqual(len(rows), 34)
        self.assertEqual(rows[0]["jd_requirement"], "Maintain Python services")
        self.assertEqual(rows[6]["difficulty"], "Hard")

    def test_default_mix_is_30_mcqs_2_coding_2_sql(self):
        rows = validate_exam(exam(), normalized_jd(JD))
        self.assertEqual(Counter(r["question_type"] for r in rows), {"mcq": 30, "coding": 2, "sql": 2})
        self.assertEqual(Counter(r["difficulty"] for r in rows if r["question_type"] == "mcq"), {"Medium": 12, "Hard": 18})
        self.assertEqual([r["question_id"] for r in rows], [f"Q{i:03d}" for i in range(1, 35)])
        for row in rows[:30]:
            self.assertEqual(len(row["options"]), 4)
            self.assertEqual(row["options"].count(row["correct_answer"]), 1)
            self.assertTrue(row["explanation"])

    def test_sections_cover_the_full_mix_in_parallel_batches(self):
        sections = generation_sections()
        self.assertEqual([s["key"] for s in sections], list(SECTION_KEYS))
        self.assertEqual(sum(s["mcq"] for s in sections), 30)
        self.assertEqual(sum(s["mcq_medium"] for s in sections), 12)
        self.assertEqual(sum(s["mcq_hard"] for s in sections), 18)
        self.assertEqual(len({s["focus"] for s in sections[1:]}), 3)
        uneven = generation_sections({"mcq": 25, "coding": 1, "sql": 0, "mcq_medium": 10, "mcq_hard": 15}, batch_size=10)
        self.assertEqual([s["mcq"] for s in uneven], [0, 9, 8, 8])
        self.assertEqual(sum(s["mcq_medium"] for s in uneven), 10)

    def test_rejects_definitions_unsupported_skills_and_malformed_mcqs(self):
        edits = [ {"question": "What is Python?"}, {"skill": "Kubernetes"},
                  {"jd_requirement": "Deploy to AWS"}, {"options": ["A", "B", "C"]},
                  {"options": ["A", "A", "C", "D"]}, {"correct_answer": "E"},
                  {"difficulty": "Expert"}, {"explanation": ""} ]
        for edit in edits:
            with self.subTest(edit=edit):
                data = exam(); data["questions"][0].update(edit)
                with self.assertRaises(ValueError):
                    validate_exam(data, normalized_jd(JD), total=TOTAL)

    def test_rejects_duplicates_and_previous_question_reuse(self):
        data = exam(); data["questions"][1]["question"] = MCQ_TEXTS[0]
        with self.assertRaises(ValueError): validate_exam(data, normalized_jd(JD), total=TOTAL)
        with self.assertRaises(ValueError): validate_exam(exam(), normalized_jd(JD), total=TOTAL, previous_questions=[MCQ_TEXTS[0]])

    def test_unambiguous_letter_answers_are_converted_to_option_text(self):
        data = exam()
        data["questions"][0]["options"] = ["Validate input", "Handle absent optional field", "Drop the request", "Disable parsing"]
        data["questions"][0]["correct_answer"] = "Option B"
        rows = validate_exam(data, normalized_jd(JD), total=TOTAL)
        self.assertEqual(rows[0]["correct_answer"], "Handle absent optional field")

    def test_requires_complete_count_and_difficulty_mix(self):
        incomplete = exam(); incomplete["questions"].pop()
        with self.assertRaises(ValueError): validate_exam(incomplete, normalized_jd(JD))
        data = exam()
        for q in data["questions"]: q["difficulty"] = "Easy"
        with self.assertRaises(ValueError): validate_exam(data, normalized_jd(JD), total=TOTAL)

    def test_fixed_type_counts_and_moderate_coding_sql_are_enforced(self):
        for index, patch_data in ((0, {"question_type": "CODING"}), (0, {"difficulty": "Hard"}),
                                  (CODING, {"difficulty": "Hard"}), (SQL, {"difficulty": "Hard"})):
            with self.subTest(index=index, patch_data=patch_data):
                data = exam(); data["questions"][index].update(patch_data)
                with self.assertRaises(ValueError): validate_exam(data, normalized_jd(JD))

    def test_a_section_is_validated_against_its_own_mix(self):
        mcq_section = next(s for s in generation_sections() if s["key"] == "mcq_2")
        rows = validate_exam(section_exam("mcq_2"), normalized_jd(JD), mix=mcq_section)
        self.assertEqual(len(rows), 10)
        with self.assertRaisesRegex(ValueError, "exactly 10 MCQs"):
            validate_exam(section_exam("coding_sql"), normalized_jd(JD), total=4, mix=mcq_section)

    def test_numbered_requirements_resolve_to_original_jd_text(self):
        catalog = requirement_catalog(normalized_jd(JD))
        ref = next(key for key, value in catalog.items() if value == "Python")
        data = exam()
        for question in data["questions"]:
            question["jd_requirement_id"] = ref
            question["jd_requirement"] = "paraphrased model evidence"
        llm = FakeExamLLM(sections={key: [json.dumps(section_exam(key, data))] for key in SECTION_KEYS})
        with patch.object(service, "LLMService", return_value=llm):
            metadata, rows = service._generate_questions_with_ai(JD)
        self.assertEqual({row["jd_requirement"] for row in rows}, {"Python"})
        self.assertEqual(metadata["experience_required"], "3-5 years")

    def test_candidate_cannot_see_answer_explanation_or_rubric(self):
        q = validate_exam(exam(), normalized_jd(JD), total=TOTAL)[0]
        public = candidate_question_payload(q)
        for key in ("correct_answer", "explanation", "evaluation_focus", "jd_requirement"):
            self.assertNotIn(key, public)
            self.assertIn(key, recruiter_question_payload(q))

    def test_generation_runs_sections_in_parallel_then_one_independent_review(self):
        llm = FakeExamLLM()
        with patch.object(service, "LLMService", return_value=llm):
            _, rows = service._generate_questions_with_ai(JD)
        self.assertEqual(len(rows), 34)
        self.assertEqual(Counter(r["question_type"] for r in rows), {"mcq": 30, "coding": 2, "sql": 2})
        self.assertEqual([r["question_type"] for r in rows[-4:]], ["coding", "coding", "sql", "sql"])
        self.assertEqual([r["sort_order"] for r in rows], list(range(34)))
        self.assertEqual([r["question_id"] for r in rows], [f"Q{i:03d}" for i in range(1, 35)])
        self.assertEqual(len(llm.prompts), 5)  # four sections + one review of the merged exam
        for key in SECTION_KEYS:
            prompt = llm.section_prompts(key)[0]
            self.assertIn(JD["raw_text"], prompt)
            self.assertNotIn("Candidate Resume", prompt)
            self.assertNotIn("resume_data", prompt)
        mcq_prompt = llm.section_prompts("mcq_1")[0]
        self.assertIn("Return exactly 10 questions: 10 MCQs (4 Medium/moderate and 6 Hard)", mcq_prompt)
        self.assertIn("exactly 30 MCQs (12 Medium/moderate and 18 Hard)", mcq_prompt)
        self.assertNotIn("SQL: answers are executed on SQLite", mcq_prompt)
        self.assertIn("SQL: answers are executed on SQLite", llm.section_prompts("coding_sql")[0])
        review = llm.review_prompts()[0]
        self.assertIn("R001", review)
        self.assertIn("Require exactly 34 questions: 30 MCQs (12 Medium/moderate and 18 Hard)", review)
        self.assertIn("Q034", review)

    def test_section_calls_are_in_flight_at_the_same_time(self):
        barrier = threading.Barrier(len(SECTION_KEYS), timeout=5)
        llm = FakeExamLLM()
        original = llm.invoke

        def invoke(prompt, temperature=None):
            if section_of(prompt):
                barrier.wait()  # BrokenBarrierError unless all four sections run concurrently
            return original(prompt, temperature)
        llm.invoke = invoke
        with patch.object(service, "LLMService", return_value=llm):
            _, rows = service._generate_questions_with_ai(JD)
        self.assertEqual(len(rows), 34)

    def test_assessment_model_default_and_override(self):
        for configured, expected in (("", "gpt-4.1"), ("custom-assessment-model", "custom-assessment-model")):
            with self.subTest(configured=configured), patch.dict("os.environ", {"ASSESSMENT_MODEL": configured}), \
                 patch.object(service, "LLMService", return_value=FakeExamLLM()) as factory:
                service._generate_questions_with_ai(JD)
                factory.assert_called_once_with(model=expected, temperature=0.6)

    def test_only_the_failed_section_is_regenerated_with_its_feedback(self):
        llm = FakeExamLLM(sections={"mcq_2": ["not json"]})
        with patch.object(service, "LLMService", return_value=llm):
            _, rows = service._generate_questions_with_ai(JD)
        self.assertEqual(len(rows), 34)
        self.assertEqual(len(llm.section_prompts("mcq_2")), 2)
        for key in ("coding_sql", "mcq_1", "mcq_3"):
            self.assertEqual(len(llm.section_prompts(key)), 1)
        self.assertIn("Previous attempt failed validation", llm.section_prompts("mcq_2")[1])

    def test_cross_section_duplicates_regenerate_the_later_section(self):
        repeated = section_exam("mcq_3")
        repeated["questions"][0]["question"] = MCQ_TEXTS[0]  # the first question of mcq_1
        llm = FakeExamLLM(sections={"mcq_3": [json.dumps(repeated)]})
        with patch.object(service, "LLMService", return_value=llm):
            _, rows = service._generate_questions_with_ai(JD)
        self.assertEqual(len({r["question_text"] for r in rows}), 34)
        self.assertEqual(len(llm.section_prompts("mcq_3")), 2)
        self.assertEqual(len(llm.section_prompts("mcq_1")), 1)
        self.assertIn("repeats another section", llm.section_prompts("mcq_3")[1])

    def test_semantic_review_failure_regenerates_the_flagged_section(self):
        llm = FakeExamLLM(reviews=['{"valid": false, "issues": ["Semantic duplicate Q012 and Q013"]}', REVIEW_OK])
        with patch.object(service, "LLMService", return_value=llm):
            _, rows = service._generate_questions_with_ai(JD)
        self.assertEqual(len(rows), 34)
        self.assertEqual(len(llm.section_prompts("mcq_2")), 2)  # Q011-Q020 come from the second MCQ batch
        self.assertEqual(len(llm.section_prompts("mcq_1")), 1)
        self.assertIn("Semantic duplicate", llm.section_prompts("mcq_2")[1])
        self.assertEqual(len(llm.review_prompts()), 2)

    def test_unattributed_review_failure_regenerates_every_section(self):
        llm = FakeExamLLM(reviews=['{"valid": false, "issues": ["Too theoretical overall"]}', REVIEW_OK])
        with patch.object(service, "LLMService", return_value=llm):
            service._generate_questions_with_ai(JD)
        for key in SECTION_KEYS:
            self.assertEqual(len(llm.section_prompts(key)), 2)

    def test_incomplete_ai_never_generates_generic_fallback(self):
        llm = FakeExamLLM(sections={key: ["{}"] * 3 for key in SECTION_KEYS})
        with patch.object(service, "LLMService", return_value=llm):
            with self.assertRaises(service.AssessmentServiceError): service._generate_questions_with_ai(JD)
        self.assertEqual(len(llm.prompts), 12)  # three rounds of four sections and never a review
        self.assertEqual(llm.review_prompts(), [])

    def test_ai_unavailable_fails_without_creating_exam(self):
        with patch.object(service, "LLMService", side_effect=ValueError("missing key")):
            with self.assertRaises(service.AssessmentServiceError): service._generate_questions_with_ai(JD)

    def test_failure_preserves_existing_draft(self):
        with patch.object(service, "_load_context", return_value={"jd": JD, "candidate": {"name": "Private", "email": "private@example.com"}}), \
             patch.object(service.assessment_repo, "get_active_assessment_for_candidate_jd", return_value={"id": 27, "status": "DRAFT"}), \
             patch.object(service.assessment_repo, "get_recent_questions_for_jd", return_value=[]), \
             patch.object(service, "_generate_questions_with_ai", side_effect=service.AssessmentServiceError("rejected")) as generate, \
             patch.object(service.assessment_repo, "create_assessment") as create, \
             patch.object(service.assessment_repo, "delete_assessment_cascade") as delete:
            with self.assertRaises(service.AssessmentServiceError):
                service.generate_assessment(recruiter_id=1, candidate_id=2, jd_id=3, passing_score=70, time_limit_minutes=90)
            create.assert_not_called(); delete.assert_not_called()
            self.assertEqual(generate.call_args.args, (JD,))

    def test_standalone_exam_requires_no_candidate_or_resume(self):
        rows = validate_exam(exam(), normalized_jd(JD), total=TOTAL)
        with patch.object(service.db, "get_jd_by_id", return_value=JD), \
             patch.object(service.db, "get_candidate_by_id") as candidate, \
             patch.object(service, "_generate_questions_with_ai", return_value=({"exam_title": "JD-Based Assessment", "job_title": "Python Developer", "experience_required": "3-5 years"}, rows)):
            result = service.generate_jd_exam(3)
            candidate.assert_not_called()
            self.assertEqual(result["experience_required"], "3-5 years")
            self.assertEqual(result["questions"][0]["question_type"], "MCQ")
            self.assertEqual(result["total_questions"], 34)


class RecruiterMcqValidationTests(unittest.TestCase):
    """Recruiter-added and edited MCQs: four distinct options, exactly one correct answer, an explanation."""

    GOOD = {"question_type": "mcq", "question_text": "Pick the safest rollout plan.", "options": ["A1", "B1", "C1", "D1"],
            "correct_answer": "C1", "explanation": "C1 keeps a rollback path."}

    def test_valid_mcq_passes(self):
        service.validate_mcq(dict(self.GOOD))
        service.validate_mcq({"question_type": "coding"})  # other types are not MCQ-checked

    def test_invalid_mcqs_are_rejected(self):
        for patch_data, message in (
            ({"options": ["A1", "B1", "C1"]}, "exactly four"),
            ({"options": ["A1", "B1", "C1", ""]}, "exactly four"),
            ({"options": ["A1", "a1", "C1", "D1"]}, "different"),
            ({"correct_answer": ""}, "exactly one"),
            ({"correct_answer": "E1"}, "exactly one"),
            ({"explanation": " "}, "explanation"),
            ({"question_text": ""}, "question text"),
        ):
            with self.subTest(patch_data=patch_data), self.assertRaisesRegex(service.AssessmentServiceError, message):
                service.validate_mcq({**self.GOOD, **patch_data})

    def test_add_and_update_enforce_mcq_rules_and_append_after_existing_questions(self):
        sent = {"id": 1, "status": "SENT"}
        existing = [{"id": 5, "sort_order": 0}, {"id": 6, "sort_order": 33}]
        with patch.object(service.assessment_repo, "get_assessment_by_id", return_value=sent), \
             patch.object(service.assessment_repo, "count_questions_for_assessment", return_value=2), \
             patch.object(service.assessment_repo, "get_questions_for_assessment", return_value=existing), \
             patch.object(service.assessment_repo, "create_question", return_value=7) as create, \
             patch.object(service.assessment_repo, "get_question_by_id", return_value={"id": 7, **self.GOOD}):
            with self.assertRaisesRegex(service.AssessmentServiceError, "exactly one"):
                service.add_question({"assessment_id": 1, **self.GOOD, "correct_answer": "nope"})
            create.assert_not_called()
            service.add_question({"assessment_id": 1, **self.GOOD})
            self.assertEqual(create.call_args.args[0]["sort_order"], 34)
        with patch.object(service.assessment_repo, "get_question_by_id", return_value={"id": 7, "assessment_id": 1, **self.GOOD}), \
             patch.object(service.assessment_repo, "get_assessment_by_id", return_value=sent), \
             patch.object(service.assessment_repo, "update_question") as update:
            with self.assertRaisesRegex(service.AssessmentServiceError, "exactly one"):
                service.update_question(7, {"options": ["W", "X", "Y", "Z"]})  # the old answer is no longer an option
            update.assert_not_called()

    def test_questions_lock_once_the_candidate_starts(self):
        for status in ("IN_PROGRESS", "COMPLETED", "PASSED"):
            with self.subTest(status=status), \
                 patch.object(service.assessment_repo, "get_assessment_by_id", return_value={"id": 1, "status": status}):
                with self.assertRaisesRegex(service.AssessmentServiceError, "only be added"):
                    service.add_question({"assessment_id": 1, **self.GOOD})


if __name__ == "__main__": unittest.main()
