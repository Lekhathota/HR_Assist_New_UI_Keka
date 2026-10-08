"""Regression coverage for JD-only generation and rejection paths; no external API calls."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assessment.generation import normalized_jd, requirement_catalog, validate_exam
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

def exam():
    return {"exam_title": "JD-Based Assessment", "job_title": "Python Developer", "experience_required": "3-5 years",
            "total_questions": 14, "skills_covered": ["Python"],
            "questions": [{"question_id": f"Q{i+1:03d}", "question": text,
                "question_type": "MCQ" if i < 10 else "CODING" if i < 12 else "SQL",
                "difficulty": "Hard" if 4 <= i < 10 else "Medium", "skill": "Python",
                "jd_requirement": "Maintain Python services", "scenario_type": "Troubleshooting",
                "options": ["A", "B", "C", "D"] if i < 10 else [], "correct_answer": "B",
                "explanation": "B addresses the stated failure with validation.",
                "evaluation_focus": ["Practical application"]} for i, text in enumerate(SCENARIOS)]}

class GenerationTests(unittest.TestCase):
    def test_complete_jd_does_not_mutate_structured_data(self):
        before = copy.deepcopy(JD)
        context = normalized_jd(JD)
        self.assertIn("service failures", context["posted_jd_text"])
        self.assertEqual(JD, before)

    def test_valid_exam_preserves_grounding_and_metadata(self):
        rows = validate_exam(exam(), normalized_jd(JD), total=14)
        self.assertEqual(len(rows), 14)
        self.assertEqual(rows[0]["jd_requirement"], "Maintain Python services")
        self.assertEqual(rows[6]["difficulty"], "Hard")

    def test_rejects_definitions_unsupported_skills_and_malformed_mcqs(self):
        edits = [ {"question": "What is Python?"}, {"skill": "Kubernetes"},
                  {"jd_requirement": "Deploy to AWS"}, {"options": ["A", "B", "C"]},
                  {"options": ["A", "A", "C", "D"]}, {"correct_answer": "E"},
                  {"difficulty": "Expert"}, {"explanation": ""} ]
        for edit in edits:
            with self.subTest(edit=edit):
                data = exam(); data["questions"][0].update(edit)
                with self.assertRaises(ValueError):
                    validate_exam(data, normalized_jd(JD), total=14)

    def test_rejects_duplicates_and_previous_question_reuse(self):
        data = exam(); data["questions"][1]["question"] = SCENARIOS[0]
        with self.assertRaises(ValueError): validate_exam(data, normalized_jd(JD), total=14)
        with self.assertRaises(ValueError): validate_exam(exam(), normalized_jd(JD), total=14, previous_questions=[SCENARIOS[0]])

    def test_unambiguous_letter_answers_are_converted_to_option_text(self):
        data = exam()
        data["questions"][0]["options"] = ["Validate input", "Handle absent optional field", "Drop the request", "Disable parsing"]
        data["questions"][0]["correct_answer"] = "Option B"
        rows = validate_exam(data, normalized_jd(JD), total=14)
        self.assertEqual(rows[0]["correct_answer"], "Handle absent optional field")

    def test_requires_complete_count_and_difficulty_mix(self):
        incomplete = exam(); incomplete["questions"].pop()
        with self.assertRaises(ValueError): validate_exam(incomplete, normalized_jd(JD))
        data = exam()
        for q in data["questions"]: q["difficulty"] = "Easy"
        with self.assertRaises(ValueError): validate_exam(data, normalized_jd(JD), total=14)

    def test_fixed_type_counts_and_moderate_coding_sql_are_enforced(self):
        for index, patch_data in ((0, {"question_type": "CODING"}), (0, {"difficulty": "Hard"}),
                                  (10, {"difficulty": "Hard"}), (12, {"difficulty": "Hard"})):
            with self.subTest(index=index, patch_data=patch_data):
                data = exam(); data["questions"][index].update(patch_data)
                with self.assertRaises(ValueError): validate_exam(data, normalized_jd(JD))

    def test_numbered_requirements_resolve_to_original_jd_text(self):
        catalog = requirement_catalog(normalized_jd(JD))
        ref = next(key for key, value in catalog.items() if value == "Python")
        data = exam()
        for question in data["questions"]:
            question["jd_requirement_id"] = ref
            question["jd_requirement"] = "paraphrased model evidence"
        with patch.object(service, "LLMService") as factory:
            factory.return_value.invoke.side_effect = [json.dumps(data), '{"valid": true, "issues": []}']
            metadata, rows = service._generate_questions_with_ai(JD)
            self.assertEqual(rows[0]["jd_requirement"], "Python")
            self.assertEqual(metadata["experience_required"], "3-5 years")

    def test_candidate_cannot_see_answer_explanation_or_rubric(self):
        q = validate_exam(exam(), normalized_jd(JD), total=14)[0]
        public = candidate_question_payload(q)
        for key in ("correct_answer", "explanation", "evaluation_focus", "jd_requirement"):
            self.assertNotIn(key, public)
            self.assertIn(key, recruiter_question_payload(q))

    def test_generation_uses_only_complete_jd_and_independent_review(self):
        with patch.object(service, "LLMService") as factory:
            llm = factory.return_value
            llm.invoke.side_effect = [json.dumps(exam()), '{"valid": true, "issues": []}']
            title, rows = service._generate_questions_with_ai(JD)
            self.assertEqual(len(rows), 14)
            generation_prompt = llm.invoke.call_args_list[0].args[0]
            self.assertIn(JD["raw_text"], generation_prompt)
            self.assertNotIn("Candidate Resume", generation_prompt)
            self.assertNotIn("resume_data", generation_prompt)
            self.assertEqual(llm.invoke.call_count, 2)
            self.assertIn("R001", llm.invoke.call_args_list[1].args[0])

    def test_assessment_model_default_and_override(self):
        for configured, expected in (("", "gpt-4.1"), ("custom-assessment-model", "custom-assessment-model")):
            with self.subTest(configured=configured), patch.dict("os.environ", {"ASSESSMENT_MODEL": configured}), \
                 patch.object(service, "LLMService") as factory:
                factory.return_value.invoke.side_effect = [json.dumps(exam()), '{"valid": true, "issues": []}']
                service._generate_questions_with_ai(JD)
                factory.assert_called_once_with(model=expected, temperature=0.6)

    def test_semantic_review_failure_retries(self):
        with patch.object(service, "LLMService") as factory:
            factory.return_value.invoke.side_effect = [json.dumps(exam()), '{"valid": false, "issues": ["Semantic duplicate Q002"]}',
                                                      json.dumps(exam()), '{"valid": true, "issues": []}']
            _, rows = service._generate_questions_with_ai(JD)
            self.assertEqual(len(rows), 14)
            self.assertIn("Semantic duplicate", factory.return_value.invoke.call_args_list[2].args[0])

    def test_incomplete_ai_never_generates_generic_fallback(self):
        with patch.object(service, "LLMService") as factory:
            factory.return_value.invoke.return_value = '{}'
            with self.assertRaises(service.AssessmentServiceError): service._generate_questions_with_ai(JD)
            self.assertEqual(factory.return_value.invoke.call_count, 3)

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
        rows = validate_exam(exam(), normalized_jd(JD), total=14)
        with patch.object(service.db, "get_jd_by_id", return_value=JD), \
             patch.object(service.db, "get_candidate_by_id") as candidate, \
             patch.object(service, "_generate_questions_with_ai", return_value=({"exam_title": "JD-Based Assessment", "job_title": "Python Developer", "experience_required": "3-5 years"}, rows)):
            result = service.generate_jd_exam(3)
            candidate.assert_not_called()
            self.assertEqual(result["experience_required"], "3-5 years")
            self.assertEqual(result["questions"][0]["question_type"], "MCQ")

if __name__ == "__main__": unittest.main()
