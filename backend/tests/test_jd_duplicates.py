from pathlib import Path
import re
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database as db


class JDDuplicateTests(unittest.TestCase):
    def setUp(self):
        self.collection = MagicMock()
        self.rows = [{"id": 1, "client_id": 7, "title": "Backend Engineer"}]
        def lookup(query, projection=None):
            for row in self.rows:
                if "$or" not in query:
                    if row['id'] == query.get('id'):
                        return row
                    continue
                if row['client_id'] != query['client_id'] or row['id'] == query.get('id', {}).get('$ne'):
                    continue
                if re.match(query['$or'][1]['title']['$regex'], row['title'], re.I):
                    return row
            return None
        self.collection.find_one.side_effect = lookup
        self.database = SimpleNamespace(job_descriptions=self.collection)

    def test_same_client_case_and_whitespace_duplicate_is_rejected(self):
        with patch.object(db, '_database', return_value=self.database):
            with self.assertRaises(db.DuplicateJDNameError):
                db._check_duplicate_jd_title('  backend   ENGINEER ', 7)

    def test_same_title_different_client_is_allowed(self):
        with patch.object(db, '_database', return_value=self.database):
            db._check_duplicate_jd_title('Backend Engineer', 8)

    def test_current_job_is_excluded_from_duplicate_check(self):
        with patch.object(db, '_database', return_value=self.database):
            db._check_duplicate_jd_title('Backend Engineer', 7, exclude_id=1)

    def test_duplicate_create_never_inserts_a_job(self):
        with patch.object(db, '_database', return_value=self.database), \
             patch.object(db, '_next_id', return_value=2), \
             patch.object(db, '_client_for_data', return_value={'client_id': 7}):
            with self.assertRaises(db.DuplicateJDNameError):
                db.create_jd({'title': 'Backend Engineer', 'client_id': 7})
        self.collection.insert_one.assert_not_called()

    def test_rename_to_existing_title_is_rejected(self):
        self.rows.append({'id': 2, 'client_id': 7, 'title': 'Data Engineer'})
        with patch.object(db, '_database', return_value=self.database):
            with self.assertRaises(db.DuplicateJDNameError):
                db.update_jd(2, {'title': 'Backend Engineer'})
        self.collection.update_one.assert_not_called()

    def test_create_for_different_client_inserts_normalized_title(self):
        with patch.object(db, '_database', return_value=self.database), \
             patch.object(db, '_next_id', return_value=2), \
             patch.object(db, '_client_for_data', return_value={'client_id': 8}), \
             patch.object(db, '_project_for_data', return_value={}), \
             patch.object(db, 'refresh_dashboard_metrics'), \
             patch.object(db.activity_feed, 'emit'):
            self.assertEqual(db.create_jd({'title': 'Backend Engineer', 'client_id': 8, 'job_code': 'JOB-2'}), 2)
        inserted = self.collection.insert_one.call_args.args[0]
        self.assertEqual(inserted['client_id'], 8)
        self.assertEqual(inserted['normalized_title'], 'backend engineer')

    def test_duplicate_upload_returns_clear_conflict_response(self):
        from flask import Flask
        from io import BytesIO
        from routes import jd_routes
        from services import auth_service
        app = Flask(__name__)
        app.config['UPLOAD_FOLDER'] = 'unused'
        app.register_blueprint(jd_routes.jd_bp)
        with patch.object(auth_service, 'effective_user_id', return_value=1), \
             patch.object(jd_routes, 'create_jd_from_upload', side_effect=db.DuplicateJDNameError('JD already exists for this client')):
            response = app.test_client().post('/api/jds/create', data={
                'file': (BytesIO(b'document'), 'jd.pdf'), 'client_id': '7', 'required_candidate_count': '1'
            })
        self.assertEqual(response.status_code, 409)
        self.assertIn('already exists', response.get_json()['error'])
