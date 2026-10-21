"""AI-generated questions added from Preview Assessment (+ Add MCQ / + Add Coding Question).

Runs the real services, prompt templates and validation against an in-memory assessment store.
The LLM is a fake that records prompts; code execution uses a fake sandbox where noted.
"""
from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assessment.models import AssessmentStatus
from services import assessment_service, coding_question_service as coding
from services import mcq_question_service as svc
from services.assessment_service import AssessmentServiceError
from tests.test_coding_questions import JD, CLIENT, TOPICS, coding_item

EMAIL = "asha@example.com"


def mcq_item(difficulty="Medium", question=None, **overrides):
    item = {
        "question": question or ("A nightly order-sync job in your Python service now takes four hours instead of forty "
                                 "minutes after a schema change. What should you check first?"),
        "question_type": "mcq", "difficulty": difficulty, "skill": "Python", "jd_requirement_id": None,
        "scenario_type": "Troubleshooting",
        "options": ["Missing index on the new join column", "Increase the server's RAM",
                    "Rewrite the job in Java", "Run the job twice as often"],
        "correct_answer": "Missing index on the new join column",
        "explanation": "A schema change that slows a query by 6x most often removed or bypassed an index.",
        "evaluation_focus": ["Root-cause analysis"], "points": 5,
    }
    item.update(overrides)
    return item


class FakeLLM:
    """Answers MCQ prompts with a valid MCQ and coding prompts with a valid coding question."""

    def __init__(self):
        self.prompts: list[str] = []
        self.responses: list = []
        self.count = 0

    def __call__(self, *args, **kwargs):
        return self

    def invoke(self, prompt, temperature=None):
        self.prompts.append(prompt)
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        self.count += 1
        difficulty = re.search(r"- Difficulty: (\w+)", prompt).group(1)
        if "multiple-choice question" in prompt:
            topic = TOPICS[(self.count - 1) % len(TOPICS)]
            return json.dumps(mcq_item(difficulty, question=f"While working on '{topic}' (case {self.count}), your Python "
                                                             "service misbehaves in production. Which action is best?"))
        topic = TOPICS[(self.count - 1) % len(TOPICS)]
        return json.dumps(coding_item(difficulty, question=f"{topic}: read the input from standard input, compute the result "
                                                           f"for case {self.count} and print it, handling edge cases."))


class FakeRunner:
    """Stands in for Judge0: echoes the expected output unless `stdout` is given."""

    def __init__(self, stdout=None):
        self.stdout = stdout
        self.calls: list[str] = []

    def run(self, language, code, cases, limits=None):
        self.calls.append(language)
        return [SimpleNamespace(status="ok", stdout=case["expected_output"] if self.stdout is None else self.stdout,
                                stderr="", time=0.01, memory=1000) for case in cases]


class Store:
    def __init__(self, status=AssessmentStatus.DRAFT.value):
        self.assessments = {1: {"id": 1, "jd_id": 20, "status": status, "candidate_id": 9, "candidate_email": EMAIL,
                                "passing_score": 60, "time_limit_minutes": 90, "title": "Backend"}}
        self.questions: dict[int, dict] = {}
        for i in range(30):
            self.questions[100 + i] = {"id": 100 + i, "assessment_id": 1, "question_type": "mcq", "sort_order": i, "points": 5,
                                       "question_id": f"Q{i + 1:03d}", "question_text": f"Base MCQ {i} about topic {i * 7919}",
                                       "options": ["a", "b", "c", "d"], "correct_answer": "a", "explanation": "x"}
        self.questions[200] = {"id": 200, "assessment_id": 1, "question_type": "coding", "sort_order": 30, "points": 15,
                               "question_id": "Q031", "question_text": "Base coding question about graphs"}
        self.next_id = 300

    def get_assessment_by_id(self, assessment_id):
        row = self.assessments.get(int(assessment_id))
        return copy.deepcopy(row) if row else None

    def update_assessment(self, assessment_id, patch_doc):
        self.assessments[int(assessment_id)].update(copy.deepcopy(patch_doc))
        return True

    def get_questions_for_assessment(self, assessment_id):
        rows = [q for q in self.questions.values() if q["assessment_id"] == int(assessment_id)]
        return copy.deepcopy(sorted(rows, key=lambda q: (q.get("sort_order", 0), q["id"])))

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

    def by_source(self, source):
        return [q for q in self.get_questions_for_assessment(1) if q.get("source") == source]


class Base(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.llm = FakeLLM()
        self.runner = None
        self.stack = ExitStack()
        for name in ("get_assessment_by_id", "update_assessment", "get_questions_for_assessment", "count_questions_for_assessment",
                     "create_question", "update_question", "get_question_by_id", "delete_question"):
            self.stack.enter_context(patch.object(svc.assessment_repo, name, side_effect=getattr(self.store, name)))
        self.stack.enter_context(patch.object(svc.db, "get_jd_by_id", side_effect=lambda i, include_raw_text=False: dict(JD) if int(i) == 20 else None))
        self.stack.enter_context(patch.object(svc.db, "get_client_by_id", side_effect=lambda i: dict(CLIENT) if int(i) == 5 else None))
        self.stack.enter_context(patch.object(svc.db, "log_audit"))
        self.stack.enter_context(patch.object(svc, "LLMService", self.llm))
        self.stack.enter_context(patch.object(coding, "LLMService", self.llm))
        self.stack.enter_context(patch.object(assessment_service, "LLMService", self.llm))
        # Code execution (Judge0) for preparation and verification; None = not configured.
        self.stack.enter_context(patch("assessment.code_execution.judge0.Judge0Runner.from_env", side_effect=lambda: self.runner))
        # Nothing in these flows may send email.
        self.send_email = self.stack.enter_context(patch.object(assessment_service, "send_email"))
        self.stack.enter_context(patch.dict("os.environ", {"ASSESSMENT_MAX_CODING_QUESTIONS": "", "ASSESSMENT_MAX_QUESTIONS": ""}))

    def tearDown(self):
        self.send_email.assert_not_called()
        self.stack.close()

    def generate_mcq(self, **settings):
        return svc.generate_mcq_draft(1, {"prompt": "Debugging slow database jobs", "difficulty": "Medium", "points": 5, **settings})

    def save_mcq(self, draft, **extra):
        question = {key: draft[key] for key in svc.EDIT_KEYS}
        return svc.save_mcq_question(1, {"question": question, "prompt": draft.get("generation_prompt", ""),
                                         "draft_meta": draft, **extra})


class McqGenerationTests(Base):
    def test_generation_returns_a_draft_and_stores_nothing(self):
        before = copy.deepcopy(self.store.questions)
        result = self.generate_mcq(topic="Query performance", difficulty="Easy", points=4, time_limit_minutes=3)
        self.assertEqual(self.store.questions, before)
        draft = result["draft"]
        self.assertEqual(len(draft["options"]), 4)
        self.assertEqual(draft["options"].count(draft["correct_answer"]), 1)
        self.assertEqual((draft["difficulty"], draft["points"], draft["skill_tag"]), ("Easy", 4, "Query performance"))
        self.assertTrue(draft["explanation"])
        prompt = self.llm.prompts[-1]
        for expected in ('"Debugging slow database jobs"', "- Difficulty: Easy", "- Marks: 4",
                         'Topic / skill assessed: "Query performance"', "Time limit: 3 minutes", "Build REST APIs in Java and Python."):
            self.assertIn(expected, prompt)
        # Existing questions are passed so the AI does not repeat them.
        self.assertIn("Base MCQ 0 about topic 0", prompt)

    def test_needs_instructions_or_topic_and_valid_settings(self):
        for data, message in (({}, "instructions or a topic"), ({"prompt": "x", "difficulty": "Expert"}, "Easy, Medium or Hard"),
                              ({"prompt": "x", "points": 0}, "between 1 and 100"),
                              ({"prompt": "x", "time_limit_minutes": 999}, "Time limit")):
            with self.subTest(message=message), self.assertRaisesRegex(AssessmentServiceError, message):
                svc.generate_mcq_draft(1, data)

    def test_invalid_ai_output_is_retried_with_feedback(self):
        self.llm.responses = [json.dumps(mcq_item(options=["a", "b", "c"])), json.dumps(mcq_item(correct_answer="Not an option"))]
        draft = self.generate_mcq()["draft"]
        self.assertEqual(len(self.llm.prompts), 3)
        self.assertIn("exactly four", self.llm.prompts[1])
        self.assertIn("exactly one option", self.llm.prompts[2])
        self.assertIn(draft["correct_answer"], draft["options"])

    def test_gives_up_after_three_invalid_answers(self):
        self.llm.responses = ["not json"] * 3
        with self.assertRaisesRegex(AssessmentServiceError, "three attempts"):
            self.generate_mcq()

    def test_ai_service_failure_is_reported(self):
        self.llm.responses = [RuntimeError("upstream timeout")]
        with self.assertRaisesRegex(AssessmentServiceError, "generation failed"):
            self.generate_mcq()

    def test_validator(self):
        base = {"difficulty": "Medium", "points": 5, "catalog": {}}
        row = svc.validate_generated_mcq(mcq_item(correct_answer="A"), **base)
        self.assertEqual(row["correct_answer"], "Missing index on the new join column")
        for item, message in ((mcq_item(difficulty="Hard"), "difficulty must be Medium"),
                              (mcq_item(options=["x", "x", "y", "z"]), "different"),
                              (mcq_item(explanation=""), "explanation"),
                              (mcq_item(question="Too short"), "complete question"),
                              (mcq_item(jd_requirement_id="R999"), "jd_requirement_id")):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                svc.validate_generated_mcq(item, **base)
        with self.assertRaisesRegex(ValueError, "repeats"):
            svc.validate_generated_mcq(mcq_item(), previous_questions=[mcq_item()["question"]], **base)

    def test_only_draft_assessments_accept_questions(self):
        self.store.assessments[1]["status"] = AssessmentStatus.SENT.value
        with self.assertRaisesRegex(AssessmentServiceError, "DRAFT"):
            self.generate_mcq()


class McqSaveTests(Base):
    def test_save_appends_after_the_mcqs_and_keeps_everything_else(self):
        before = {qid: q["question_text"] for qid, q in self.store.questions.items()}
        draft = self.generate_mcq(topic="Indexes", time_limit_minutes=2)["draft"]
        result = self.save_mcq(draft, request_id="req-mcq-0001", topic="Indexes", time_limit_minutes=2)
        saved = self.store.by_source("custom_mcq")
        self.assertEqual(len(saved), 1)
        q = saved[0]
        self.assertEqual((q["sort_order"], q["question_id"], q["question_type"]), (30, "Q032", "mcq"))
        self.assertEqual(self.store.questions[200]["sort_order"], 31)  # the coding question moved down, MCQs stay first
        self.assertEqual((q["generation_prompt"], q["skill_tag"], q["time_limit_minutes"]), ("Debugging slow database jobs", "Indexes", 2))
        for qid, text in before.items():  # nothing existing was replaced
            self.assertEqual(self.store.questions[qid]["question_text"], text)
        self.assertEqual(result["counts"], {"mcq": 31, "coding": 1, "sql": 0})
        self.assertEqual(result["total_marks"], 30 * 5 + 15 + 5)
        self.assertEqual(len(result["questions"]), 32)
        self.assertFalse(result["replayed"])
        self.assertEqual(self.store.assessments[1]["time_limit_minutes"], 90)  # duration only changes when asked

    def test_recruiter_edits_are_saved(self):
        draft = self.generate_mcq()["draft"]
        edited = {**draft, "question_text": "Edited: which index should the order-sync job's join use after the change?",
                  "options": ["Composite (customer_id, created_at)", "None", "A full-text index", "A hash on email"],
                  "correct_answer": "Composite (customer_id, created_at)", "explanation": "It covers the join and the filter.",
                  "difficulty": "Hard", "points": 8}
        self.save_mcq(edited)
        q = self.store.by_source("custom_mcq")[0]
        self.assertEqual((q["question_text"][:7], q["correct_answer"], q["difficulty"], q["points"]),
                         ("Edited:", "Composite (customer_id, created_at)", "Hard", 8))

    def test_repeated_save_of_the_same_request_stores_one_question(self):
        draft = self.generate_mcq()["draft"]
        first = self.save_mcq(draft, request_id="req-mcq-0002")
        second = self.save_mcq(draft, request_id="req-mcq-0002")
        self.assertEqual(first["question"]["id"], second["question"]["id"])
        self.assertTrue(second["replayed"])
        self.assertEqual(len(self.store.by_source("custom_mcq")), 1)

    def test_several_mcqs_get_unique_ids_and_numbers(self):
        for n in range(3):
            self.save_mcq(self.generate_mcq()["draft"], request_id=f"req-mcq-10{n}x")
        saved = self.store.by_source("custom_mcq")
        self.assertEqual([q["sort_order"] for q in saved], [30, 31, 32])
        self.assertEqual(len({q["question_id"] for q in self.store.questions.values()}), len(self.store.questions))
        self.assertEqual(self.store.questions[200]["sort_order"], 33)

    def test_invalid_or_duplicate_questions_are_rejected(self):
        draft = self.generate_mcq()["draft"]
        for change, message in (({"options": ["a", "b", "c"]}, "four"), ({"correct_answer": "zzz"}, "exactly one"),
                                ({"explanation": ""}, "explanation"),
                                ({"question_text": "Base MCQ 3 about topic 23757"}, "repeats")):
            with self.subTest(message=message), self.assertRaisesRegex(AssessmentServiceError, message):
                self.save_mcq({**draft, **change})
        self.assertEqual(self.store.by_source("custom_mcq"), [])

    def test_extend_duration_adds_the_time_limit_capped(self):
        draft = self.generate_mcq(time_limit_minutes=5)["draft"]
        result = self.save_mcq(draft, time_limit_minutes=5, extend_duration=True)
        self.assertEqual(result["assessment"]["time_limit_minutes"], 95)
        self.store.assessments[1]["time_limit_minutes"] = 478
        self.save_mcq(self.generate_mcq()["draft"], time_limit_minutes=5, extend_duration=True)
        self.assertEqual(self.store.assessments[1]["time_limit_minutes"], 480)

    def test_saved_question_needs_revalidation_and_passes_the_mcq_checks(self):
        before = assessment_service.publication_check(1)["fingerprint"]
        self.save_mcq(self.generate_mcq()["draft"])
        after = assessment_service.publication_check(1)
        self.assertNotEqual(before, after["fingerprint"])  # a previous approval / review no longer applies
        self.assertEqual(after["mcq_questions"], 31)
        self.assertFalse([i for i in after["questions"] if i["question_type"] == "mcq"])

    def test_regenerating_a_saved_custom_mcq_keeps_its_settings(self):
        self.save_mcq(self.generate_mcq(topic="Indexes", difficulty="Easy", points=3)["draft"], topic="Indexes")
        q = self.store.by_source("custom_mcq")[0]
        assessment_service.regenerate_question(q["id"])
        prompt = self.llm.prompts[-1]
        self.assertIn("multiple-choice question", prompt)
        self.assertIn("- Difficulty: Easy", prompt)
        self.assertIn('"Debugging slow database jobs"', prompt)
        regenerated = self.store.questions[q["id"]]
        self.assertEqual((regenerated["points"], regenerated["difficulty"], regenerated["sort_order"]), (3, "Easy", q["sort_order"]))
        self.assertNotEqual(regenerated["question_text"], q["question_text"])


class CodingFromPreviewTests(Base):
    """+ Add Coding Question: entry → draft → review/validate → save, as the preview drives it."""

    def new_draft(self, **fields):
        spec = coding.add_spec(1, {"prompt": "Total order amounts", **fields})["spec"]
        return spec["id"], coding.generate_spec_question(1, spec["id"])["draft"]

    def test_generated_extras_reach_the_draft(self):
        tests = [{"input": f"{n}\n" + "1 " * n + "\n", "expected_output": f"{n}\n", "hidden": n > 3, "weight": 3 if n == 1 else 1,
                  "mandatory": n == 1} for n in range(1, 9)]
        self.llm.responses = [json.dumps(coding_item(title="Order totals", edge_cases="Empty input\nLarge values", test_cases=tests,
                                                     scoring={"min_tests_passed": 4, "min_score_percent": 60},
                                                     reference_solutions={"java": "class Main {}"}))]
        _, draft = self.new_draft(language="java")
        self.assertEqual((draft["title"], draft["edge_cases"]), ("Order totals", "Empty input\nLarge values"))
        self.assertEqual(draft["scoring"]["min_tests_passed"], 4)
        self.assertEqual(draft["scoring"]["min_score_percent"], 60)
        self.assertEqual(draft["reference_solutions"], {"java": "class Main {}"})
        self.assertEqual((draft["test_cases"][0]["weight"], draft["test_cases"][0]["mandatory"]), (3, True))
        self.assertIn("reference_solutions", self.llm.prompts[-1])
        # Generation is not validation: without a sandbox the draft says so.
        self.assertEqual(draft["verification"]["status"], "unavailable")
        self.assertIn("not configured", draft["verification"]["message"])

    def test_validate_runs_the_draft_in_the_sandbox_and_save_keeps_the_result(self):
        spec_id, draft = self.new_draft()
        self.runner = FakeRunner()
        checked = coding.verify_spec_draft(1, spec_id, {"question": {"test_cases": draft["test_cases"]}})["draft"]
        self.assertEqual(checked["verification"]["status"], "verified")
        self.assertEqual(len(self.store.by_source("custom_coding")), 0)  # validating adds nothing
        self.runner = None  # saving the unchanged draft does not need to execute again
        saved = coding.save_spec_question(1, spec_id, {"extend_duration": True, "time_limit_minutes": 20})
        question = self.store.by_source("custom_coding")[0]
        self.assertEqual(question["verification"]["status"], "verified")
        self.assertEqual(saved["counts"]["coding"], 2)
        self.assertEqual(saved["assessment"]["time_limit_minutes"], 110)
        self.assertFalse(coding_problems(question))

    def test_failing_reference_is_reported_and_blocks_publication(self):
        spec_id, _ = self.new_draft()
        self.runner = FakeRunner(stdout="wrong\n")
        checked = coding.verify_spec_draft(1, spec_id, {})["draft"]
        self.assertEqual(checked["verification"]["status"], "failed")
        self.assertTrue(any(not r["passed"] for r in checked["verification"]["results"]))
        coding.save_spec_question(1, spec_id, {})
        question = self.store.by_source("custom_coding")[0]
        self.assertIn("The reference solution fails one or more test cases.", coding_problems(question))

    def test_without_execution_the_saved_question_stays_unvalidated(self):
        spec_id, _ = self.new_draft()
        checked = coding.verify_spec_draft(1, spec_id, {})["draft"]
        self.assertEqual(checked["verification"]["status"], "unavailable")
        coding.save_spec_question(1, spec_id, {})
        problems = coding_problems(self.store.by_source("custom_coding")[0])
        self.assertTrue(any("could not be executed" in p for p in problems))
        check = assessment_service.publication_check(1)
        self.assertFalse(check["ready"])

    def test_editing_after_validation_makes_the_result_stale(self):
        spec_id, draft = self.new_draft()
        self.runner = FakeRunner()
        coding.verify_spec_draft(1, spec_id, {})
        self.runner = None
        tests = [dict(t) for t in draft["test_cases"]]
        tests[0]["expected_output"] = "999\n"
        coding.save_spec_question(1, spec_id, {"question": {"test_cases": tests}})
        question = self.store.by_source("custom_coding")[0]
        self.assertNotEqual(question.get("verification", {}).get("status"), "verified")
        self.assertTrue(coding_problems(question))

    def test_weights_and_threshold_edits_are_validated_and_saved(self):
        spec_id, draft = self.new_draft()
        tests = [{**t, "weight": 2.5 if i == 0 else 1} for i, t in enumerate(draft["test_cases"])]
        with self.assertRaisesRegex(AssessmentServiceError, "cannot exceed"):
            coding.save_spec_question(1, spec_id, {"question": {"test_cases": tests, "scoring": {"min_tests_passed": 30}}})
        with self.assertRaisesRegex(AssessmentServiceError, "Weight"):
            coding.save_spec_question(1, spec_id, {"question": {"test_cases": [{**tests[0], "weight": -1}, *tests[1:]]}})
        coding.save_spec_question(1, spec_id, {"question": {"test_cases": tests, "title": "Totals",
                                                            "scoring": {"min_tests_passed": 3, "min_score_percent": 70}}})
        q = self.store.by_source("custom_coding")[0]
        self.assertEqual((q["test_cases"][0]["weight"], q["scoring"]["min_tests_passed"], q["scoring"]["min_score_percent"], q["title"]),
                         (2.5, 3, 70, "Totals"))

    def test_any_number_of_coding_questions(self):
        for n in range(6):
            spec_id, _ = self.new_draft()
            coding.save_spec_question(1, spec_id, {})
        self.assertEqual(len(self.store.by_source("custom_coding")), 6)
        self.assertEqual(len({q["sort_order"] for q in self.store.get_questions_for_assessment(1)}), 37)


def coding_problems(question):
    from assessment.code_execution.coding_config import config_problems
    return config_problems(question)


if __name__ == "__main__":
    unittest.main()
