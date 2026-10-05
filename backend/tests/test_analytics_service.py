from datetime import datetime, timezone
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.analytics_service import build_analytics, parse_filters

JOBS = [{'id': 1, 'title': 'Engineer', 'status': 'Active', 'skills': ['Python']}, {'id': 2, 'title': 'Analyst', 'status': 'Closed'}]


def run(rows=None, comparisons=None, interviews=None, args=None):
    return build_analytics(rows or [], JOBS, comparisons or [], interviews or [], parse_filters(args or {}), datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_empty_data_is_zero_but_unknown_stages_are_null():
    result = run()
    assert result['metrics']['total_candidates'] == 0
    assert result['metrics']['selection_rate'] == 0
    assert result['analytics']['pipeline'][-1]['count'] is None
    assert result['analytics']['time_to_hire']['days'] is None


def test_date_bounds_are_inclusive_start_exclusive_end_and_deduplicate():
    rows = [{'id': 1, 'uploaded_at': '2026-01-01T00:00:00Z'}, {'id': 1, 'uploaded_at': '2026-01-01T00:00:00Z'},
            {'id': 2, 'uploaded_at': '2026-02-01T00:00:00Z'}, {'id': 3}]
    result = run(rows, args={'start_date': '2026-01-01', 'end_date': '2026-02-01'})
    assert result['metrics']['total_candidates'] == 1
    assert result['analytics']['trend'] == [{'name': '2026-01', 'count': 1}]
    assert '1 candidate records' in result['analytics']['notes'][2]


def test_job_comparison_associations_do_not_leak_another_jobs_outcome():
    rows = [{'id': 1, 'jd_id': 1, 'status': 'Selected', 'candidate_source': 'Direct'}]
    comparisons = [{'candidate_id': 1, 'jd_id': 2, 'status': 'Rejected'}]
    result = run(rows, comparisons, args={'jd_id': '2'})
    assert result['metrics']['total_candidates'] == 1
    assert result['metrics']['selected_candidates'] == 0
    assert result['metrics']['rejected_candidates'] == 1


def test_job_reports_keep_decisions_separate_in_all_jobs_view():
    rows = [{'id': 1, 'jd_id': 1, 'status': 'Rejected'}]
    result = run(rows, [{'candidate_id': 1, 'jd_id': 2, 'status': 'Selected'}])
    assert result['jd_reports'][0]['selected'] == 0
    assert result['jd_reports'][0]['rejected'] == 1
    assert result['jd_reports'][1]['selected'] == 1


def test_candidate_screening_counts_are_unique_across_comparisons():
    result = run([{'id': 1}], [{'candidate_id': 1, 'jd_id': 1, 'status': 'Selected'}, {'candidate_id': 1, 'jd_id': 2, 'status': 'Selected'}])
    assert result['metrics']['screened_candidates'] == 1
    assert result['metrics']['submissions'] == 2


def test_scheduled_interview_is_not_completion_or_hire():
    result = run([{'id': 1}], interviews=[{'candidate_id': 1, 'status': 'Scheduled', 'interview_start': '2026-01-03', 'recruiter_id': 5}])
    assert result['analytics']['pipeline'][2]['count'] is None
    assert result['analytics']['pipeline'][4]['count'] is None
    assert result['analytics']['recruiters'][0]['interviews'] == 1


def test_time_to_hire_excludes_missing_and_invalid_dates():
    result = run([{'id': 1, 'uploaded_at': '2026-01-01', 'hired_at': '2026-01-11'}, {'id': 2, 'hired_at': '2026-01-12'}, {'id': 3, 'uploaded_at': '2026-01-30', 'hired_at': '2026-01-01'}])
    assert result['analytics']['time_to_hire'] == {'days': 10.0, 'sample_size': 1}


@pytest.mark.parametrize('args', [{'jd_id': 'bad'}, {'jd_id': '0'}, {'start_date': 'bad'}, {'start_date': '2026-02-01', 'end_date': '2026-01-01'}])
def test_invalid_filters(args):
    with pytest.raises(ValueError):
        parse_filters(args)


def test_routes_share_payload_and_keep_default_contract(monkeypatch):
    from flask import Flask
    from routes import dashboard_routes, report_routes
    monkeypatch.setattr(dashboard_routes, 'dashboard_payload', lambda: {'legacy': 'dashboard'})
    monkeypatch.setattr(report_routes, 'reports_payload', lambda: {'legacy': 'reports'})
    import services.analytics_service as service
    monkeypatch.setattr(service, 'load_analytics_records', lambda: ([{'id': 1, 'uploaded_at': '2026-01-15'}], JOBS, [], []))
    app = Flask(__name__)
    app.secret_key = 'fixture'
    app.register_blueprint(dashboard_routes.dashboard_bp)
    app.register_blueprint(report_routes.report_bp)
    with app.test_client() as client:
        assert client.get('/api/dashboard?analytics=1').status_code == 401
        with client.session_transaction() as session:
            session['user_id'] = 1
        assert client.get('/api/dashboard').json == {'legacy': 'dashboard'}
        assert client.get('/api/reports').json == {'legacy': 'reports'}
        query = '?analytics=1&start_date=2026-01-01&end_date=2026-02-01'
        assert client.get('/api/dashboard' + query).json == client.get('/api/reports' + query).json
        assert client.get('/api/reports?jd_id=bad').status_code == 400


def test_snapshot_reads_are_projected_and_dates_are_serialized(monkeypatch):
    import database as db
    from services.analytics_service import load_analytics_records
    reads = []
    class Collection:
        def __init__(self, name):
            self.name = name
        def find(self, query, projection):
            reads.append((self.name, projection))
            if self.name == 'candidates':
                return [{'id': 1, 'name': 'A', 'uploaded_at': datetime(2026, 1, 1, tzinfo=timezone.utc)}]
            return []
    class Store:
        def __getitem__(self, name):
            return Collection(name)
    monkeypatch.setattr(db, 'get_database', lambda: Store())
    rows, _, _, _ = load_analytics_records()
    assert len(reads) == 4
    assert all(projection['_id'] == 0 for _, projection in reads)
    assert rows[0]['uploaded_at'] == '2026-01-01T00:00:00+00:00'
