from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import assessment_service as service
from assessment.utilities import generate_access_token, utc_now


class CandidateFlowTests(unittest.TestCase):
    def test_email_is_sent_only_after_token_is_active(self):
        token = generate_access_token()
        assessment = {'id': 1, 'candidate_id': 10, 'jd_id': 20, 'status': 'DRAFT'}
        link = f'https://shimento.org.com/assessment/{token}'
        with ExitStack() as stack:
            stack.enter_context(patch.object(service, '_prepare_assessment_send', return_value=(
                assessment, 'DRAFT', token, utc_now() + timedelta(days=7), link, 'hr@example.com', 'candidate@example.com')))
            update = stack.enter_context(patch.object(service.assessment_repo, 'update_assessment', return_value=True))
            stack.enter_context(patch.object(service.assessment_repo, 'get_assessment_by_id', return_value={'status': 'SENT'}))
            stack.enter_context(patch.object(service.db, 'log_audit'))
            def deliver(*args, **kwargs):
                self.assertEqual(update.call_args.args[1]['access_token'], token)
                self.assertEqual(update.call_args.args[1]['status'], 'SENT')
            send = stack.enter_context(patch.object(service, 'send_email', side_effect=deliver))
            result = service.send_assessment(1, recruiter={'username': 'hr'})
        send.assert_called_once()
        self.assertEqual(result['assessment_link'], link)

    def test_public_candidate_loads_generated_questions_without_answer_key(self):
        token = generate_access_token()
        assessment = {"id": 1, "access_token": token, "status": "IN_PROGRESS",
                      "started_at": utc_now(), "time_limit_minutes": 60}
        questions = [{"id": 2, "question_text": "Choose A", "question_type": "mcq",
                      "options": ["A", "B"], "correct_answer": "A", "points": 10}]
        with patch.object(service.assessment_repo, 'get_assessment_by_token', return_value=assessment), \
             patch.object(service.assessment_repo, 'get_questions_for_assessment', return_value=questions), \
             patch.object(service.assessment_repo, 'get_answers_for_assessment', return_value=[]):
            result = service.get_assessment_by_token(token)
        self.assertEqual(result['questions'][0]['question_text'], 'Choose A')
        self.assertNotIn('correct_answer', result['questions'][0])

    def test_submission_scores_and_advances_only_passing_result(self):
        for answer, passed in [('A', True), ('B', False)]:
            token = generate_access_token()
            assessment = {'id': 1, 'candidate_id': 10, 'jd_id': 20, 'access_token': token,
                          'status': 'IN_PROGRESS', 'passing_score': 70}
            questions = [{'id': 2, 'question_type': 'mcq', 'correct_answer': 'A', 'points': 10}]
            with ExitStack() as stack:
                for name, value in {'get_assessment_by_token': assessment, 'get_questions_for_assessment': questions,
                                    'upsert_candidate_answer': 1, 'update_assessment': True,
                                    'mark_answers_final': True, 'upsert_assessment_result': 1}.items():
                    stack.enter_context(patch.object(service.assessment_repo, name, return_value=value))
                stack.enter_context(patch.object(service.db, 'update_candidate', return_value=True))
                stack.enter_context(patch.object(service.db, 'log_audit'))
                stack.enter_context(patch.object(service, 'get_assessment_result', return_value={}))
                advance = stack.enter_context(patch('services.hiring_process_service.advance_after_assessment'))
                service.submit_assessment(token, [{'question_id': 2, 'answer': answer}])
                self.assertEqual(advance.called, passed)

    def test_timer_expiry_submits_saved_answers_instead_of_accepting_late_changes(self):
        token = generate_access_token()
        assessment = {'id': 1, 'candidate_id': 10, 'jd_id': 20, 'access_token': token,
                      'status': 'IN_PROGRESS', 'started_at': utc_now() - timedelta(minutes=2),
                      'time_limit_minutes': 1}
        with ExitStack() as stack:
            for name, value in {'get_assessment_by_token': assessment,
                                'get_questions_for_assessment': [{'id': 2, 'question_type': 'mcq', 'correct_answer': 'A', 'points': 10}],
                                'get_answers_for_assessment': [{'question_id': 2, 'answer': 'B'}],
                                'update_assessment': True, 'mark_answers_final': True,
                                'upsert_assessment_result': 1}.items():
                stack.enter_context(patch.object(service.assessment_repo, name, return_value=value))
            save = stack.enter_context(patch.object(service.assessment_repo, 'upsert_candidate_answer'))
            stack.enter_context(patch.object(service.db, 'update_candidate'))
            stack.enter_context(patch.object(service.db, 'log_audit'))
            stack.enter_context(patch.object(service, 'get_assessment_result', return_value={}))
            service.submit_assessment(token, [{'question_id': 2, 'answer': 'A'}])
            save.assert_called_once_with(1, 2, 'B', is_final=True)
