"""Read-only cohort analytics. No guessed hiring events or database writes."""
from collections import Counter
from datetime import datetime, timezone


def timestamp(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_filters(args):
    result = {}
    for key in ('start_date', 'end_date'):
        if args.get(key):
            result[key] = timestamp(args[key])
            if result[key] is None:
                raise ValueError(f'{key} must be an ISO date or timestamp.')
    if result.get('start_date') and result.get('end_date') and result['start_date'] >= result['end_date']:
        raise ValueError('end_date must be after start_date (exclusive).')
    if args.get('jd_id'):
        try:
            result['jd_id'] = int(args['jd_id'])
            if result['jd_id'] <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('jd_id must be a positive integer.') from None
    return result


def build_analytics(candidates, jobs, comparisons, interviews, filters, now=None):
    """Dates select candidate upload cohorts; stages are their current state.

    Candidate IDs are the unique unit. Comparison associations support candidates
    submitted to multiple jobs. Interview events have a separate date scope.
    """
    now = now or datetime.now(timezone.utc)
    start, end, job_id = (filters.get(k) for k in ('start_date', 'end_date', 'jd_id'))
    def in_range(value):
        date = timestamp(value)
        return bool(date and (not start or date >= start) and (not end or date < end))
    def job_matches(row):
        return job_id is None or str(row.get('jd_id')) == str(job_id)
    selected_jobs = [j for j in jobs if job_id is None or str(j.get('id')) == str(job_id)]
    relevant_comparisons = [r for r in comparisons if job_matches(r)]
    associated = {str(r.get('candidate_id')) for r in relevant_comparisons}
    unique = {}
    missing_dates = 0
    for row in candidates:
        if row.get('id') is None:
            continue
        if not job_matches(row) and str(row['id']) not in associated:
            continue
        date = row.get('uploaded_at') or row.get('created_at')
        if not timestamp(date):
            missing_dates += 1
        if (start or end) and not in_range(date):
            continue
        unique.setdefault(str(row['id']), row)
    rows = list(unique.values())
    ids = set(unique)
    comp = [r for r in relevant_comparisons if str(r.get('candidate_id')) in ids]
    selected, rejected = set(), set()
    for row in [r for r in rows if job_matches(r)] + comp:
        cid = str(row.get('candidate_id', row.get('id')))
        if row.get('status') == 'Selected' or row.get('selection_status') in {'selected_bench', 'accepted_vendor'}:
            selected.add(cid)
        if row.get('status') == 'Rejected' or row.get('selection_status') == 'rejected':
            rejected.add(cid)
    screened = selected | rejected
    events = [r for r in interviews if job_matches(r) and str(r.get('status', '')).lower() not in {'cancelled', 'canceled'}]
    dated_events = [r for r in events if (not start and not end) or in_range(r.get('interview_start'))]
    completed = {str(r.get('candidate_id')) for r in events if str(r.get('status', '')).lower() == 'completed' and str(r.get('candidate_id')) in ids}
    has_completion = any(str(r.get('status', '')).lower() == 'completed' for r in interviews)
    # These fields are optional: absence is not evidence of zero hires/offers.
    has_hires = any(timestamp(r.get('hired_at')) for r in candidates)
    has_offers = any(timestamp(r.get('offered_at')) for r in candidates)
    hired = [r for r in rows if timestamp(r.get('hired_at'))]
    offered = [r for r in rows if timestamp(r.get('offered_at'))]
    sources = Counter(str(r.get('candidate_source') or 'Unknown') for r in rows)
    months = Counter()
    source_months = {}
    for row in rows:
        date = timestamp(row.get('uploaded_at') or row.get('created_at'))
        if date:
            key = date.strftime('%Y-%m')
            months[key] += 1
            source_months.setdefault(key, Counter())[str(row.get('candidate_source') or 'Unknown')] += 1
    stages = [{'name': 'Uploaded', 'count': len(rows)}, {'name': 'Screened', 'count': len(screened)},
              {'name': 'Interviewed', 'count': len(completed) if has_completion else None},
              {'name': 'Offered', 'count': len(offered) if has_offers else None},
              {'name': 'Hired', 'count': len(hired) if has_hires else None}]
    reasons = {'Interviewed': 'Completed interview status has not been recorded.',
               'Offered': 'Offer timestamps have not been recorded.', 'Hired': 'Hire timestamps have not been recorded.'}
    for stage in stages:
        stage['reason'] = reasons.get(stage['name'], '') if stage['count'] is None else ''
    job_reports = []
    for job in selected_jobs:
        jid = str(job['id'])
        linked = {str(r['id']) for r in rows if str(r.get('jd_id')) == jid}
        linked |= {str(r.get('candidate_id')) for r in comp if str(r.get('jd_id')) == jid}
        job_comp = [r for r in comp if str(r.get('jd_id')) == jid]
        passed = {str(r.get('candidate_id')) for r in job_comp if r.get('status') == 'Selected' or r.get('selection_status') in {'selected_bench', 'accepted_vendor'}}
        failed = {str(r.get('candidate_id')) for r in job_comp if r.get('status') == 'Rejected' or r.get('selection_status') == 'rejected'}
        passed |= {str(r['id']) for r in rows if str(r.get('jd_id')) == jid and (r.get('status') == 'Selected' or r.get('selection_status') in {'selected_bench', 'accepted_vendor'})}
        failed |= {str(r['id']) for r in rows if str(r.get('jd_id')) == jid and (r.get('status') == 'Rejected' or r.get('selection_status') == 'rejected')}
        comparison_scores = {str(r.get('candidate_id')): r.get('match_score') for r in job_comp}
        scores = [float(comparison_scores.get(cid) or unique[cid].get('match_score') or 0) for cid in linked]
        job_reports.append({'id': job['id'], 'title': job.get('title', 'Untitled job'), 'total_screened': len(linked),
                            'selected': len(passed), 'rejected': len(failed), 'avg_match': round(sum(scores) / len(scores)) if scores else 0})
    skills = Counter(str(skill) for job in selected_jobs for skill in job.get('skills') or [])
    skill_gaps = [{'name': skill, 'jd_count': count, 'candidate_count': sum(skill.lower() in (str(r.get('structured_data') or {}) + str(r.get('applied_roles') or [])).lower() for r in rows)} for skill, count in skills.most_common(12)]
    durations = [(timestamp(r['hired_at']) - timestamp(r.get('uploaded_at') or r.get('created_at'))).total_seconds() / 86400 for r in hired if timestamp(r.get('uploaded_at') or r.get('created_at')) and timestamp(r['hired_at']) >= timestamp(r.get('uploaded_at') or r.get('created_at'))]
    recruiters = Counter(str(r['recruiter_id']) for r in dated_events if r.get('recruiter_id') is not None)
    metrics = {'total_candidates': len(rows), 'total_jobs': len(selected_jobs), 'total_jds': len(selected_jobs),
               'active_jobs': sum(j.get('status') == 'Active' for j in selected_jobs),
               'selected_candidates': len(selected), 'rejected_candidates': len(rejected), 'screened_candidates': len(screened),
               'selection_rate': round(len(selected) / len(screened) * 100) if screened else 0,
               'rejection_rate': round(len(rejected) / len(screened) * 100) if screened else 0,
               'submissions': len(comp), 'internal_interviews': sum(str(r.get('interview_type', '')).lower() == 'internal' for r in dated_events),
               'external_interviews': sum(str(r.get('interview_type', '')).lower() == 'external' for r in dated_events),
               'client_submissions': len(selected), 'client_rejections': None,
               'selected_bench_candidates': sum(r.get('selection_status') == 'selected_bench' for r in comp),
               'waitlisted_bench_candidates': sum(r.get('selection_status') == 'waitlisted_bench' for r in comp),
               'vendor_submitted_candidates': sum(r.get('selection_status') == 'vendor_submitted' for r in comp),
               'accepted_vendor_candidates': sum(r.get('selection_status') == 'accepted_vendor' for r in comp),
               'remaining_vendor_requirement': sum(int(j.get('remaining_vendor_requirement') or 0) for j in selected_jobs)}
    upcoming = sorted([r for r in events if timestamp(r.get('interview_start')) and timestamp(r['interview_start']) >= now], key=lambda r: timestamp(r['interview_start']))[:5]
    notes = ['Candidate charts show upload cohorts and current screening outcomes, not historical stage transitions.',
             'Interview events use their scheduled start date. Upcoming interviews use the job filter and future dates.',
             f'{missing_dates} candidate records lack usable upload dates; dated cohorts exclude them.',
             'Period comparisons and stage trends are unavailable without complete event history.',
             'Job counts, skills demanded and open shortage are current job totals; candidate counts use the upload cohort.',
             'Hire, offer and completed-interview counts include recorded evidence only; incomplete history can undercount them.']
    return {'metrics': metrics, 'jd_reports': job_reports, 'funnel': stages, 'skill_gaps': skill_gaps,
            'candidates': rows, 'recent_candidates': sorted(rows, key=lambda r: str(r.get('uploaded_at') or ''), reverse=True)[:5],
            'recent_jds': [{**j, 'selected_count': r['selected'], 'rejected_count': r['rejected']} for j, r in zip(selected_jobs, job_reports)][:5],
            'recent_comparisons': sorted(comp, key=lambda r: str(r.get('comparison_date') or ''), reverse=True)[:5],
            'analytics': {'pipeline': stages, 'sources': [{'name': k, 'count': v} for k, v in sources.most_common()],
                          'trend': [{'name': k, 'count': v} for k, v in sorted(months.items())],
                          'source_trend': [{'month': k, 'sources': dict(v)} for k, v in sorted(source_months.items())],
                          'time_to_hire': {'days': round(sum(durations) / len(durations), 1) if durations else None, 'sample_size': len(durations)},
                          'recruiters': [{'name': f'Recruiter #{k}', 'interviews': v} for k, v in recruiters.most_common()],
                          'upcoming_interviews': upcoming, 'notes': notes, 'jobs': [{'id': j['id'], 'title': j.get('title', '')} for j in jobs],
                          'filters': {k: v.isoformat() if isinstance(v, datetime) else v for k, v in filters.items()}}}


def analytics_payload(args):
    filters = parse_filters(args)
    return build_analytics(*load_analytics_records(), filters)


def load_analytics_records():
    """Four projected reads, avoiding per-candidate/per-comparison lookups."""
    import database as db
    store = db.get_database()
    fields = {
        'candidates': 'id jd_id name status selection_status candidate_source uploaded_at created_at hired_at offered_at match_score applied_roles structured_data',
        'job_descriptions': 'id title status skills created_at remaining_vendor_requirement',
        'comparisons': 'id candidate_id jd_id status selection_status candidate_source comparison_date match_score',
        'interviews': 'id candidate_id candidate_name jd_id jd_title recruiter_id recruiter_name status interview_type interview_start interview_end',
    }
    records = [db._serialize_docs(list(store[name].find({}, {'_id': 0, **{field: 1 for field in keys.split()}}))) for name, keys in fields.items()]
    candidates, jobs, comparisons, interviews = records
    names = {r['id']: r.get('name', '') for r in candidates}
    titles = {r['id']: r.get('title', '') for r in jobs}
    for row in comparisons + interviews:
        row.setdefault('candidate_name', names.get(row.get('candidate_id'), ''))
        row.setdefault('jd_title', titles.get(row.get('jd_id'), ''))
    return records
