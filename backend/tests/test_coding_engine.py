"""Coding assessment engine: configuration, real execution, test-case scoring, qualification,
section scoring, publishing and versioning.

Programs are really executed (Python, JavaScript, Java) through tests/local_runner.py, a
test-only backend with the Judge0 runner's interface. The Judge0 HTTP client is exercised
with recorded Judge0 responses. Persistence uses an in-memory store with the repository's
function signatures.
"""
from __future__ import annotations

import base64
import copy
import json
import sys
import unittest
from contextlib import ExitStack
from datetime import timedelta
from enum import Enum
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assessment.code_execution import coding_config, grader, verification
from assessment.code_execution.judge0 import ExecutionLimits, ExecutionResult, ExecutionUnavailable, Judge0Runner
from assessment.evaluation_service import evaluate_assessment, normalize_scoring_policy
from assessment.evaluators.coding_evaluator import AutoCodingEvaluator
from assessment.utilities import candidate_question_payload, generate_access_token, utc_now
from services import assessment_service as service
from tests.local_runner import LocalSubprocessRunner, available

# Sum of n integers. Two public samples, three hidden tests.
TESTS = [
    {"id": "t1", "name": "sample small", "hidden": False, "input": "3\n1 2 3\n", "expected_output": "6\n"},
    {"id": "t2", "name": "sample single", "hidden": False, "input": "1\n5\n", "expected_output": "5\n"},
    {"id": "t3", "name": "negatives", "hidden": True, "input": "4\n-1 -2 -3 -4\n", "expected_output": "-10\n"},
    {"id": "t4", "name": "empty", "hidden": True, "input": "0\n\n", "expected_output": "0\n"},
    {"id": "t5", "name": "large values", "hidden": True, "input": "2\n1000000000 1000000000\n", "expected_output": "2000000000\n"},
]
REFERENCE = "import sys\nd = sys.stdin.read().split()\nn = int(d[0])\nprint(sum(int(x) for x in d[1:1 + n]))\n"
PROGRAMS = {
    "correct_loop": ("python", "import sys\nd = sys.stdin.read().split()\nt = 0\nfor i in range(int(d[0])):\n    t += int(d[1 + i])\nprint(t)\n"),
    "correct_js": ("javascript", "const d = require('fs').readFileSync(0, 'utf8').trim().split(/\\s+/).map(Number);\n"
                                 "let t = 0; for (let i = 1; i <= d[0]; i++) t += d[i];\nconsole.log(String(t));\n"),
    "correct_java": ("java", "import java.util.*;\npublic class Main {\n  public static void main(String[] a) {\n"
                             "    Scanner s = new Scanner(System.in); int n = s.nextInt(); long t = 0;\n"
                             "    for (int i = 0; i < n; i++) t += s.nextLong();\n    System.out.println(t);\n  }\n}\n"),
    "one_test": ("python", "print(6)\n"),
    "samples_only": ("python", "import sys\nd = [int(x) for x in sys.stdin.read().split()]\n"
                               "print(sum(d[1:]) if d[0] > 0 and min(d[1:]) > 0 and max(d[1:]) < 100 else 'unknown')\n"),
    "large_only": ("python", "print(2000000000)\n"),
    "runtime_error": ("python", "raise ValueError('boom')\n"),
    "timeout": ("python", "while True:\n    pass\n"),
    "huge_output": ("python", "print('x' * 200000)\n"),
    "compile_error": ("java", "public class Main { public static void main(String[] a) { int x = 1 } }\n"),
}


def question(**over):
    q = {"id": 7, "assessment_id": 1, "question_type": "coding", "points": 10, "title": "Sum of numbers",
         "question_text": "Read n and then n integers and print their sum. Handle negative, empty and large inputs.",
         "correct_answer": REFERENCE, "reference_language": "python", "test_cases": copy.deepcopy(TESTS),
         "allowed_languages": ["python", "javascript", "java"], "default_language": "python",
         "time_limit_seconds": 1.0, "memory_limit_mb": 128}
    q.update(over)
    return q


def run(name, q=None, runner=None):
    language, code = PROGRAMS[name]
    with patch.object(grader.Judge0Runner, "from_env", return_value=runner or LocalSubprocessRunner()):
        return AutoCodingEvaluator().evaluate(q or question(), code, language).to_dict()


class ReferenceValidationTests(unittest.TestCase):
    """1. The reference solution is executed against every test before the question can be approved."""

    def test_reference_solution_passes_all_test_cases(self):
        result, _ = verification.verify_question(question(), runner=LocalSubprocessRunner())
        self.assertEqual(result["status"], "verified")
        self.assertEqual(sum(r["passed"] for r in result["results"]), 5)

    @unittest.skipUnless(available("java") and available("javascript"), "needs node and a JDK")
    def test_every_language_reference_must_pass(self):
        q = question(reference_solutions={"java": PROGRAMS["correct_java"][1], "javascript": PROGRAMS["correct_js"][1]})
        result, _ = verification.verify_question(q, runner=LocalSubprocessRunner())
        self.assertEqual(result["status"], "verified")
        self.assertEqual({e["language"]: e["passed"] for e in result["languages"]}, {"python": 5, "java": 5, "javascript": 5})

    def test_a_failing_reference_marks_the_question_invalid_and_shows_the_failing_test(self):
        q = question()
        q["test_cases"][2]["expected_output"] = "999\n"
        result, _ = verification.verify_question(q, runner=LocalSubprocessRunner())
        self.assertEqual(result["status"], "failed")
        failing = [r for r in result["results"] if not r["passed"]]
        self.assertEqual([(r["id"], r["status"], r["actual"].strip()) for r in failing], [("t3", "wrong_answer", "-10")])
        q["verification"] = result
        self.assertIn("The reference solution fails one or more test cases.", coding_config.config_problems(q))

    def test_changing_limits_or_comparison_requires_verifying_again(self):
        q = question()
        q["verification"], _ = verification.verify_question(q, runner=LocalSubprocessRunner())
        self.assertEqual(verification.verification_view(q)["status"], "verified")
        for change in ({"time_limit_seconds": 3.0}, {"comparison": "tokens"}, {"reference_solutions": {"java": "x"}}):
            with self.subTest(change=change):
                self.assertEqual(verification.verification_view({**q, **change})["status"], "not_verified")


class CandidateScoringTests(unittest.TestCase):
    """2-7. Marks come from executed tests, never from comparing source code."""

    def test_candidate_passing_every_test_gets_full_marks_and_qualifies(self):
        row = run("correct_loop")
        meta = row["metadata"]
        self.assertEqual((row["points_earned"], meta["tests_passed"], meta["result_status"], meta["qualification"]),
                         (10, 5, "passed", "qualified"))
        self.assertTrue(row["is_correct"])

    def test_partial_credit_table_for_a_10_mark_question_with_5_tests(self):
        # 0..5 tests passed -> 0, 2, 4, 6, 8, 10 marks (equal weights, partial credit on).
        for passed in range(6):
            outcomes = [{"id": f"t{i + 1}", "passed": i < passed, "status": "passed" if i < passed else "failed"} for i in range(5)]
            with self.subTest(passed=passed):
                self.assertEqual(coding_config.score_outcomes(question(), outcomes)["marks"], passed * 2)

    def test_one_test_passed_earns_partial_credit(self):
        row = run("one_test")
        self.assertEqual((row["points_earned"], row["metadata"]["tests_passed"], row["metadata"]["result_status"]),
                         (2, 1, "partially_passed"))

    def test_two_tests_passed_qualifies_when_the_criteria_allow_it(self):
        q = question(scoring={"min_tests_passed": 2, "min_score_percent": 40, "partial_credit": True, "require_mandatory": True})
        meta = run("samples_only", q)["metadata"]
        self.assertEqual((meta["tests_passed"], meta["marks"], meta["result_status"], meta["qualification"]),
                         (2, 4, "partially_passed", "qualified"))

    def test_two_tests_passed_does_not_qualify_under_a_higher_threshold(self):
        for scoring in ({"min_tests_passed": 3, "min_score_percent": 40}, {"min_tests_passed": 2, "min_score_percent": 50}):
            with self.subTest(scoring=scoring):
                meta = run("samples_only", question(scoring=scoring))["metadata"]
                self.assertEqual((meta["tests_passed"], meta["qualification"]), (2, "not_qualified"))
                self.assertIn(False, [c["met"] for c in meta["qualification_checks"]])

    def test_passing_samples_but_failing_hidden_tests_does_not_qualify(self):
        meta = run("samples_only")["metadata"]
        self.assertEqual((meta["visible_passed"], meta["hidden_passed"], meta["hidden_total"]), (2, 0, 3))
        self.assertEqual(meta["qualification"], "not_qualified")  # default criteria: at least 50% of the marks
        hidden = [t for t in meta["tests"] if t["hidden"]]
        self.assertTrue(all(t["input"] is None and t["expected"] is None and t["actual"] is None for t in hidden))

    @unittest.skipUnless(available("java") and available("javascript"), "needs node and a JDK")
    def test_different_correct_algorithms_and_languages_get_full_credit(self):
        for name in ("correct_loop", "correct_js", "correct_java"):
            with self.subTest(program=name):
                self.assertEqual(run(name)["points_earned"], 10)

    def test_weighted_tests_and_mandatory_tests(self):
        q = question()
        for case, weight in zip(q["test_cases"], (1, 1, 1, 1, 6)):
            case["weight"] = weight
        self.assertEqual(run("large_only", q)["points_earned"], 6)  # only the weight-6 test passes
        q["test_cases"][4]["mandatory"] = True
        meta = run("samples_only", q)["metadata"]
        self.assertEqual(meta["qualification"], "not_qualified")
        self.assertEqual(meta["mandatory_failed"], ["large values"])

    def test_all_or_nothing_when_partial_credit_is_off(self):
        q = question(scoring={"partial_credit": False})
        self.assertEqual(run("one_test", q)["points_earned"], 0)
        self.assertEqual(run("correct_loop", q)["points_earned"], 10)


class ExecutionFailureTests(unittest.TestCase):
    """8. Compilation, runtime, timeout and resource-limit failures are recorded consistently."""

    @unittest.skipUnless(available("java"), "needs a JDK")
    def test_compilation_error(self):
        row = run("compile_error")
        meta = row["metadata"]
        self.assertEqual((row["points_earned"], meta["result_status"], meta["error_kind"], meta["compile_status"]),
                         (0, "execution_error", "compile_error", "compile_error"))
        self.assertEqual(row["evaluation_status"], "scored")  # the candidate's error: scored 0, not retried
        self.assertTrue(any("error" in (t["error"] or "") for t in meta["tests"] if not t["hidden"]))

    def test_runtime_error(self):
        meta = run("runtime_error")["metadata"]
        self.assertEqual((meta["marks"], meta["error_kind"]), (0, "runtime_error"))
        self.assertTrue(all(t["status"] == "runtime_error" for t in meta["tests"]))
        self.assertIn("boom", meta["tests"][0]["error"])

    def test_timeout(self):
        meta = run("timeout")["metadata"]
        self.assertEqual({t["status"] for t in meta["tests"]}, {"time_limit"})
        self.assertEqual(meta["marks"], 0)

    def test_output_limit(self):
        meta = run("huge_output")["metadata"]
        self.assertEqual({t["status"] for t in meta["tests"]}, {"output_limit"})

    def test_judge0_statuses_and_limits(self):
        runner = Judge0Runner("https://judge0.example.com", auth_token="t")
        enc = lambda text: base64.b64encode(text.encode()).decode()
        sent = {}

        def fake_request(method, path, body=None):
            if method == "POST":
                sent.update(body["submissions"][0])
                return [{"token": str(i)} for i in range(5)]
            return {"submissions": [
                {"token": "0", "status": {"id": 3}, "stdout": enc("6\n"), "time": "0.01", "memory": 900},
                {"token": "1", "status": {"id": 5}},
                {"token": "2", "status": {"id": 7}, "memory": 65_000},      # killed at the 64 MB cap
                {"token": "3", "status": {"id": 8}},                        # SIGXFSZ: output file too large
                {"token": "4", "status": {"id": 13, "description": "Internal Error"}},
            ]}

        limits = ExecutionLimits.for_question({"time_limit_seconds": 1.5, "memory_limit_mb": 64})
        with patch.object(runner, "_request", side_effect=fake_request):
            results = runner.run("python", "x", [{"id": f"t{i}", "input": ""} for i in range(5)], limits=limits)
        self.assertEqual([r.status for r in results], ["ok", "time_limit", "memory_limit", "output_limit", "error"])
        self.assertEqual((sent["cpu_time_limit"], sent["memory_limit"], sent["enable_network"]), (1.5, 65_536, False))
        self.assertGreaterEqual(sent["wall_time_limit"], 3.75)


class InfrastructureFailureTests(unittest.TestCase):
    """14. A sandbox failure is never recorded as a candidate failure."""

    class Broken:
        def __init__(self, mode):
            self.mode = mode

        def default_limits(self):
            return ExecutionLimits()

        def run(self, language, source, cases, limits=None):
            if self.mode == "unreachable":
                raise ExecutionUnavailable("Judge0 is unreachable")
            return [ExecutionResult(c["id"], "error", stderr="Internal Error") for c in cases]

    def test_unreachable_or_internal_errors_give_a_retryable_execution_error(self):
        for mode in ("unreachable", "internal"):
            with self.subTest(mode=mode):
                row = run("correct_loop", runner=self.Broken(mode))
                self.assertEqual(row["evaluation_status"], "execution_error")
                self.assertEqual((row["metadata"]["error_kind"], row["metadata"]["qualification"]), ("infrastructure", "pending"))
                self.assertTrue(row["metadata"]["retryable"])

    def test_assessment_with_an_infrastructure_error_is_not_failed(self):
        mcq = {"id": 1, "question_type": "mcq", "correct_answer": "A", "points": 10}
        with patch.object(grader.Judge0Runner, "from_env", return_value=self.Broken("unreachable")):
            result = evaluate_assessment([mcq, question()], {1: "A", 7: "print(1)"}, passing_score=50,
                                         languages_by_question={7: "python"})
        self.assertTrue(result["needs_retry"])
        self.assertFalse(result["passed"])
        self.assertEqual(service._final_status(result), "COMPLETED")


class ConfigurationValidationTests(unittest.TestCase):
    """10. Invalid weights, thresholds and limits are rejected by the backend."""

    def test_invalid_configuration_is_rejected(self):
        for data, message in (
            ({"scoring": {"min_score_percent": 150}}, "between 0 and 100"),
            ({"scoring": {"min_tests_passed": -1}}, "Minimum tests passed"),
            ({"scoring": {"partial_credit": "yes"}}, "true or false"),
            ({"time_limit_seconds": 0}, "Time limit"),
            ({"memory_limit_mb": 4096}, "Memory limit"),
            ({"points": 0}, "Maximum marks"),
            ({"allowed_languages": []}, "at least one"),
            ({"allowed_languages": ["cobol"]}, "Unsupported language"),
            ({"comparison": "fuzzy"}, "Output comparison"),
            ({"difficulty": "Extreme"}, "Difficulty"),
        ):
            with self.subTest(data=data), self.assertRaisesRegex(ValueError, message):
                coding_config.normalize_config("coding", data, question())

    def test_invalid_test_weights_are_rejected(self):
        for weight in (0, -2, 1000, "heavy"):
            with self.subTest(weight=weight), self.assertRaisesRegex(ValueError, "Weight"):
                coding_config.normalize_case_scoring([{"id": "t1"}], [{"weight": weight}])

    def test_invalid_section_weights_are_rejected(self):
        for policy, message in (({"section_weights": {"mcq": 50, "coding": 60}}, "add up to 100"),
                                ({"section_weights": {"mcq": -10, "coding": 110}}, "between 0 and 100"),
                                ({"section_weights": {"essay": 100}}, "mcq and coding"),
                                ({"min_coding_score": 101}, "between 0 and 100")):
            with self.subTest(policy=policy), self.assertRaisesRegex(ValueError, message):
                normalize_scoring_policy(policy)


class SectionScoringTests(unittest.TestCase):
    """11. MCQ and coding sections are scored separately and combined with configurable weights."""

    def setUp(self):
        self.mcqs = [{"id": 100 + i, "question_type": "mcq", "correct_answer": "A", "points": 1} for i in range(30)]

    def evaluate(self, mcq_right, program, policy, passing=60):
        answers = {100 + i: ("A" if i < mcq_right else "B") for i in range(30)}
        answers[7] = PROGRAMS[program][1]
        with patch.object(grader.Judge0Runner, "from_env", return_value=LocalSubprocessRunner()):
            return evaluate_assessment(self.mcqs + [question()], answers, passing_score=passing,
                                       languages_by_question={7: "python"}, scoring_policy=policy)

    def test_weighted_40_60_combination(self):
        result = self.evaluate(24, "samples_only", {"section_weights": {"mcq": 40, "coding": 60}})
        self.assertEqual((result["mcq_percentage"], result["coding_percentage"]), (80.0, 40.0))
        self.assertEqual(result["score_percentage"], 56.0)  # 0.4 * 80 + 0.6 * 40
        self.assertEqual(result["pass_basis"], "weighted")
        self.assertFalse(result["passed"])

    def test_points_based_when_no_weights_are_set(self):
        result = self.evaluate(24, "samples_only", None)
        self.assertEqual(result["score_percentage"], round((24 + 4) / 40 * 100, 2))
        self.assertEqual(result["pass_basis"], "overall")

    def test_high_mcq_score_cannot_override_a_mandatory_coding_requirement(self):
        policy = {"section_weights": {"mcq": 70, "coding": 30}, "coding_section_mandatory": True, "min_coding_score": 60,
                  "require_coding_qualification": True}
        result = self.evaluate(30, "samples_only", policy, passing=50)
        self.assertGreaterEqual(result["score_percentage"], 50)  # 70 + 12 = 82% overall
        self.assertFalse(result["passed"])
        self.assertEqual({c["rule"]: c["met"] for c in result["qualification_checks"]},
                         {"overall": True, "min_coding_score": False, "coding_qualification": False})
        self.assertTrue(self.evaluate(30, "correct_loop", policy, passing=50)["passed"])

    def test_advisory_coding_threshold_when_coding_is_not_mandatory(self):
        policy = {"section_weights": {"mcq": 70, "coding": 30}, "min_coding_score": 60}
        self.assertTrue(self.evaluate(30, "samples_only", policy, passing=50)["passed"])


class MemoryStore:
    """In-memory stand-in for assessment.repository (same function names and behaviour)."""

    def __init__(self, questions, status="DRAFT"):
        self.assessments = {1: {"id": 1, "candidate_id": 10, "jd_id": 20, "status": status, "passing_score": 50,
                                "time_limit_minutes": 60, "title": "Backend exam", "candidate_email": "c@example.com"}}
        self.questions = {q["id"]: copy.deepcopy(q) for q in questions}
        self.answers, self.results, self.attempts, self.versions = {}, {}, [], []

    def get_assessment_by_id(self, aid):
        return copy.deepcopy(self.assessments.get(int(aid)))

    def update_assessment(self, aid, patch_doc):
        # MongoDB stores an enum status as its plain string value.
        self.assessments[int(aid)].update({k: (v.value if isinstance(v, Enum) else copy.deepcopy(v)) for k, v in patch_doc.items()})
        return True

    def get_questions_for_assessment(self, aid):
        return copy.deepcopy(sorted(self.questions.values(), key=lambda q: (q.get("sort_order", 0), q["id"])))

    def get_question_by_id(self, qid):
        return copy.deepcopy(self.questions.get(int(qid)))

    def update_question(self, qid, patch_doc):
        self.questions[int(qid)].update(copy.deepcopy(patch_doc))
        return True

    def update_question_if_unchanged(self, qid, expected, patch_doc):
        return self.update_question(qid, patch_doc)

    def count_questions_for_assessment(self, aid):
        return len(self.questions)

    def upsert_candidate_answer(self, aid, qid, answer, *, is_final=False, language=None):
        self.answers[int(qid)] = {"question_id": int(qid), "answer": answer, "language": language, "is_final": is_final}
        return int(qid)

    def get_answers_for_assessment(self, aid):
        return copy.deepcopy(list(self.answers.values()))

    def complete_candidate_attempt(self, aid):
        if self.assessments[int(aid)]["status"] != "IN_PROGRESS":
            return False
        self.assessments[int(aid)]["status"] = "COMPLETED"
        return True

    def mark_answers_final(self, aid):
        for row in self.answers.values():
            row["is_final"] = True

    def upsert_assessment_result(self, data):
        from assessment.repository import _result_document

        self.results[int(data["assessment_id"])] = {"id": 1, **json.loads(json.dumps(_result_document(data), default=str))}
        return 1

    def get_result_by_assessment_id(self, aid):
        return copy.deepcopy(self.results.get(int(aid)))

    def record_code_attempt(self, data):
        self.attempts.append(copy.deepcopy(data))

    def get_code_attempts(self, aid):
        return copy.deepcopy(self.attempts)

    def create_assessment_version(self, data):
        self.versions.append(copy.deepcopy(data))
        return data["version"]

    def get_assessment_versions(self, aid):
        return copy.deepcopy(self.versions)

    def activate_assessment(self, aid, expected, patch_doc):
        if self.assessments[int(aid)]["status"] != getattr(expected, "value", expected):
            return False
        return self.update_assessment(aid, patch_doc)

    def push_delivery_event(self, aid, event):
        self.assessments[int(aid)].setdefault("delivery_history", []).append(dict(event))

    def return_assessment_to_draft(self, aid):
        row = self.assessments[int(aid)]
        if row["status"] != "SENT" or row.get("started_at"):
            return False
        row.update(status="DRAFT", approval=None)
        return True


class LifecycleTests(unittest.TestCase):
    """9, 12, 13: publishing gate, persisted submissions, immutable published versions."""

    def setUp(self):
        self.mcq = {"id": 1, "assessment_id": 1, "question_type": "mcq", "question_text": "Pick A", "options": ["A", "B", "C", "D"],
                    "correct_answer": "A", "explanation": "A is right.", "points": 10, "sort_order": 0}
        self.store = MemoryStore([self.mcq, {**question(), "sort_order": 1}])
        self.stack = ExitStack()
        for name in [n for n in dir(MemoryStore) if not n.startswith("_")]:
            self.stack.enter_context(patch.object(service.assessment_repo, name, side_effect=getattr(self.store, name)))
        for name in ("log_audit", "update_candidate"):
            self.stack.enter_context(patch.object(service.db, name))
        self.stack.enter_context(patch.object(service.db, "get_jd_by_id", return_value={"id": 20, "title": "Backend", "client_id": 5}))
        self.stack.enter_context(patch.object(service.db, "get_client_by_id", return_value={"id": 5, "name": "Acme"}))
        self.stack.enter_context(patch("services.hiring_process_service.advance_after_assessment"))
        self.runner = LocalSubprocessRunner()
        self.stack.enter_context(patch.object(verification.Judge0Runner, "from_env", side_effect=lambda: self.runner))
        self.stack.enter_context(patch.object(grader.Judge0Runner, "from_env", side_effect=lambda: self.runner))
        self.sent = self.stack.enter_context(patch.object(service, "send_email"))
        self.token = generate_access_token()
        link = f"https://shimento.org.com/assessment/{self.token}"
        self.stack.enter_context(patch.object(service, "_prepare_assessment_send", side_effect=lambda aid, **kw: (
            self.store.get_assessment_by_id(aid), self.store.assessments[aid]["status"], self.token,
            utc_now() + timedelta(days=7), link, "hr@example.com", "c@example.com")))

    def tearDown(self):
        self.stack.close()

    def send(self):
        return service.send_assessment(1, recruiter={"username": "rec"}, confirm=True)

    def test_invalid_or_missing_test_cases_prevent_publication(self):
        check = service.publication_check(1)
        self.assertFalse(check["ready"])  # never verified
        self.assertIn("not been verified", " ".join(check["questions"][0]["problems"]))
        with self.assertRaises(service.AssessmentServiceError) as ctx:
            service.approve_assessment(1, actor="rec")
        self.assertEqual(ctx.exception.status_code, 409)
        # Hidden tests removed: still invalid even with a passing reference.
        visible_only = [dict(c) for c in TESTS if not c["hidden"]]
        config = service.save_reference_config(7, {"reference_solution": REFERENCE, "test_cases": visible_only, "verify": True})
        self.assertEqual(config["verification"]["status"], "verified")
        self.assertIn("Add at least one hidden test case.", config["problems"])
        with self.assertRaises(service.AssessmentServiceError):
            self.send()
        self.sent.assert_not_called()

    def test_invalid_thresholds_are_rejected_on_save(self):
        with self.assertRaisesRegex(service.AssessmentServiceError, "cannot exceed"):
            service.save_reference_config(7, {"reference_solution": REFERENCE, "test_cases": TESTS,
                                              "config": {"scoring": {"min_tests_passed": 6}}})
        with self.assertRaisesRegex(service.AssessmentServiceError, "Weight"):
            service.save_reference_config(7, {"reference_solution": REFERENCE, "test_cases": [{**TESTS[0], "weight": -1}] + TESTS[1:]})

    def configure_and_approve(self):
        config = service.save_reference_config(7, {
            "reference_solution": REFERENCE, "test_cases": TESTS, "verify": True,
            "config": {"scoring": {"min_tests_passed": 2, "min_score_percent": 40}, "time_limit_seconds": 1}})
        self.assertEqual((config["verification"]["status"], config["problems"]), ("verified", []))
        self.assertEqual(config["client"], {"id": 5, "name": "Acme"})
        check = service.approve_assessment(1, actor="rec")
        self.assertTrue(check["approval"]["current"])

    def test_send_requires_a_current_approval_and_publishes_a_version(self):
        self.configure_and_approve()
        service.save_reference_config(7, {"reference_solution": REFERENCE, "test_cases": TESTS, "verify": True,
                                          "config": {"points": 20}})  # changed after approval
        with self.assertRaisesRegex(service.AssessmentServiceError, "approve"):
            self.send()
        service.approve_assessment(1, actor="rec")
        self.send()
        self.assertEqual(self.store.assessments[1]["status"], "SENT")
        self.assertEqual([v["version"] for v in self.store.versions], [1])
        self.assertEqual(self.store.versions[0]["questions"][1]["points"], 20)

    def test_draft_edits_do_not_change_a_published_version(self):
        self.configure_and_approve()
        self.send()
        published = copy.deepcopy(self.store.versions[0])
        with self.assertRaises(service.AssessmentServiceError):  # a published assessment cannot be edited
            service.save_reference_config(7, {"reference_solution": REFERENCE, "test_cases": TESTS, "config": {"points": 50}})
        service.return_to_draft(1, actor="rec")
        service.save_reference_config(7, {"reference_solution": REFERENCE, "test_cases": TESTS[:4], "verify": True,
                                          "config": {"points": 50}})
        self.assertEqual(self.store.versions[0], published)
        self.assertEqual(self.store.versions[0]["questions"][1]["points"], 10)
        self.assertEqual(len(self.store.versions[0]["questions"][1]["test_cases"]), 5)
        service.approve_assessment(1, actor="rec")
        self.send()
        self.assertEqual([v["version"] for v in self.store.versions], [1, 2])
        self.assertEqual(self.store.versions[1]["questions"][1]["points"], 50)

    def test_started_assessment_cannot_return_to_draft(self):
        self.configure_and_approve()
        self.send()
        self.store.assessments[1]["started_at"] = utc_now()
        with self.assertRaises(service.AssessmentServiceError):
            service.return_to_draft(1)

    def start(self):
        self.store.assessments[1].update(status="IN_PROGRESS", started_at=utc_now())
        self.stack.enter_context(patch.object(service, "_resolve_token_assessment",
                                              side_effect=lambda token, **kw: self.store.get_assessment_by_id(1)))

    def test_submission_results_and_attempts_persist_after_refresh(self):
        self.configure_and_approve()
        self.send()
        self.start()
        self.stack.enter_context(patch.object(service.assessment_repo, "consume_code_run", return_value=True))
        sample_run = service.run_candidate_code(self.token, 7, PROGRAMS["samples_only"][1], "python")
        self.assertEqual((sample_run["passed"], sample_run["total"]), (2, 2))  # samples only
        service.save_answer(self.token, 7, PROGRAMS["samples_only"][1], "python")
        service.save_answer(self.token, 1, "A")
        service.submit_assessment(self.token)

        refreshed = service.get_assessment_result(1)["result"]  # what the results page loads after a reload
        coding = next(r for r in refreshed["question_results"] if r["question_id"] == 7)
        self.assertEqual((coding["points_earned"], coding["metadata"]["tests_passed"], coding["metadata"]["qualification"]),
                         (4, 2, "qualified"))
        self.assertEqual(refreshed["status"], "PASSED")  # (10 + 4) / 20 = 70% >= 50%
        self.assertEqual(refreshed["assessment_version"], 1)
        self.assertEqual(self.store.answers[7]["language"], "python")
        attempts = service.get_code_attempts(1)["attempts"]
        self.assertEqual([a["kind"] for a in attempts], ["run", "submit"])
        self.assertEqual((attempts[1]["marks"], attempts[1]["qualification"]), (4, "qualified"))
        public = candidate_question_payload(self.store.questions[7])
        for secret in ("correct_answer", "test_cases", "scoring", "reference_solutions"):
            self.assertNotIn(secret, public)

    def test_infrastructure_failure_waits_for_a_regrade_instead_of_failing(self):
        self.configure_and_approve()
        self.send()
        self.start()
        service.save_answer(self.token, 7, PROGRAMS["correct_loop"][1], "python")
        service.save_answer(self.token, 1, "A")
        self.runner = InfrastructureFailureTests.Broken("unreachable")
        service.submit_assessment(self.token)
        self.assertEqual(self.store.assessments[1]["status"], "COMPLETED")
        self.assertTrue(self.store.results[1]["needs_retry"])
        service.db.update_candidate.assert_not_called()  # hiring stage untouched
        self.runner = LocalSubprocessRunner()  # the sandbox is back
        service.regrade_assessment(1, actor="rec")
        self.assertEqual(self.store.assessments[1]["status"], "PASSED")
        self.assertFalse(self.store.results[1]["needs_retry"])


@unittest.skipUnless(Judge0Runner.from_env(), "set JUDGE0_URL (and JUDGE0_AUTH_TOKEN) to run against a real Judge0 sandbox")
class LiveJudge0Tests(unittest.TestCase):
    """Integration check against the configured Judge0 server: real sandboxed execution in every language."""

    def test_reference_and_candidate_programs_in_the_sandbox(self):
        runner = Judge0Runner.from_env()
        q = question(reference_solutions={"java": PROGRAMS["correct_java"][1], "javascript": PROGRAMS["correct_js"][1]})
        result, _ = verification.verify_question(q, runner=runner)
        self.assertEqual(result["status"], "verified", result["message"])
        for name, expected in (("samples_only", 4), ("compile_error", 0), ("timeout", 0)):
            with self.subTest(program=name):
                self.assertEqual(run(name, runner=runner)["points_earned"], expected)


if __name__ == "__main__":
    unittest.main()
