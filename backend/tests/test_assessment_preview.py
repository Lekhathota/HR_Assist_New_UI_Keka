"""Preview Assessment backend: question edits through the real routes, single-question regeneration."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask

from services import assessment_service as service
from tests.test_assessment_generation import JD, MCQ_TEXTS, SCENARIOS, _question

MCQ = {"id": 5, "assessment_id": 1, "question_type": "mcq", "question_text": "Pick the safest rollout plan for the release.",
       "options": ["Canary", "Big bang", "Skip tests", "Friday deploy"], "correct_answer": "Canary",
       "explanation": "Canary limits blast radius.", "points": 3, "sort_order": 4, "difficulty": "Hard", "skill_tag": "Python"}


class Store:
    def __init__(self, status="DRAFT"):
        self.assessment = {"id": 1, "jd_id": 20, "status": status, "candidate_email": "c@example.com"}
        self.questions = {5: copy.deepcopy(MCQ), 6: {**copy.deepcopy(MCQ), "id": 6, "question_text": MCQ_TEXTS[1], "sort_order": 5}}

    def get_question_by_id(self, qid):
        return copy.deepcopy(self.questions.get(int(qid)))

    def get_assessment_by_id(self, aid):
        return copy.deepcopy(self.assessment)

    def get_questions_for_assessment(self, aid):
        return copy.deepcopy(list(self.questions.values()))

    def update_question(self, qid, patch_doc):
        self.questions[int(qid)].update(copy.deepcopy(patch_doc))
        return True

    def count_questions_for_assessment(self, aid):
        return len(self.questions)

    def create_question(self, data):
        self.questions[99] = {**copy.deepcopy(data), "id": 99}
        return 99


class Base(unittest.TestCase):
    status = "DRAFT"

    def setUp(self):
        self.store = Store(self.status)
        self.stack = ExitStack()
        for name in ("get_question_by_id", "get_assessment_by_id", "get_questions_for_assessment", "update_question",
                     "count_questions_for_assessment", "create_question"):
            self.stack.enter_context(patch.object(service.assessment_repo, name, side_effect=getattr(self.store, name)))
        self.stack.enter_context(patch.object(service.db, "log_audit"))
        self.stack.enter_context(patch.object(service.db, "get_jd_by_id", return_value=dict(JD)))

    def tearDown(self):
        self.stack.close()


class FakeLLM:
    """Returns one replacement question per call; the first reply can be a duplicate to force a retry."""

    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def invoke(self, prompt, temperature=None):
        self.prompts.append(prompt)
        return self.replies.pop(0)


def one(text, qtype="MCQ", difficulty="Hard"):
    question = {**_question(0, text, qtype), "difficulty": difficulty}
    return json.dumps({"exam_title": "JD-Based Assessment", "job_title": "Python Developer", "experience_required": "3-5 years",
                       "total_questions": 1, "skills_covered": ["Python"], "questions": [question]})


class RegenerateTests(Base):
    def test_mcq_is_replaced_in_place_keeping_position_and_marks(self):
        llm = FakeLLM([one(MCQ_TEXTS[1]), one(SCENARIOS[7])])  # first reply repeats question 6
        with patch.object(service, "LLMService", return_value=llm):
            result = service.regenerate_question(5, actor="rec")
        row = self.store.questions[5]
        self.assertEqual((row["id"], row["sort_order"], row["points"], row["difficulty"]), (5, 4, 3, "Hard"))
        self.assertEqual(row["question_text"], SCENARIOS[7])
        self.assertEqual(len(row["options"]), 4)
        self.assertEqual(row["options"].count(row["correct_answer"]), 1)
        self.assertEqual(result["question"]["question_text"], SCENARIOS[7])
        self.assertIn("Section key: replace", llm.prompts[0])
        self.assertIn("Return exactly 1 questions: 1 MCQs (0 Medium/moderate and 1 Hard)", llm.prompts[0])
        self.assertIn("repeats an existing question", llm.prompts[1])  # feedback from the duplicate
        self.assertEqual(self.store.questions[6]["question_text"], MCQ_TEXTS[1])  # other questions untouched

    def test_failure_keeps_the_original_question(self):
        with patch.object(service, "LLMService", return_value=FakeLLM(["{}"] * 3)):
            with self.assertRaises(service.AssessmentServiceError) as ctx:
                service.regenerate_question(5)
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertEqual(self.store.questions[5], MCQ)

    def test_custom_coding_questions_use_their_own_prompt(self):
        self.store.questions[5].update(question_type="coding", source="custom_coding", coding_spec_id="s1")
        self.store.assessment["coding_specs"] = [{"id": "s1", "prompt": "Merge intervals", "difficulty": "Medium", "points": 15}]
        with patch("services.coding_question_service._generate_with_ai",
                   return_value={"question_text": "Merge overlapping intervals and print them.", "question_type": "coding",
                                 "correct_answer": "print(1)", "points": 15}) as generate:
            service.regenerate_question(5)
        self.assertEqual(generate.call_args.args[2]["prompt"], "Merge intervals")
        row = self.store.questions[5]
        self.assertEqual((row["question_text"], row["generation_prompt"], row["points"]), ("Merge overlapping intervals and print them.", "Merge intervals", 3))


class LockedTests(Base):
    status = "SENT"

    def test_published_questions_cannot_be_regenerated(self):
        with self.assertRaises(service.AssessmentServiceError) as ctx:
            service.regenerate_question(5)
        self.assertEqual(ctx.exception.status_code, 409)


class RouteTests(Base):
    def setUp(self):
        super().setUp()
        from routes import assessment_routes as routes

        app = Flask(__name__)
        app.register_blueprint(routes.assessment_bp)
        self.http = app.test_client()
        self.stack.enter_context(patch("services.auth_service.effective_user_id", return_value=7))
        self.stack.enter_context(patch.object(routes, "current_user", return_value={"id": 7, "username": "rec", "role": "recruiter"}))

    def test_mcq_edits_keep_explanation_and_difficulty(self):
        body = {"question_text": "Edited text for the rollout question.", "options": ["Canary", "Blue/green", "Skip", "Friday"],
                "correct_answer": "Blue/green", "explanation": "Instant rollback.", "difficulty": "Medium", "points": 4}
        response = self.http.put("/api/assessment/question/5", json=body)
        self.assertEqual(response.status_code, 200, response.get_json())
        row = self.store.questions[5]
        self.assertEqual((row["explanation"], row["difficulty"], row["correct_answer"], row["points"]),
                         ("Instant rollback.", "Medium", "Blue/green", 4))
        bad = self.http.put("/api/assessment/question/5", json={**body, "correct_answer": "Nope"})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("exactly one", bad.get_json()["error"])
        self.assertEqual(self.http.put("/api/assessment/question/5", json={"difficulty": "Extreme"}).status_code, 400)

    def test_new_mcq_with_explanation_is_accepted(self):
        response = self.http.post("/api/assessment/question", json={
            "assessment_id": 1, "question_type": "mcq", "question_text": "Which rollout keeps a rollback path?",
            "options": ["A1", "B1", "C1", "D1"], "correct_answer": "B1", "explanation": "B1 keeps it.", "difficulty": "Hard"})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual((self.store.questions[99]["explanation"], self.store.questions[99]["difficulty"]), ("B1 keeps it.", "Hard"))

    def test_regenerate_route(self):
        with patch.object(service, "LLMService", return_value=FakeLLM([one(SCENARIOS[8])])):
            response = self.http.post("/api/assessment/question/5/regenerate")
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["question"]["question_text"], SCENARIOS[8])


if __name__ == "__main__":
    unittest.main()
