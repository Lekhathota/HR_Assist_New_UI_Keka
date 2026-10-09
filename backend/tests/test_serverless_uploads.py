from io import BytesIO
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from docx import Document
from flask import Flask
import pytest
from werkzeug.datastructures import FileStorage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database as db
from services import upload_storage as storage
from services import auth_service, jd_service
from routes import matching_routes, candidate_routes
from app.text_extractor import extract_text


def test_vercel_uses_writable_temp_directory(monkeypatch):
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('UPLOAD_FOLDER', '/var/task/backend/static/uploads')
    assert Path(storage.upload_directory()).parent == Path(tempfile.gettempdir())


def test_local_uploads_keep_existing_storage(tmp_path, monkeypatch):
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.setenv('UPLOAD_FOLDER', str(tmp_path))
    assert storage.upload_directory() == str(tmp_path)
    with patch.object(storage.gridfs, 'GridFS') as grid:
        path = storage.save_upload(FileStorage(stream=BytesIO(b'resume')), str(tmp_path), 'resume.pdf')
    assert Path(path).read_bytes() == b'resume'
    grid.assert_not_called()


def test_resume_upload_processes_and_persists_then_downloads_after_temp_cleanup(tmp_path, monkeypatch):
    monkeypatch.setenv('VERCEL', '1')
    app = Flask(__name__)
    app.config['UPLOAD_FOLDER'] = str(tmp_path)
    app.register_blueprint(matching_routes.matching_bp)
    app.register_blueprint(candidate_routes.candidate_bp)
    app.teardown_appcontext(lambda error: storage.cleanup_processing_uploads())
    document = Document()
    document.add_paragraph('Test Candidate: Python developer')
    original = BytesIO()
    document.save(original)
    original_bytes = original.getvalue()
    original.seek(0)
    persisted = {}
    processing_paths = []
    bucket = MagicMock()
    def persist(contents, **metadata):
        persisted[metadata['filename']] = contents.read()
    bucket.put.side_effect = persist
    bucket.find_one.side_effect = lambda query: SimpleNamespace(read=lambda: persisted[query['filename']]) if query['filename'] in persisted else None
    def screen(payload, **kwargs):
        item = payload['resume_items'][0]
        processing_paths.append(item['path'])
        assert 'Python developer' in extract_text(item['path'])
        return {'ranked_candidates': [{'id': 1, 'status': 'Selected'}], 'selected_results': [{'id': 1}], 'summary': {}}
    monkeypatch.setattr(auth_service, 'effective_user_id', lambda: 1)
    monkeypatch.setattr(matching_routes, 'current_user', lambda: {'username': 'tester'})
    monkeypatch.setattr(matching_routes, 'run_main_orchestrator', screen)
    monkeypatch.setattr(db, 'log_audit', lambda *args: None)
    monkeypatch.setattr(db, 'get_database', lambda: object())
    with patch.object(storage.gridfs, 'GridFS', return_value=bucket):
        response = app.test_client().post('/api/compare', data={'jd_id': '33', 'resumes': (original, 'resume.docx')})
        assert response.status_code == 200
        assert response.get_json()['mode'] == 'resume_upload'
        assert not Path(processing_paths[0]).exists()
        filename = next(iter(persisted))
        download = app.test_client().get('/api/uploads/' + filename)
        assert download.status_code == 200
        assert download.data == original_bytes
        assert download.headers['Cache-Control'] == 'private, no-store'


def test_uploaded_resumes_require_authentication():
    app = Flask(__name__)
    app.register_blueprint(candidate_routes.candidate_bp)
    with patch.object(auth_service, 'effective_user_id', return_value=None):
        assert app.test_client().get('/api/uploads/resume.pdf').status_code == 401


def test_failed_persistence_removes_processing_copy(tmp_path, monkeypatch):
    monkeypatch.setenv('VERCEL', '1')
    with patch.object(db, 'get_database', return_value=object()), patch.object(storage.gridfs, 'GridFS') as grid:
        grid.return_value.put.side_effect = RuntimeError('storage unavailable')
        with pytest.raises(RuntimeError):
            storage.save_upload(FileStorage(stream=BytesIO(b'resume')), str(tmp_path), 'resume.pdf')
    assert not (tmp_path / 'resume.pdf').exists()


def test_serverless_connection_does_not_run_cold_start_backfills(monkeypatch):
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.delenv('RA_RUN_DB_MAINTENANCE', raising=False)
    with patch.object(db, '_client', None), patch.object(db, '_db', None), \
         patch.object(db, 'get_mongo_uri', return_value='mongodb://example'), \
         patch.object(db, 'MongoClient') as mongo, patch.object(db, '_ensure_indexes') as indexes, \
         patch.object(db, '_sync_counters') as counters, patch.object(db, 'refresh_dashboard_metrics') as metrics:
        db.init_pool()
        db.init_pool()
        mongo.assert_called_once()
        indexes.assert_not_called()
        counters.assert_not_called()
        metrics.assert_not_called()


def test_jobs_list_uses_one_batch_of_counts():
    rows = [{'id': 1, 'title': 'Developer'}, {'id': 2, 'title': 'Tester'}]
    counts = {1: {'total_resumes': 3, 'selected_count': 1, 'rejected_count': 2},
              2: {'total_resumes': 0, 'selected_count': 0, 'rejected_count': 0}}
    with patch.object(db, 'get_all_jds', return_value=rows), \
         patch.object(db, 'jd_candidate_counts_batch', return_value=counts) as batch, \
         patch.object(db, 'get_jd_by_id') as get_job, \
         patch.object(jd_service, '_apply_jd_category', side_effect=lambda row: row):
        result = jd_service.jd_summary_list_payload()
    batch.assert_called_once_with([1, 2])
    get_job.assert_not_called()
    assert result[0]['total_resumes'] == 3
