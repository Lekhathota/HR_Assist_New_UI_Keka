"""Regression coverage: MCQ correct answers are not pinned to option A, and
pass/fail uses the assessment's configured passing score on the reported score."""
import random
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assessment.evaluation_service import evaluate_assessment
from assessment.generation import normalized_jd, shuffle_mcq_options, validate_exam
from tests.test_assessment_generation import JD, exam

OPTIONS = ["Correct decision", "Distractor one", "Distractor two", "Distractor three"]


def model_exam_with_answer_first():
    """What the model tends to return: the correct option always listed first."""
    data = exam()
    for question in data["questions"][:10]:
        question["options"] = list(OPTIONS)
        question["correct_answer"] = OPTIONS[0]
    return data


class AnswerPositionTests(unittest.TestCase):
    def test_correct_option_moves_off_a_and_stays_mapped(self):
        positions = Counter()
        for _ in range(30):
            rows = validate_exam(model_exam_with_answer_first(), normalized_jd(JD), total=14)
            mcqs = [r for r in rows if r["question_type"] == "mcq"]
            self.assertEqual(len(mcqs), 10)
            slots = []
            for row in mcqs:
                self.assertEqual(sorted(row["options"]), sorted(OPTIONS))
                self.assertEqual(row["options"].count(row["correct_answer"]), 1)
                self.assertEqual(row["correct_answer"], "Correct decision")
                slots.append(row["options"].index(row["correct_answer"]))
            positions.update(slots)
            # Every exam spreads answers across A-D (3/3/2/2), never all A.
            self.assertEqual(sorted(Counter(slots).values()), [2, 2, 3, 3])
        self.assertEqual(set(positions), {0, 1, 2, 3})

    def test_letter_answer_resolves_before_shuffle(self):
        data = exam()
        data["questions"][0]["options"] = ["Validate input", "Handle absent optional field", "Drop the request", "Disable parsing"]
        data["questions"][0]["correct_answer"] = "C"
        row = validate_exam(data, normalized_jd(JD), total=14)[0]
        self.assertEqual(row["correct_answer"], "Drop the request")
        self.assertIn("Drop the request", row["options"])

    def test_shuffle_is_not_a_fixed_cycle(self):
        rows = [{"question_type": "mcq", "options": list(OPTIONS), "correct_answer": OPTIONS[0]} for _ in range(10)]
        orders = {tuple(r["options"].index(r["correct_answer"]) for r in shuffle_mcq_options(
            [dict(r, options=list(r["options"])) for r in rows], random.Random(seed))) for seed in range(20)}
        self.assertGreater(len(orders), 15)
        self.assertNotIn((0, 1, 2, 3, 0, 1, 2, 3, 0, 1), orders)


def ten_mcqs_after_shuffle():
    rows = [{"question_type": "mcq", "options": list(OPTIONS), "correct_answer": OPTIONS[0],
             "points": 10} for _ in range(10)]
    rows = shuffle_mcq_options(rows, random.Random(7))
    for index, row in enumerate(rows):
        row["id"] = index + 1
    return rows


class ScoringTests(unittest.TestCase):
    def test_selecting_bcd_correct_answers_earns_credit_and_a_does_not(self):
        rows = ten_mcqs_after_shuffle()
        non_a = [r for r in rows if r["options"].index(r["correct_answer"]) != 0]
        self.assertTrue(non_a)
        for row in non_a:
            right = evaluate_assessment([row], {row["id"]: row["correct_answer"]}, passing_score=70)
            wrong = evaluate_assessment([row], {row["id"]: row["options"][0]}, passing_score=70)
            self.assertEqual(right["earned_points"], 10)
            self.assertEqual(wrong["earned_points"], 0)

    def test_score_uses_question_points(self):
        rows = ten_mcqs_after_shuffle()
        rows[0]["points"] = 30
        answers = {r["id"]: r["correct_answer"] for r in rows[:4]}
        result = evaluate_assessment(rows, answers, passing_score=70)
        self.assertEqual((result["earned_points"], result["total_points"]), (60, 120))
        self.assertEqual(result["score_percentage"], 50.0)

    def test_configured_passing_score_boundaries(self):
        cases = {68: False, 69: False, 70: True, 71: True}
        for percent, expected in cases.items():
            questions = [{"id": 1, "question_type": "mcq", "correct_answer": "x", "points": percent},
                         {"id": 2, "question_type": "mcq", "correct_answer": "y", "points": 100 - percent}]
            result = evaluate_assessment(questions, {1: "x", 2: "wrong"}, passing_score=70)
            self.assertEqual(result["score_percentage"], float(percent))
            self.assertIs(result["passed"], expected, percent)

    def test_threshold_comes_from_configuration(self):
        questions = [{"id": 1, "question_type": "mcq", "correct_answer": "x", "points": 68},
                     {"id": 2, "question_type": "mcq", "correct_answer": "y", "points": 32}]
        answers = {1: "x"}
        self.assertTrue(evaluate_assessment(questions, answers, passing_score=60)["passed"])
        self.assertFalse(evaluate_assessment(questions, answers, passing_score=70)["passed"])

    def test_displayed_68_89_with_pending_coding_is_fail(self):
        # 62 / 90 = 68.89%: MCQs all right, coding still pending review.
        questions = [{"id": i, "question_type": "mcq", "correct_answer": "x", "points": 31} for i in (1, 2)]
        questions.append({"id": 3, "question_type": "coding", "points": 28})
        result = evaluate_assessment(questions, {1: "x", 2: "x", 3: "def solve(): ..."}, passing_score=70)
        self.assertEqual(result["score_percentage"], 68.89)
        self.assertEqual(result["mcq_percentage"], 100.0)
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
