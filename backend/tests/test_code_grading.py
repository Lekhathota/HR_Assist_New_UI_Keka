"""Automatic grading of coding / SQL answers with visible and hidden test cases.

SQL runs for real in the in-memory SQLite sandbox. Judge0 is replaced with fakes here
(no network calls); tests/test_coding_engine.py executes real programs.
"""
import base64
import copy
import json
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assessment.code_execution import grader, judge0
from assessment.code_execution.judge0 import ExecutionResult, ExecutionUnavailable, Judge0Runner, outputs_match
from assessment.code_execution.preparation import prepare_executable_questions, validate_test_fields
from assessment.evaluation_service import evaluate_assessment
from assessment.evaluators.coding_evaluator import AutoCodingEvaluator
from assessment.utilities import candidate_question_payload
from services import assessment_service as service

SCHEMA = "CREATE TABLE orders (id INTEGER, customer TEXT, amount REAL);"
REFERENCE_SQL = "SELECT customer, SUM(amount) AS total FROM orders GROUP BY customer"


def sql_question(**over):
    question = {
        "id": 5, "assessment_id": 1, "question_type": "sql", "points": 20, "question_text": "Total per customer",
        "sql_schema": SCHEMA, "correct_answer": REFERENCE_SQL, "order_matters": False,
        "test_cases": [
            {"id": "t1", "hidden": False, "setup_sql": "INSERT INTO orders VALUES (1,'a',10),(2,'a',5),(3,'b',1);"},
            {"id": "t2", "hidden": True, "setup_sql": "INSERT INTO orders VALUES (1,'x',2.5),(2,'y',NULL);"},
            {"id": "t3", "hidden": True, "setup_sql": "INSERT INTO orders VALUES (1,'z',7);"},
        ],
    }
    question.update(over)
    return prepare_executable_questions([question], runner=None)[0]


def coding_question(**over):
    question = {
        "id": 7, "assessment_id": 1, "question_type": "coding", "points": 10, "question_text": "Double n",
        "correct_answer": "print(int(input()) * 2)", "default_language": "python",
        "test_cases": [
            {"id": "t1", "hidden": False, "input": "1\n", "expected_output": "2\n"},
            {"id": "t2", "hidden": False, "input": "5\n", "expected_output": "10\n"},
            {"id": "t3", "hidden": True, "input": "0\n", "expected_output": "0\n"},
            {"id": "t4", "hidden": True, "input": "-4\n", "expected_output": "-8\n"},
        ],
    }
    question.update(over)
    return question


class FakeRunner:
    """Pretends to run a 'program' that is a python lambda over stdin text."""

    def __init__(self, fn=None, fail=None):
        self.fn, self.fail, self.calls = fn, fail, []

    def run(self, language, source, cases, limits=None):
        self.calls.append((language, source, [c["id"] for c in cases]))
        if self.fail:
            raise ExecutionUnavailable(self.fail)
        out = []
        for case in cases:
            try:
                out.append(ExecutionResult(case["id"], "ok", stdout=self.fn(case["input"])))
            except Exception as exc:  # noqa: BLE001 - simulated runtime error
                out.append(ExecutionResult(case["id"], "runtime_error", stderr=str(exc)))
        return out


class SqlGradingTests(unittest.TestCase):
    def test_expected_results_come_from_running_the_reference(self):
        q = sql_question()
        self.assertEqual(q["test_cases"][0]["expected"]["rows"], [["a", 15], ["b", 1]])
        self.assertTrue(q["tests_verified"])

    def test_correct_query_passes_visible_and_hidden(self):
        result = grader.grade_answer(sql_question(), "select customer, sum(amount) from orders group by 1 order by 2 desc;")
        self.assertEqual((result.method, result.passed, result.total), ("sql_executed", 3, 3))

    def test_wrong_query_gets_partial_credit_and_hidden_details_stay_hidden(self):
        # Filtering amount > 1 drops customer b (t1) and the NULL-only customer y (t2); t3 is unaffected.
        result = grader.grade_answer(sql_question(), "SELECT customer, SUM(amount) FROM orders WHERE amount > 1 GROUP BY customer")
        summary = result.summary()
        self.assertEqual(summary["visible_passed"], 0)
        self.assertEqual(summary["hidden_passed"], 1)
        hidden = [o for o in result.outcomes if o.hidden]
        self.assertTrue(all(o.input is None and o.expected is None and o.actual is None for o in hidden))

    def test_writes_and_errors_fail_cleanly(self):
        for query in ("DELETE FROM orders", "SELEC nonsense", "SELECT 1; SELECT 2"):
            result = grader.grade_answer(sql_question(), query)
            self.assertEqual(result.passed, 0, query)
            self.assertTrue(all(o.status == "error" and o.error for o in result.outcomes), query)

    def test_broken_reference_is_rejected_at_generation(self):
        with self.assertRaises(ValueError):
            sql_question(correct_answer="SELECT customer FROM orders QUALIFY 1")


class CodeGradingTests(unittest.TestCase):
    def test_executed_with_hidden_tests_and_partial_credit(self):
        runner = FakeRunner(lambda stdin: f"{abs(int(stdin)) * 2}\n")  # wrong for negatives
        result = grader.grade_answer(coding_question(), "code", "java", runner=runner)
        summary = result.summary()
        self.assertEqual(result.method, "executed")
        self.assertEqual((summary["visible_passed"], summary["hidden_passed"], summary["hidden_total"]), (2, 1, 2))
        self.assertEqual(runner.calls[0][0], "java")

    def test_run_button_only_uses_visible_tests(self):
        runner = FakeRunner(lambda stdin: f"{int(stdin) * 2}\n")
        result = grader.grade_answer(coding_question(), "code", "python", include_hidden=False, runner=runner)
        self.assertEqual(runner.calls[0][2], ["t1", "t2"])
        self.assertEqual(result.total, 2)
        self.assertEqual(result.outcomes[0].actual, "2\n")

    def test_runtime_errors_fail_the_test(self):
        runner = FakeRunner(lambda stdin: 1 / 0)
        result = grader.grade_answer(coding_question(), "code", "c", runner=runner)
        self.assertEqual(result.passed, 0)
        self.assertEqual({o.status for o in result.outcomes}, {"runtime_error"})

    def test_unavailable_execution_is_never_estimated(self):
        for runner in (FakeRunner(fail="Judge0 is unreachable"), None):
            with self.subTest(runner=runner), self.assertRaises(ExecutionUnavailable):
                grader.grade_answer(coding_question(), "code", "cpp", runner=runner)

    def test_disallowed_language_is_rejected(self):
        with self.assertRaises(ValueError):
            grader.grade_answer(coding_question(allowed_languages=["python"]), "code", "java", runner=FakeRunner(str))

    def test_output_comparison_ignores_trailing_whitespace_only(self):
        self.assertTrue(outputs_match("1 2 \r\n3\n\n", "1 2\n3"))
        self.assertFalse(outputs_match("1  2\n", "1 2\n"))

    def test_reference_mismatch_blocks_generation_when_judge0_configured(self):
        q = coding_question()
        q["test_cases"][3]["expected_output"] = "999\n"
        with self.assertRaises(ValueError):
            prepare_executable_questions([q], runner=FakeRunner(lambda stdin: f"{int(stdin) * 2}\n"))
        ok = prepare_executable_questions([coding_question()], runner=FakeRunner(lambda stdin: f"{int(stdin) * 2}\n"))
        self.assertTrue(ok[0]["tests_verified"])
        unverified = prepare_executable_questions([coding_question()], runner=None)
        self.assertFalse(unverified[0]["tests_verified"])


class ScoringTests(unittest.TestCase):
    def test_submit_scores_coding_automatically_no_pending_review(self):
        mcq = {"id": 1, "question_type": "mcq", "correct_answer": "A", "points": 10}
        runner = FakeRunner(lambda stdin: f"{abs(int(stdin)) * 2}\n")
        with patch.object(grader.Judge0Runner, "from_env", return_value=runner):
            result = evaluate_assessment([mcq, coding_question(), sql_question()],
                                         {1: "A", 7: "code", 5: REFERENCE_SQL}, passing_score=70,
                                         languages_by_question={7: "python"})
        by_id = {r["question_id"]: r for r in result["question_results"]}
        self.assertEqual(result["pending_review_count"], 0)
        self.assertEqual(by_id[7]["points_earned"], 7.5)  # 3 of 4 equally weighted tests x 10 marks
        self.assertEqual(by_id[7]["metadata"]["hidden_total"], 2)
        self.assertEqual(by_id[5]["points_earned"], 20)
        self.assertEqual(result["score_percentage"], 93.75)
        self.assertTrue(result["passed"])

    def test_legacy_question_without_tests_waits_for_manual_review(self):
        legacy = {"id": 9, "question_type": "coding", "points": 10, "correct_answer": "def f(): return 1"}
        row = AutoCodingEvaluator().evaluate(legacy, "def f(): return 2").to_dict()
        self.assertEqual((row["points_earned"], row["evaluation_status"]), (0, "pending_review"))

    def test_nothing_to_grade_against_stays_pending(self):
        bare = {"id": 9, "question_type": "coding", "points": 10}
        row = AutoCodingEvaluator().evaluate(bare, "print(1)").to_dict()
        self.assertEqual(row["evaluation_status"], "pending_review")


class CandidatePayloadTests(unittest.TestCase):
    def test_hidden_tests_and_reference_never_reach_the_candidate(self):
        for question in (coding_question(), sql_question()):
            payload = candidate_question_payload(question)
            flat = json.dumps(payload)
            self.assertNotIn("correct_answer", payload)
            self.assertNotIn("test_cases", payload)
            self.assertNotIn(question["correct_answer"], flat)
            self.assertEqual(payload["hidden_test_count"], 2)
            hidden_ids = {c["id"] for c in question["test_cases"] if c["hidden"]}
            self.assertFalse(hidden_ids & {t["id"] for t in payload["sample_tests"]})
            for hidden in [c for c in question["test_cases"] if c["hidden"] and c.get("setup_sql")]:
                self.assertNotIn(hidden["setup_sql"], flat)
        coding = candidate_question_payload(coding_question())
        self.assertEqual([o["key"] for o in coding["language_options"]], ["python", "javascript", "java", "c", "cpp"])
        self.assertEqual(len(coding["sample_tests"]), 2)


class RunEndpointServiceTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.assessment = {"id": 1, "status": "IN_PROGRESS"}
        self.stack.enter_context(patch.object(service, "_resolve_token_assessment", return_value=self.assessment))
        self.get_q = self.stack.enter_context(patch.object(service.assessment_repo, "get_question_by_id", return_value=coding_question()))
        self.consume = self.stack.enter_context(patch.object(service.assessment_repo, "consume_code_run", return_value=True))
        self.attempts = self.stack.enter_context(patch.object(service.assessment_repo, "record_code_attempt"))
        self.stack.enter_context(patch.object(grader.Judge0Runner, "from_env", return_value=FakeRunner(lambda s: f"{int(s) * 2}\n")))

    def tearDown(self):
        self.stack.close()

    def test_run_returns_visible_results_only(self):
        out = service.run_candidate_code("tok", 7, "print(int(input())*2)", "python")
        self.assertEqual((out["passed"], out["total"], out["hidden_test_count"]), (2, 2, 2))
        self.assertEqual({t["id"] for t in out["tests"]}, {"t1", "t2"})

    def test_run_limit_and_validation(self):
        self.consume.return_value = False
        with self.assertRaises(service.AssessmentServiceError) as ctx:
            service.run_candidate_code("tok", 7, "x", "python")
        self.assertEqual(ctx.exception.status_code, 429)
        self.consume.return_value = True
        with self.assertRaises(service.AssessmentServiceError):
            service.run_candidate_code("tok", 7, "   ", "python")
        self.get_q.return_value = {**coding_question(), "assessment_id": 99}
        with self.assertRaises(service.AssessmentServiceError):
            service.run_candidate_code("tok", 7, "x", "python")


class Judge0ClientTests(unittest.TestCase):
    def test_batch_submit_and_poll(self):
        runner = Judge0Runner("https://judge0.example.com", auth_token="t")
        calls = []

        def fake_request(method, path, body=None):
            calls.append((method, path))
            if method == "POST":
                self.assertEqual(body["submissions"][0]["language_id"], 71)
                self.assertEqual(base64.b64decode(body["submissions"][1]["stdin"]).decode(), "5\n")
                return [{"token": "a"}, {"token": "b"}]
            enc = lambda s: base64.b64encode(s.encode()).decode()
            return {"submissions": [{"token": "a", "status": {"id": 3}, "stdout": enc("2\n"), "time": "0.01"},
                                    {"token": "b", "status": {"id": 6}, "compile_output": enc("syntax error")}]}

        with patch.object(runner, "_request", side_effect=fake_request):
            results = runner.run("python", "print(1)", [{"id": "t1", "input": "1\n"}, {"id": "t2", "input": "5\n"}])
        self.assertEqual([r.status for r in results], ["ok", "compile_error"])
        self.assertEqual(results[1].stderr, "syntax error")
        self.assertEqual(calls[0][0], "POST")

    def test_not_configured_without_url(self):
        with patch.dict("os.environ", {"JUDGE0_URL": ""}):
            self.assertIsNone(Judge0Runner.from_env())


class GenerationValidationTests(unittest.TestCase):
    def test_requires_visible_and_hidden_tests(self):
        item = {"test_cases": [{"input": "1", "expected_output": "2", "hidden": False}]}
        with self.assertRaises(ValueError):
            validate_test_fields(item, "coding", "Q11")
        fields = validate_test_fields({"test_cases": copy.deepcopy(coding_question()["test_cases"]) + [
            {"input": "9\n", "expected_output": "18\n", "hidden": True}], "default_language": "C++"}, "coding", "Q11")
        self.assertEqual(fields["default_language"], "cpp")
        self.assertEqual(sum(c["hidden"] for c in fields["test_cases"]), 3)


if __name__ == "__main__":
    unittest.main()


class RegradeTests(unittest.TestCase):
    def _run(self, status, answer):
        assessment = {"id": 39, "status": status, "candidate_id": 4, "jd_id": 2, "passing_score": 70}
        questions = [{"id": 1, "question_type": "mcq", "correct_answer": "A", "points": 10}, sql_question(id=2, points=10)]
        answers = [{"question_id": 1, "answer": "A"}, {"question_id": 2, "answer": answer}]
        with ExitStack() as stack:
            stack.enter_context(patch.object(service.assessment_repo, "get_assessment_by_id", return_value=assessment))
            stack.enter_context(patch.object(service.assessment_repo, "get_questions_for_assessment", return_value=questions))
            stack.enter_context(patch.object(service.assessment_repo, "get_answers_for_assessment", return_value=answers))
            upsert = stack.enter_context(patch.object(service.assessment_repo, "upsert_assessment_result", return_value=7))
            update = stack.enter_context(patch.object(service.assessment_repo, "update_assessment", return_value=True))
            candidate = stack.enter_context(patch.object(service.db, "update_candidate"))
            stack.enter_context(patch.object(service.db, "log_audit"))
            stack.enter_context(patch.object(service, "get_assessment_result", return_value={}))
            advance = stack.enter_context(patch("services.hiring_process_service.advance_after_assessment"))
            service.regrade_assessment(39, actor="rec")
        return upsert.call_args.args[0], update, candidate, advance

    def test_regrade_scores_previously_ungraded_sql_and_updates_status(self):
        doc, update, candidate, advance = self._run("FAILED", REFERENCE_SQL)
        self.assertEqual((doc["score_percentage"], doc["status"]), (100.0, "PASSED"))
        self.assertEqual(doc["question_results"][1]["evaluation_method"], "sql_executed")
        update.assert_called_once_with(39, {"status": "PASSED"})
        advance.assert_called_once_with(4, 2)

    def test_regrade_without_status_change_leaves_pipeline_alone(self):
        doc, update, candidate, advance = self._run("FAILED", "SELECT 1")
        self.assertEqual(doc["status"], "FAILED")
        update.assert_not_called()
        candidate.assert_not_called()
        advance.assert_not_called()

    def test_only_submitted_assessments_can_be_regraded(self):
        with patch.object(service.assessment_repo, "get_assessment_by_id", return_value={"id": 1, "status": "IN_PROGRESS"}):
            with self.assertRaises(service.AssessmentServiceError):
                service.regrade_assessment(1)


class LenientGenerationTests(unittest.TestCase):
    def test_sql_accepts_statement_lists_empty_datasets_and_missing_flags(self):
        item = {"schema": SCHEMA, "test_cases": [
            {"setup_sql": ["INSERT INTO orders VALUES (1,'a',10);", "INSERT INTO orders VALUES (2,'b',3);"]},
            {"data": "INSERT INTO orders VALUES (1,'c',4);"},
            {"setup_sql": "", "is_hidden": True},          # empty-table edge case
            {"setup_sql": "INSERT INTO orders VALUES (1,'d',1),(2,'d',2);", "hidden": "true"},
        ]}
        fields = validate_test_fields(item, "sql", "Q13")
        self.assertEqual(len(fields["test_cases"]), 4)
        self.assertEqual([c["hidden"] for c in fields["test_cases"]], [False, True, True, True])
        self.assertIn("INSERT INTO orders VALUES (2,'b',3);", fields["test_cases"][0]["setup_sql"])
        prepared = prepare_executable_questions([{"question_type": "sql", "correct_answer": REFERENCE_SQL, **fields}], runner=None)
        self.assertEqual(prepared[0]["test_cases"][2]["expected"]["rows"], [])

    def test_coding_accepts_numeric_outputs_and_rebalances_flags(self):
        item = {"test_cases": [{"input": f"{n}", "output": n * 2, "hidden": False} for n in range(1, 7)]}
        fields = validate_test_fields(item, "coding", "Q11")
        self.assertEqual(fields["test_cases"][0]["expected_output"], "2")
        self.assertEqual(sum(c["hidden"] for c in fields["test_cases"]), 4)

    def test_final_attempt_keeps_questions_whose_tests_are_unusable(self):
        from assessment.generation import normalized_jd, validate_exam
        from tests.test_assessment_generation import JD, SQL, TOTAL, exam

        data = exam()
        data["questions"][SQL]["test_cases"] = [{"setup_sql": "INSERT INTO requests VALUES (1, 1, 'x', 'y');"}]
        with self.assertRaises(ValueError):
            validate_exam(copy.deepcopy(data), normalized_jd(JD), total=TOTAL)
        rows = validate_exam(data, normalized_jd(JD), total=TOTAL, require_tests=False)
        self.assertNotIn("test_cases", rows[SQL])
        self.assertIn("test_cases", rows[SQL + 1])

    def test_non_strict_preparation_drops_only_the_broken_question(self):
        good = {"question_type": "sql", "correct_answer": REFERENCE_SQL, "sql_schema": SCHEMA,
                "test_cases": [{"id": f"t{n}", "hidden": n > 1, "setup_sql": "INSERT INTO orders VALUES (1,'a',1);"} for n in range(1, 4)]}
        make_bad = lambda: {**copy.deepcopy(good), "correct_answer": "SELECT nope FROM missing"}
        rows = prepare_executable_questions([make_bad(), good], runner=None, strict=False)
        self.assertNotIn("test_cases", rows[0])
        self.assertTrue(rows[1]["tests_verified"])
        with self.assertRaises(ValueError):
            prepare_executable_questions([make_bad()], runner=None, strict=True)


from assessment.code_execution import verification as verify_mod  # noqa: E402


class ReferenceVerificationTests(unittest.TestCase):
    def test_statuses_come_from_real_execution(self):
        q = coding_question()
        ok, _ = verify_mod.verify_question(q, runner=FakeRunner(lambda s: f"{int(s) * 2}\n"))
        self.assertEqual(ok["status"], "verified")
        self.assertEqual(len(ok["results"]), 4)
        bad, _ = verify_mod.verify_question(q, runner=FakeRunner(lambda s: f"{abs(int(s)) * 2}\n"))
        self.assertEqual(bad["status"], "failed")
        self.assertEqual([r["passed"] for r in bad["results"]], [True, True, True, False])
        none, _ = verify_mod.verify_question(q, runner=None)
        self.assertEqual(none["status"], "unavailable")
        down, _ = verify_mod.verify_question(q, runner=FakeRunner(fail="Judge0 is unreachable"))
        self.assertEqual(down["status"], "unavailable")

    def test_disabled_tests_are_skipped_everywhere(self):
        q = coding_question()
        q["test_cases"][3]["enabled"] = False
        result, _ = verify_mod.verify_question(q, runner=FakeRunner(lambda s: f"{abs(int(s)) * 2}\n"))
        self.assertEqual(result["status"], "verified")
        graded = grader.grade_answer(q, "code", "python", runner=FakeRunner(lambda s: f"{abs(int(s)) * 2}\n"))
        self.assertEqual(graded.total, 3)
        self.assertEqual(candidate_question_payload(q)["hidden_test_count"], 1)

    def test_any_change_makes_verification_stale(self):
        q = coding_question()
        result, _ = verify_mod.verify_question(q, runner=FakeRunner(lambda s: f"{int(s) * 2}\n"))
        q["verification"] = result
        self.assertEqual(verify_mod.verification_view(q)["status"], "verified")
        for change in ({"correct_answer": "print(1)"}, {"reference_language": "java"}):
            self.assertEqual(verify_mod.verification_view({**q, **change})["status"], "not_verified")
        edited = copy.deepcopy(q)
        edited["test_cases"][0]["expected_output"] = "3\n"
        self.assertTrue(verify_mod.verification_view(edited)["stale"])
        renamed = copy.deepcopy(q)
        renamed["test_cases"][0]["name"] = "renamed only"
        self.assertEqual(verify_mod.verification_view(renamed)["status"], "verified")

    def test_sql_verification_records_expected_results(self):
        q = sql_question()
        for case in q["test_cases"]:
            case.pop("expected")
        result, tests = verify_mod.verify_question(q)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(tests[0]["expected"]["rows"], [["a", 15], ["b", 1]])

    def test_normalize_keeps_ids_and_validates(self):
        cases = verify_mod.normalize_test_cases("coding", [
            {"id": "t1", "name": "basic", "input": "1\n", "expected_output": "2\n", "hidden": False},
            {"input": "2\n", "expected_output": "4\n", "hidden": True, "enabled": False},
        ])
        self.assertEqual(cases[0]["id"], "t1")
        self.assertTrue(cases[1]["id"].startswith("tc_"))
        self.assertFalse(cases[1]["enabled"])
        with self.assertRaises(ValueError):
            verify_mod.normalize_test_cases("coding", [{"input": "1", "expected_output": "  "}])

    def test_candidate_payload_never_contains_reference_or_verification(self):
        q = coding_question(verification={"status": "verified"}, reference_language="java", config_fingerprint="x")
        payload = candidate_question_payload(q)
        for key in ("verification", "reference_language", "config_fingerprint", "correct_answer", "test_cases"):
            self.assertNotIn(key, payload)


class ReferenceServiceTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.question = {**coding_question(), "assessment_id": 1}
        self.stack.enter_context(patch.object(service.assessment_repo, "get_question_by_id", side_effect=lambda qid: copy.deepcopy(self.question)))
        self.assessment = {"id": 1, "status": "DRAFT", "jd_id": 3}
        self.stack.enter_context(patch.object(service.assessment_repo, "get_assessment_by_id", side_effect=lambda aid: self.assessment))
        self.stack.enter_context(patch.object(service.db, "get_jd_by_id", return_value={"id": 3, "title": "Backend", "client_id": 5}))
        self.stack.enter_context(patch.object(service.db, "get_client_by_id", return_value={"id": 5, "name": "Acme"}))
        self.stack.enter_context(patch.object(service.db, "log_audit"))
        self.stack.enter_context(patch.object(service.assessment_repo, "update_question", side_effect=self._apply))
        self.guarded = self.stack.enter_context(patch.object(service.assessment_repo, "update_question_if_unchanged", side_effect=self._apply_guarded))
        self.stack.enter_context(patch.object(verify_mod.Judge0Runner, "from_env", return_value=FakeRunner(lambda s: f"{int(s) * 2}\n")))

    def tearDown(self):
        self.stack.close()

    def _apply(self, qid, patch_doc):
        self.question.update(copy.deepcopy(patch_doc))
        return True

    def _apply_guarded(self, qid, expected, patch_doc):
        if self.question.get("config_fingerprint") not in (None, expected):
            return False
        return self._apply(qid, patch_doc)

    def _tests(self):
        return [{k: v for k, v in c.items()} for c in self.question["test_cases"]]

    def test_save_resets_then_verify_marks_verified(self):
        self.question["verification"] = {"status": "verified", "fingerprint": "old"}
        saved = service.save_reference_config(7, {"reference_solution": "print(int(input())*2)", "reference_language": "python",
                                                  "test_cases": self._tests()})
        self.assertEqual(saved["verification"]["status"], "not_verified")
        verified = service.verify_reference_solution(7)
        self.assertEqual(verified["verification"]["status"], "verified")
        self.assertTrue(self.question["tests_verified"])

    def test_save_with_verify_flag_and_language_validation(self):
        out = service.save_reference_config(7, {"reference_solution": "x", "reference_language": "java",
                                                "test_cases": self._tests(), "verify": True})
        self.assertEqual(out["reference_language"], "java")
        self.assertEqual(out["verification"]["status"], "verified")
        with self.assertRaises(service.AssessmentServiceError):
            service.save_reference_config(7, {"reference_solution": "x", "reference_language": "powershell", "test_cases": self._tests()})

    def test_edits_blocked_after_sending_but_verify_allowed(self):
        self.assessment["status"] = "SENT"  # published: edit only after returning it to draft
        with self.assertRaises(service.AssessmentServiceError) as ctx:
            service.save_reference_config(7, {"reference_solution": "x", "test_cases": self._tests()})
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertFalse(service.get_reference_config(7)["editable"])
        self.assertEqual(service.verify_reference_solution(7)["verification"]["status"], "verified")

    def test_concurrent_edit_discards_stale_verification(self):
        self.question["config_fingerprint"] = "fp-before"
        original = verify_mod.verify_question

        def edited_meanwhile(question, **kwargs):
            result = original(question, **kwargs)
            self.question["config_fingerprint"] = "fp-after-another-save"  # a save lands mid-verification
            return result

        with patch.object(verify_mod, "verify_question", side_effect=edited_meanwhile):
            with self.assertRaises(service.AssessmentServiceError) as ctx:
                service.verify_reference_solution(7)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertNotIn("verification", {k for k, v in self.question.items() if v})
