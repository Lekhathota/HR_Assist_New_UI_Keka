"""Recruiter-defined coding questions (Assessment Builder → Coding Questions).

Runs the real service, prompt template, validation and test preparation against an
in-memory assessment store. The LLM is a fake that records every prompt it receives.
"""
from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask

from assessment.models import AssessmentStatus
from services import coding_question_service as svc
from services.assessment_service import AssessmentServiceError

JD = {"id": 20, "title": "Backend Engineer", "client_id": 5, "raw_text": "Build REST APIs in Java and Python.",
      "skills": ["Java", "Python"], "responsibilities": ["Design order processing services"]}
CLIENT = {"id": 5, "name": "Acme", "coding_assessment_prompt": "Acme default: focus on clean, testable code."}
TOPICS = [
    "Detect cycles in a dependency graph of microservices",
    "Merge overlapping booking intervals for meeting rooms",
    "Compute a sliding-window rate limit per API key",
    "Find the longest palindromic substring in log tokens",
    "Schedule warehouse jobs with deadlines to maximise profit",
    "Validate balanced brackets in configuration templates",
    "Shortest delivery route on a weighted city grid",
    "Top-k most frequent error codes from a stream",
    "Serialize and deserialize a binary search tree of SKUs",
    "LRU cache eviction for product catalogue lookups",
]


def coding_item(difficulty="Medium", question=None, **overrides):
    item = {
        "question": question or ("Write a program that reads a list of order amounts from standard input and prints "
                                 "the total value of all orders, handling empty input and very large values."),
        "question_type": "coding", "difficulty": difficulty, "skill": "Python", "jd_requirement_id": None,
        "scenario_type": "Implementation", "explanation": "Sum the values in one pass.",
        "evaluation_focus": ["Correctness", "Edge cases"], "input_format": "n then n integers", "output_format": "total",
        "default_language": "python", "options": [], "starter_code": "",
        "correct_answer": "import sys\nd=sys.stdin.read().split()\nprint(sum(map(int,d[1:])))\n",
        "test_cases": [{"input": f"{n}\n" + " ".join(["1"] * n) + "\n", "expected_output": f"{n}\n", "hidden": n > 2}
                       for n in range(1, 9)],
    }
    item.update(overrides)
    return item


class FakeLLM:
    """Answers each prompt with a valid coding question unless told otherwise; records prompts."""

    def __init__(self):
        self.prompts: list[str] = []
        self.responses: list = []  # queued raw responses (str) or exceptions, used before the default

    def __call__(self, *args, **kwargs):
        return self

    def invoke(self, prompt, temperature=None):
        self.prompts.append(prompt)
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        difficulty = re.search(r"- Difficulty: (\w+)", prompt).group(1)
        topic = json.loads(prompt.split("RECRUITER QUESTION PROMPT:\n", 1)[1].split("\n", 1)[0])
        return json.dumps(coding_item(difficulty, question=f"Implement this client requirement as a stdin/stdout program: {topic}. "
                                                           "Read the input, handle edge cases and print the result."))


class Store:
    def __init__(self, status=AssessmentStatus.DRAFT.value):
        self.assessments = {1: {"id": 1, "jd_id": 20, "status": status, "candidate_id": 9}}
        self.questions: dict[int, dict] = {
            100: {"id": 100, "assessment_id": 1, "question_type": "mcq", "question_text": "Base MCQ", "sort_order": 0},
            101: {"id": 101, "assessment_id": 1, "question_type": "coding", "question_text": "Base coding question", "sort_order": 1},
        }
        self.next_id = 200
        self.client_updates: list = []

    def get_assessment_by_id(self, assessment_id):
        row = self.assessments.get(int(assessment_id))
        return copy.deepcopy(row) if row else None

    def update_assessment(self, assessment_id, patch_doc):
        self.assessments[int(assessment_id)].update(copy.deepcopy(patch_doc))
        return True

    def get_questions_for_assessment(self, assessment_id):
        rows = [q for q in self.questions.values() if q["assessment_id"] == int(assessment_id)]
        return copy.deepcopy(sorted(rows, key=lambda q: q.get("sort_order", 0)))

    def count_questions_for_assessment(self, assessment_id):
        return len(self.get_questions_for_assessment(assessment_id))

    def create_question(self, data):
        self.next_id += 1
        self.questions[self.next_id] = {**copy.deepcopy(data), "id": self.next_id}
        return self.next_id

    def update_question(self, question_id, patch_doc):
        self.questions[int(question_id)].update(copy.deepcopy(patch_doc))
        return True

    def get_question_by_id(self, question_id):
        row = self.questions.get(int(question_id))
        return copy.deepcopy(row) if row else None

    def delete_question(self, question_id):
        return self.questions.pop(int(question_id), None) is not None

    def custom(self, assessment_id=1):
        return [q for q in self.get_questions_for_assessment(assessment_id) if q.get("source") == "custom_coding"]


class CodingTestBase(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.llm = FakeLLM()
        self.client = dict(CLIENT)
        self.stack = ExitStack()
        for name in ("get_assessment_by_id", "update_assessment", "get_questions_for_assessment", "count_questions_for_assessment",
                     "create_question", "update_question", "get_question_by_id", "delete_question"):
            self.stack.enter_context(patch.object(svc.assessment_repo, name, side_effect=getattr(self.store, name)))
        self.stack.enter_context(patch.object(svc.db, "get_jd_by_id", side_effect=lambda i, include_raw_text=False: dict(JD) if int(i) == 20 else None))
        self.stack.enter_context(patch.object(svc.db, "get_client_by_id", side_effect=lambda i: dict(self.client) if int(i) == 5 else None))
        self.stack.enter_context(patch.object(svc.db, "update_client", side_effect=lambda i, data: self.client.update(data) or True))
        self.stack.enter_context(patch.object(svc.db, "log_audit"))
        self.stack.enter_context(patch.object(svc, "LLMService", self.llm))
        # No Judge0 in tests: generated tests are kept and marked unverified.
        self.stack.enter_context(patch("assessment.code_execution.preparation.Judge0Runner.from_env", return_value=None))
        self.stack.enter_context(patch.dict("os.environ", {"ASSESSMENT_MAX_CODING_QUESTIONS": "", "ASSESSMENT_MAX_QUESTIONS": ""}))

    def tearDown(self):
        self.stack.close()

    def add(self, prompt="Reverse a linked list", **fields):
        return svc.add_spec(1, {"prompt": prompt, **fields})["spec"]

    def generate_and_save(self, spec_id, **data):
        """The recruiter flow: generate a draft, review it, save it to the assessment."""
        svc.generate_spec_question(1, spec_id)
        return svc.save_spec_question(1, spec_id, data)


class DynamicCountTests(CodingTestBase):
    def test_adding_1_2_5_and_10_coding_questions(self):
        for target in (1, 2, 5, 10):
            with self.subTest(count=target):
                self.setUp()
                for i, topic in enumerate(TOPICS[:target]):
                    spec = self.add(topic, difficulty=("Easy", "Medium", "Hard")[i % 3])
                    self.generate_and_save(spec["id"])
                config = svc.get_coding_config(1)
                self.assertEqual(len(config["specs"]), target)
                self.assertTrue(all(s["status"] == "generated" for s in config["specs"]))
                self.assertEqual(len(self.store.custom()), target)
                self.assertEqual(config["coding_question_count"], target + 1)  # plus the base exam's coding question
                self.assertEqual([q["sort_order"] for q in self.store.custom()], list(range(2, 2 + target)))
                self.tearDown()

    def test_each_question_uses_its_own_prompt_plus_client_and_jd(self):
        svc.save_client_prompt(1, "Acme wants Java 17 idioms and O(n log n) or better.")
        first = self.add("Design a rate limiter for order APIs", language="java", difficulty="Hard")
        second = self.add("Parse CSV of invoices and total by customer", language="python", difficulty="Easy")
        self.generate_and_save(first["id"])
        self.generate_and_save(second["id"])
        p1, p2 = self.llm.prompts
        self.assertIn("Design a rate limiter for order APIs", p1)
        self.assertNotIn("Parse CSV of invoices", p1)
        self.assertIn("Parse CSV of invoices and total by customer", p2)
        for prompt in (p1, p2):
            self.assertIn("Acme wants Java 17 idioms", prompt)
            self.assertIn("Build REST APIs in Java and Python.", prompt)
        self.assertIn("- Difficulty: Hard", p1)
        self.assertIn("- Language: Java", p1)
        java, python = self.store.custom()
        self.assertEqual((java["generation_prompt"], java["client_prompt_snapshot"]),
                         ("Design a rate limiter for order APIs", "Acme wants Java 17 idioms and O(n log n) or better."))
        self.assertEqual((java["allowed_languages"], java["default_language"], java["difficulty"]), (["java"], "java", "Hard"))
        self.assertEqual((python["difficulty"], python["allowed_languages"]), ("Easy", ["python"]))
        self.assertGreaterEqual(len(java["test_cases"]), 5)
        self.assertTrue(any(case["hidden"] for case in java["test_cases"]))

    def test_any_language_keeps_all_languages(self):
        self.generate_and_save(self.add("Any-language task")["id"])
        self.assertEqual(len(self.store.custom()[0]["allowed_languages"]), 5)


class EditRegenerateRemoveTests(CodingTestBase):
    def test_edit_then_regenerate_replaces_the_same_question(self):
        spec = self.add("Old requirement")
        first = self.generate_and_save(spec["id"])["question"]
        svc.update_spec(1, spec["id"], {"prompt": "New requirement: dedupe events", "points": 30})
        svc.generate_spec_question(1, spec["id"])
        # Until the new draft is saved the assessment keeps the old question.
        self.assertIn("Old requirement", self.store.custom()[0]["question_text"])
        self.assertEqual(svc.get_coding_config(1)["specs"][0]["status"], "review")
        second = svc.save_spec_question(1, spec["id"])["question"]
        self.assertEqual(first["id"], second["id"])
        self.assertIn("New requirement: dedupe events", second["question_text"])
        self.assertEqual(second["points"], 30)
        self.assertEqual(len(self.store.custom()), 1)
        # Regenerating does not count the question's own old text as a duplicate.
        self.assertNotIn("Old requirement", self.llm.prompts[-1].split("Do not repeat")[-1] if "Do not repeat" in self.llm.prompts[-1] else "")

    def test_generate_accepts_unsaved_edits(self):
        spec = self.add("")
        svc.generate_spec_question(1, spec["id"], {"prompt": "Typed but not saved", "difficulty": "Hard"})
        saved = svc.get_coding_config(1)["specs"][0]
        self.assertEqual((saved["prompt"], saved["difficulty"]), ("Typed but not saved", "Hard"))

    def test_remove_deletes_entry_and_its_question(self):
        spec = self.add()
        self.generate_and_save(spec["id"])
        config = svc.remove_spec(1, spec["id"])
        self.assertEqual(config["specs"], [])
        self.assertEqual(self.store.custom(), [])
        self.assertIn(101, self.store.questions)  # base exam untouched

    def test_question_deleted_from_list_shows_entry_as_pending(self):
        spec = self.add()
        question = self.generate_and_save(spec["id"])["question"]
        self.store.delete_question(question["id"])
        self.assertEqual(svc.get_coding_config(1)["specs"][0]["status"], "pending")


class ValidationTests(CodingTestBase):
    def test_empty_prompt_cannot_be_generated(self):
        spec = self.add("")
        with self.assertRaisesRegex(AssessmentServiceError, "requirements"):
            svc.generate_spec_question(1, spec["id"])
        self.assertEqual(self.llm.prompts, [])

    def test_field_validation(self):
        for fields, message in (
            ({"language": "cobol"}, "Unsupported language"),
            ({"difficulty": "Extreme"}, "Difficulty"),
            ({"points": 0}, "Points"),
            ({"prompt": "x" * 4001}, "too long"),
            ({"prompt": 42}, "must be text"),
        ):
            with self.subTest(fields=fields), self.assertRaisesRegex(AssessmentServiceError, message):
                svc.add_spec(1, {"prompt": "ok", **fields})
        with self.assertRaisesRegex(AssessmentServiceError, "too long"):
            svc.save_client_prompt(1, "y" * 4001)

    def test_limits_are_configurable(self):
        with patch.dict("os.environ", {"ASSESSMENT_MAX_CODING_QUESTIONS": "3"}):
            for _ in range(3):
                self.add()
            with self.assertRaises(AssessmentServiceError) as ctx:
                self.add()
        self.assertEqual(ctx.exception.status_code, 409)
        with patch.dict("os.environ", {"ASSESSMENT_MAX_QUESTIONS": "34"}):  # the floor: the generated exam size
            self.store.questions.update({i: {"id": i, "assessment_id": 1, "question_type": "mcq", "question_text": f"q{i}"} for i in range(300, 330)})
            with self.assertRaisesRegex(AssessmentServiceError, "at most 34 questions"):
                self.add()

    def test_malformed_output_is_retried_with_feedback(self):
        self.llm.responses = ["not json", json.dumps(coding_item("Easy"))]
        spec = self.add(difficulty="Medium")
        svc.generate_spec_question(1, spec["id"])
        self.assertEqual(len(self.llm.prompts), 3)
        self.assertIn("previous attempt failed validation", self.llm.prompts[2].lower())
        self.assertIn("difficulty must be Medium", self.llm.prompts[2])

    def test_repeated_failure_keeps_prompt_and_marks_entry_failed(self):
        self.llm.responses = ["{}", "{}", "{}"]
        spec = self.add("Keep this prompt")
        with self.assertRaises(AssessmentServiceError) as ctx:
            svc.generate_spec_question(1, spec["id"])
        self.assertEqual(ctx.exception.status_code, 502)
        saved = svc.get_coding_config(1)["specs"][0]
        self.assertEqual((saved["status"], saved["prompt"]), ("failed", "Keep this prompt"))
        self.assertTrue(saved["last_error"])
        self.assertEqual(self.store.custom(), [])

    def test_sent_but_not_started_assessments_can_still_change(self):
        self.store.assessments[1]["status"] = AssessmentStatus.SENT.value
        spec = self.add()
        self.generate_and_save(spec["id"])
        self.assertEqual(len(self.store.custom()), 1)
        self.assertTrue(svc.get_coding_config(1)["editable"])

    def test_questions_lock_once_the_candidate_starts(self):
        spec = self.add()
        self.store.assessments[1]["status"] = AssessmentStatus.IN_PROGRESS.value
        for call in (lambda: self.add(), lambda: svc.generate_spec_question(1, spec["id"]),
                     lambda: svc.remove_spec(1, spec["id"]), lambda: svc.save_client_prompt(1, "x"),
                     lambda: svc.save_spec_question(1, spec["id"]), lambda: svc.discard_draft(1, spec["id"])):
            with self.assertRaises(AssessmentServiceError) as ctx:
                call()
            self.assertEqual(ctx.exception.status_code, 409)
        self.assertFalse(svc.get_coding_config(1)["editable"])

    def test_unknown_assessment_and_entry(self):
        with self.assertRaises(AssessmentServiceError) as ctx:
            svc.get_coding_config(99)
        self.assertEqual(ctx.exception.status_code, 404)
        with self.assertRaises(AssessmentServiceError) as ctx:
            svc.generate_spec_question(1, "missing")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_question_validator(self):
        base = dict(difficulty="Medium", language="", points=15, catalog={"R001": "Build REST APIs"})
        svc.validate_generated_coding_question(coding_item(jd_requirement_id="R001"), **base)
        for item, message in (
            (coding_item("Hard"), "difficulty must be Medium"),
            (coding_item(jd_requirement_id="R999"), "jd_requirement_id"),
            (coding_item(question="Too short"), "complete problem statement"),
            (coding_item(correct_answer=""), "reference program"),
            (coding_item(question_type="mcq"), "coding"),
            (coding_item(test_cases=[]), "test_cases"),
            ([], "one JSON object"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                svc.validate_generated_coding_question(item, **base)
        with self.assertRaisesRegex(ValueError, "repeats"):
            svc.validate_generated_coding_question(coding_item(), previous_questions=[coding_item()["question"]], **base)


class FakeRunner:
    """Stands in for Judge0: runs nothing, answers every test with `stdout` (None echoes the expected output)."""

    def __init__(self, stdout=None):
        self.stdout = stdout
        self.calls = []

    def run(self, language, code, cases):
        from types import SimpleNamespace
        self.calls.append(code)
        return [SimpleNamespace(status="ok", stdout=case["expected_output"] if self.stdout is None else self.stdout) for case in cases]


class ReviewAndSaveTests(CodingTestBase):
    """Generate → review/edit the draft → save; the assessment only changes on save."""

    def test_generate_creates_a_reviewable_draft_without_touching_the_assessment(self):
        before = copy.deepcopy(self.store.questions)
        result = svc.generate_spec_question(1, self.add("Merge overlapping intervals", topic="Intervals", time_limit_minutes=25)["id"])
        self.assertEqual(self.store.questions, before)
        draft = result["draft"]
        for key in ("question_text", "input_format", "output_format", "constraints", "correct_answer", "explanation", "test_cases"):
            self.assertIn(key, draft)
        self.assertTrue(any(case["hidden"] for case in draft["test_cases"]))
        self.assertTrue(any(not case["hidden"] for case in draft["test_cases"]))
        self.assertEqual((draft["skill_tag"], draft["time_limit_minutes"]), ("Intervals", 25))
        self.assertEqual(result["spec"]["status"], "review")
        # The draft is stored on the entry, so it survives a page reload.
        reloaded = svc.get_coding_config(1)["specs"][0]
        self.assertEqual(reloaded["draft"]["question_text"], draft["question_text"])
        self.assertEqual(reloaded["status"], "review")

    def test_topic_and_time_limit_reach_the_prompt(self):
        svc.generate_spec_question(1, self.add("Rate limiter", topic="Sliding window", time_limit_minutes=40)["id"])
        self.assertIn('Topic / skill assessed: "Sliding window"', self.llm.prompts[-1])
        self.assertIn("Time limit: 40 minutes", self.llm.prompts[-1])
        svc.generate_spec_question(1, self.add("No extras")["id"])
        self.assertNotIn("Topic / skill assessed", self.llm.prompts[-1])
        self.assertNotIn("Time limit:", self.llm.prompts[-1])

    def test_recruiter_edits_are_saved_and_the_question_gets_the_next_number(self):
        spec = self.add("Top-k error codes", topic="Heaps", time_limit_minutes=30, points=25)
        svc.generate_spec_question(1, spec["id"])
        edited = ("Given a stream of service error codes, print the k most frequent codes in descending order of "
                  "frequency, breaking ties by the smaller code.")
        tests = [{"input": f"{n}\n" + " ".join(["1"] * n) + "\n", "expected_output": f"{n}\n", "hidden": n > 2} for n in range(1, 7)]
        saved = svc.save_spec_question(1, spec["id"], {"question": {
            "question_text": edited, "constraints": "1 <= k <= n <= 10^5", "explanation": "Count, then heap-select k.",
            "test_cases": tests}})["question"]
        row = self.store.questions[saved["id"]]
        self.assertEqual((row["question_text"], row["constraints"], row["explanation"]),
                         (edited, "1 <= k <= n <= 10^5", "Count, then heap-select k."))
        self.assertEqual((row["skill_tag"], row["time_limit_minutes"], row["points"]), ("Heaps", 30, 25))
        self.assertEqual(len(row["test_cases"]), 6)
        self.assertEqual(sum(case["hidden"] for case in row["test_cases"]), 4)
        self.assertEqual(row["source"], "custom_coding")
        # Appended after the existing questions: Q1, Q2 untouched and this becomes Q3.
        self.assertEqual([q["id"] for q in self.store.get_questions_for_assessment(1)], [100, 101, saved["id"]])
        self.assertEqual(self.store.questions[100]["question_text"], "Base MCQ")
        spec_view = svc.get_coding_config(1)["specs"][0]
        self.assertEqual((spec_view["status"], spec_view["draft"]), ("generated", None))

    def test_new_questions_go_after_the_highest_position_even_with_gaps(self):
        self.store.questions[101]["sort_order"] = 40  # e.g. a question in the middle was deleted earlier
        first = self.generate_and_save(self.add(TOPICS[0])["id"])["question"]
        second = self.generate_and_save(self.add(TOPICS[1])["id"])["question"]
        self.assertEqual((first["sort_order"], second["sort_order"]), (41, 42))

    def test_save_validates_the_reviewed_question(self):
        spec = self.add("Validate me")
        svc.generate_spec_question(1, spec["id"])
        draft_tests = svc.get_coding_config(1)["specs"][0]["draft"]["test_cases"]
        for edits, message in (
            ({"question_text": "Too short to be a problem"}, "at least 12 words"),
            ({"correct_answer": "  "}, "reference solution"),
            ({"explanation": ""}, "explanation"),
            ({"question_text": 42}, "must be text"),
            ({"test_cases": [dict(case, hidden=True) for case in draft_tests]}, "visible sample tests"),
            ({"test_cases": draft_tests[:3]}, "hidden tests"),
            ({"test_cases": [dict(case, expected_output="") if i == 0 else case for i, case in enumerate(draft_tests)]}, "Test 1 needs an expected output"),
            ({"test_cases": [dict(case, input=draft_tests[0]["input"]) if i == 1 else case for i, case in enumerate(draft_tests)]}, "same input"),
            ({"question_text": "Base coding question"}, "at least 12 words"),
        ):
            with self.subTest(edits=list(edits)), self.assertRaisesRegex(AssessmentServiceError, message):
                svc.save_spec_question(1, spec["id"], {"question": edits})
        self.assertEqual(self.store.custom(), [])  # nothing saved by failed attempts; the draft is kept
        self.assertEqual(svc.get_coding_config(1)["specs"][0]["status"], "review")
        with self.assertRaisesRegex(AssessmentServiceError, "Time limit"):
            svc.save_spec_question(1, spec["id"], {"time_limit_minutes": 999})

    def test_duplicate_of_an_existing_question_is_rejected_on_save(self):
        self.store.questions[102] = {"id": 102, "assessment_id": 1, "question_type": "mcq", "sort_order": 2,
                                     "question_text": "Write a program that reads order amounts and prints the grand total for the whole batch of orders."}
        spec = self.add("Anything")
        svc.generate_spec_question(1, spec["id"])
        with self.assertRaisesRegex(AssessmentServiceError, "repeats another question"):
            svc.save_spec_question(1, spec["id"], {"question": {"question_text": self.store.questions[102]["question_text"]}})

    def test_edited_tests_are_verified_against_the_reference_solution(self):
        spec = self.add("Verify me")
        svc.generate_spec_question(1, spec["id"])
        tests = svc.get_coding_config(1)["specs"][0]["draft"]["test_cases"]
        with patch("assessment.code_execution.preparation.Judge0Runner.from_env", return_value=FakeRunner(stdout="wrong\n")):
            with self.assertRaisesRegex(AssessmentServiceError, "does not pass the test cases"):
                svc.save_spec_question(1, spec["id"], {"question": {"test_cases": tests}})
        runner = FakeRunner()
        with patch("assessment.code_execution.preparation.Judge0Runner.from_env", return_value=runner):
            saved = svc.save_spec_question(1, spec["id"], {"question": {"test_cases": tests}})["question"]
        self.assertTrue(saved["tests_verified"])
        self.assertEqual(len(runner.calls), 1)

    def test_save_requires_a_generated_draft(self):
        spec = self.add("Not generated yet")
        with self.assertRaises(AssessmentServiceError) as ctx:
            svc.save_spec_question(1, spec["id"])
        self.assertEqual(ctx.exception.status_code, 409)

    def test_discarding_a_draft_keeps_the_saved_question(self):
        spec = self.add("Keep my saved version")
        saved = self.generate_and_save(spec["id"])["question"]
        svc.update_spec(1, spec["id"], {"prompt": "Experimental rewrite"})
        svc.generate_spec_question(1, spec["id"])
        config = svc.discard_draft(1, spec["id"])
        self.assertEqual((config["specs"][0]["status"], config["specs"][0]["draft"]), ("generated", None))
        self.assertEqual(self.store.custom()[0]["id"], saved["id"])
        self.assertIn("Keep my saved version", self.store.custom()[0]["question_text"])

    def test_more_than_two_questions_survive_a_reload_alongside_the_base_exam(self):
        for topic in TOPICS[:4]:
            self.generate_and_save(self.add(topic)["id"])
        questions = self.store.get_questions_for_assessment(1)  # what GET /api/assessment/1 returns after a refresh
        self.assertEqual(len(questions), 6)
        self.assertEqual([q["id"] for q in questions[:2]], [100, 101])
        self.assertEqual(len({q["id"] for q in questions}), 6)
        self.assertEqual([s["status"] for s in svc.get_coding_config(1)["specs"]], ["generated"] * 4)

    def test_candidates_never_see_the_recruiter_prompts(self):
        from assessment.utilities import candidate_question_payload

        saved = self.generate_and_save(self.add("Secret approach: use a monotonic stack", topic="Stacks", time_limit_minutes=20)["id"])["question"]
        public = candidate_question_payload(self.store.questions[saved["id"]])
        for key in ("generation_prompt", "client_prompt_snapshot", "correct_answer", "source", "coding_spec_id"):
            self.assertNotIn(key, public)
        self.assertEqual(public["time_limit_minutes"], 20)

    def test_topic_and_time_limit_validation(self):
        for fields, message in (({"topic": "x" * 201}, "topic is too long"), ({"topic": 5}, "topic must be text"),
                                ({"time_limit_minutes": 0}, "Time limit"), ({"time_limit_minutes": "abc"}, "Time limit"),
                                ({"time_limit_minutes": 2.5}, "Time limit")):
            with self.subTest(fields=fields), self.assertRaisesRegex(AssessmentServiceError, message):
                svc.add_spec(1, {"prompt": "ok", **fields})
        spec = svc.add_spec(1, {"prompt": "ok", "time_limit_minutes": ""})["spec"]
        self.assertIsNone(spec["time_limit_minutes"])


class ClientPromptTests(CodingTestBase):
    def test_client_default_is_used_until_overridden_and_can_be_saved(self):
        config = svc.get_coding_config(1)
        self.assertEqual(config["client"], {"id": 5, "name": "Acme"})
        self.assertEqual(config["client_prompt"], CLIENT["coding_assessment_prompt"])
        svc.generate_spec_question(1, self.add()["id"])
        self.assertIn("Acme default: focus on clean, testable code.", self.llm.prompts[-1])

        svc.save_client_prompt(1, "Assessment-specific rules")
        self.assertEqual(svc.get_coding_config(1)["client_prompt"], "Assessment-specific rules")
        self.assertEqual(self.client["coding_assessment_prompt"], CLIENT["coding_assessment_prompt"])

        svc.save_client_prompt(1, "New Acme default", save_as_client_default=True)
        self.assertEqual(self.client["coding_assessment_prompt"], "New Acme default")

    def test_an_empty_assessment_prompt_overrides_the_client_default(self):
        svc.save_client_prompt(1, "")
        self.assertEqual(svc.get_coding_config(1)["client_prompt"], "")


class CarryOverTests(CodingTestBase):
    def test_regenerated_draft_keeps_entries_and_questions(self):
        svc.save_client_prompt(1, "Shared rules")
        generated = self.add("Generated one")
        self.generate_and_save(generated["id"])
        self.add("Still pending")
        self.store.assessments[2] = {"id": 2, "jd_id": 20, "status": AssessmentStatus.DRAFT.value}
        svc.carry_over_custom_coding(self.store.get_assessment_by_id(1), 2)
        config = svc.get_coding_config(2)
        self.assertEqual([s["prompt"] for s in config["specs"]], ["Generated one", "Still pending"])
        self.assertEqual([s["status"] for s in config["specs"]], ["generated", "pending"])
        self.assertEqual(config["client_prompt"], "Shared rules")
        copied = self.store.custom(2)
        self.assertEqual(len(copied), 1)
        self.assertEqual(copied[0]["generation_prompt"], "Generated one")


class RegenerateFromJdWiringTests(unittest.TestCase):
    """generate_assessment() replacing a draft must carry custom coding over before deleting it."""

    def run_generate(self, carry_side_effect=None):
        from services import assessment_service as service

        events = []
        draft = {"id": 1, "status": AssessmentStatus.DRAFT.value, "coding_specs": [{"id": "s1"}]}
        with ExitStack() as stack:
            stack.enter_context(patch.object(service, "_load_context", return_value={"candidate": {"name": "A", "email": "a@x.com"}, "jd": JD}))
            stack.enter_context(patch.object(service, "_generate_questions_with_ai",
                                             return_value=({"exam_title": "T", "job_title": "J", "experience_required": "1"}, [{"question_text": "q"}])))
            stack.enter_context(patch.object(service, "_build_assessment_response", return_value={"assessment": {"id": 2}}))
            stack.enter_context(patch.object(service.db, "log_audit"))
            repo = service.assessment_repo
            stack.enter_context(patch.object(repo, "get_active_assessment_for_candidate_jd", return_value=draft))
            stack.enter_context(patch.object(repo, "get_recent_questions_for_jd", return_value=[]))
            stack.enter_context(patch.object(repo, "create_assessment", return_value=2))
            stack.enter_context(patch.object(repo, "create_questions_bulk"))
            stack.enter_context(patch.object(repo, "delete_assessment_cascade", side_effect=lambda i: events.append(("delete", i))))
            stack.enter_context(patch.object(svc, "carry_over_custom_coding",
                                             side_effect=carry_side_effect or (lambda old, new: events.append(("carry", old["id"], new)))))
            service.generate_assessment(recruiter_id=7, candidate_id=9, jd_id=20, passing_score=70, time_limit_minutes=90)
        return events

    def test_custom_coding_is_carried_before_the_old_draft_is_deleted(self):
        self.assertEqual(self.run_generate(), [("carry", 1, 2), ("delete", 1)])

    def test_failed_carry_over_keeps_the_old_draft(self):
        with self.assertRaises(RuntimeError):
            self.run_generate(carry_side_effect=RuntimeError("db down"))


class RouteTests(CodingTestBase):
    def setUp(self):
        super().setUp()
        from routes import assessment_routes as routes

        app = Flask(__name__)
        app.register_blueprint(routes.assessment_bp)
        self.http = app.test_client()
        self.stack.enter_context(patch("services.auth_service.effective_user_id", return_value=7))
        self.stack.enter_context(patch.object(routes, "current_user", return_value={"id": 7, "username": "rec", "role": "recruiter"}))

    def test_full_flow_over_http(self):
        self.assertEqual(self.http.get("/api/assessment/1/coding").get_json()["client"]["name"], "Acme")
        spec = self.http.post("/api/assessment/1/coding/specs", json={"prompt": "Merge intervals", "language": "cpp"}).get_json()["spec"]
        response = self.http.post(f"/api/assessment/1/coding/specs/{spec['id']}/generate", json={})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["draft"]["generation_prompt"], "Merge intervals")
        self.assertEqual(self.store.custom(), [])  # nothing is added before the recruiter saves
        response = self.http.post(f"/api/assessment/1/coding/specs/{spec['id']}/save",
                                  json={"question": {"constraints": "1 <= n <= 1000"}})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["question"]["generation_prompt"], "Merge intervals")
        self.assertEqual(response.get_json()["question"]["constraints"], "1 <= n <= 1000")
        self.assertEqual(self.http.post(f"/api/assessment/1/coding/specs/{spec['id']}/generate", json={}).status_code, 200)
        self.assertIsNone(self.http.delete(f"/api/assessment/1/coding/specs/{spec['id']}/draft").get_json()["specs"][0]["draft"])
        self.assertEqual(self.http.put(f"/api/assessment/1/coding/specs/{spec['id']}", json={"difficulty": "Hard"}).status_code, 200)
        self.assertEqual(self.http.put("/api/assessment/1/coding/client-prompt", json={"prompt": "Rules"}).status_code, 200)
        self.assertEqual(self.http.delete(f"/api/assessment/1/coding/specs/{spec['id']}").get_json()["specs"], [])

    def test_errors_map_to_status_codes(self):
        self.assertEqual(self.http.get("/api/assessment/99/coding").status_code, 404)
        self.assertEqual(self.http.post("/api/assessment/1/coding/specs", json={"language": "cobol"}).status_code, 400)
        self.assertEqual(self.http.post("/api/assessment/1/coding/specs/nope/generate", json={}).status_code, 404)

    def test_login_required(self):
        with patch("services.auth_service.effective_user_id", return_value=None):
            self.assertEqual(self.http.get("/api/assessment/1/coding").status_code, 401)


if __name__ == "__main__":
    unittest.main()
