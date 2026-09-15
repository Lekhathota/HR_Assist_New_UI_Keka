"""
Unit tests for the Assessment module (utilities, schemas, scoring).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from assessment.models import AssessmentStatus, QuestionType
from assessment.schemas import SchemaValidationError, validate_generate_payload, validate_save_answer_payload
from assessment.evaluation_service import evaluate_assessment
from assessment.evaluators.coding_evaluator import StubCodingEvaluator
from assessment.utilities import (
    assert_status_transition,
    generate_access_token,
    score_assessment,
    score_question,
)


class AssessmentUtilitiesTests(unittest.TestCase):
    def test_generate_access_token_is_uuid(self) -> None:
        token = generate_access_token()
        self.assertEqual(len(token), 36)
        self.assertEqual(token.count("-"), 4)

    def test_status_transition_draft_to_sent(self) -> None:
        assert_status_transition(AssessmentStatus.DRAFT, AssessmentStatus.SENT)

    def test_status_transition_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            assert_status_transition(AssessmentStatus.DRAFT, AssessmentStatus.PASSED)

    def test_score_mcq_correct(self) -> None:
        question = {
            "id": 1,
            "question_type": QuestionType.MCQ,
            "correct_answer": "B",
            "points": 10,
        }
        result = score_question(question, "B")
        self.assertTrue(result["is_correct"])
        self.assertEqual(result["points_earned"], 10)

    def test_score_mcq_incorrect(self) -> None:
        question = {
            "id": 1,
            "question_type": QuestionType.MCQ,
            "correct_answer": "B",
            "points": 10,
        }
        result = score_question(question, "A")
        self.assertFalse(result["is_correct"])
        self.assertEqual(result["points_earned"], 0)

    def test_score_assessment_aggregate(self) -> None:
        questions = [
            {"id": 1, "question_type": QuestionType.MCQ, "correct_answer": "A", "points": 10},
            {"id": 2, "question_type": QuestionType.MCQ, "correct_answer": "B", "points": 10},
        ]
        answers = {1: "A", 2: "C"}
        result = score_assessment(questions, answers)
        self.assertEqual(result["total_points"], 20)
        self.assertEqual(result["earned_points"], 10)
        self.assertEqual(result["score_percentage"], 50.0)


class AssessmentEvaluationTests(unittest.TestCase):
    def test_mcq_auto_scoring_passes_on_mcq_percentage(self) -> None:
        questions = [
            {"id": 1, "question_type": QuestionType.MCQ, "correct_answer": "A", "points": 10},
            {"id": 2, "question_type": QuestionType.MCQ, "correct_answer": "B", "points": 10},
            {"id": 3, "question_type": QuestionType.CODING, "correct_answer": "", "points": 20},
        ]
        answers = {1: "A", 2: "B", 3: "print('hello')"}
        result = evaluate_assessment(questions, answers, passing_score=70)
        self.assertEqual(result["mcq_percentage"], 100.0)
        self.assertTrue(result["passed"])
        self.assertEqual(result["pending_review_count"], 1)
        self.assertEqual(result["question_results"][2]["evaluation_status"], "pending_review")

    def test_coding_stub_awards_zero_points(self) -> None:
        questions = [{"id": 1, "question_type": QuestionType.CODING, "points": 20}]
        result = evaluate_assessment(
            questions,
            {1: "def solve(): pass"},
            passing_score=70,
            coding_evaluator=StubCodingEvaluator(),
        )
        self.assertEqual(result["earned_points"], 0)
        self.assertEqual(result["pending_review_count"], 1)


class AssessmentSchemaTests(unittest.TestCase):
    def test_validate_generate_payload(self) -> None:
        payload = validate_generate_payload({"candidate_id": 1, "jd_id": 2})
        self.assertEqual(payload["candidate_id"], 1)
        self.assertEqual(payload["jd_id"], 2)

    def test_validate_generate_payload_missing_fields(self) -> None:
        with self.assertRaises(SchemaValidationError):
            validate_generate_payload({})

    def test_validate_save_answer_payload(self) -> None:
        payload = validate_save_answer_payload(
            {"token": "abc", "question_id": 1, "answer": "yes"}
        )
        self.assertEqual(payload["token"], "abc")


if __name__ == "__main__":
    unittest.main()
