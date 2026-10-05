// Frontend presentation adapter for existing, unmodified API contracts.
const list = value => Array.isArray(value) ? value : [];
const numeric = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? Number(value) : null;
const date = value => value && Number.isFinite(Date.parse(value)) ? new Date(value) : null;
const outcome = row => {
  const selection = row._screening_comparison?.selection_status || row.selection_status;
  const status = row._screening_comparison?.status || row.status;
  if (['selected_bench', 'accepted_vendor'].includes(selection) || status === 'Selected') return 'Selected';
  if (selection === 'rejected' || status === 'Rejected') return 'Rejected';
  return status || 'Pending';
};
const counts = (rows, key) => Object.entries(rows.reduce((acc, row) => { const name = key(row); acc[name] = (acc[name] || 0) + 1; return acc; }, {})).map(([name, count]) => ({ name, count }));

export function buildAnalyticsView(snapshot, filters, now = new Date()) {
  const { dashboard, reports, interviews, jobs: jobResponse, warnings = [] } = snapshot;
  const raw = list(dashboard?.candidates);
  const candidates = [...new Map(raw.filter(r => r.id != null).map(r => [String(r.id), r])).values()];
  const jobs = list(jobResponse).length ? jobResponse : list(dashboard?.recent_jds);
  const titles = new Map(jobs.map(j => [String(j.id), j.title]));
  const jobOptions = [...jobs.map(j => ({ id: j.id, title: j.title })), ...candidates.filter(r => r.jd_id != null && !titles.has(String(r.jd_id))).map(r => ({ id: r.jd_id, title: `Job #${r.jd_id}` }))];
  const options = [...new Map(jobOptions.map(j => [String(j.id), j])).values()];
  const start = filters.allTime ? null : date(`${filters.start}T00:00:00`);
  const end = filters.allTime ? null : date(`${filters.end}T00:00:00`);
  if (!filters.allTime && (!start || !end || start > end)) throw new Error('Choose a valid date range.');
  if (end) end.setDate(end.getDate() + 1);
  const inRange = value => { const d = date(value); return filters.allTime || Boolean(d && d >= start && d < end); };
  const selectedJobs = filters.jobs?.length ? filters.jobs.map(String) : filters.job ? [String(filters.job)] : [];
  const matchesJob = row => !selectedJobs.length || selectedJobs.includes(String(row.jd_id));
  const matchesSegment = row => (!filters.status || outcome(row) === filters.status) && (!filters.source || (row.candidate_source || 'Unknown') === filters.source);
  const segmentIds = new Set(candidates.filter(matchesSegment).map(r => String(r.id)));
  const matchesPerson = row => !(filters.status || filters.source) || segmentIds.has(String(row.candidate_id ?? row.id));
  const scoped = candidates.filter(r => matchesJob(r) && matchesSegment(r) && inRange(r.uploaded_at || r.created_at));
  const filtered = !filters.allTime || Boolean(selectedJobs.length || filters.status || filters.source);
  if (filtered && !Array.isArray(dashboard?.candidates)) throw new Error('Candidate records are unavailable. Retry before filtering analytics.');
  const byStatus = counts(scoped, outcome);
  const selected = scoped.filter(r => outcome(r) === 'Selected').length;
  const rejected = scoped.filter(r => outcome(r) === 'Rejected').length;
  const current = dashboard?.metrics || reports?.metrics || {};
  const metrics = filtered ? {
    total_candidates: scoped.length, screened_candidates: selected + rejected,
    selected_candidates: selected, rejected_candidates: rejected,
    selection_rate: selected + rejected ? Math.round(selected / (selected + rejected) * 100) : 0,
  } : { ...current, total_jobs: current.total_jobs ?? current.total_jds, total_jds: current.total_jds ?? current.total_jobs };
  if (Array.isArray(dashboard?.candidates)) Object.assign(metrics, {
    total_candidates: scoped.length, screened_candidates: selected + rejected,
    selected_candidates: selected, rejected_candidates: rejected,
    selection_rate: selected + rejected ? Math.round(selected / (selected + rejected) * 100) : 0,
  });
  const interviewRows = Array.isArray(interviews) ? interviews : list(interviews?.interviews);
  const scopedInterviews = interviewRows.filter(r => matchesJob(r) && matchesPerson(r) && inRange(r.interview_start) && !['cancelled', 'canceled'].includes(String(r.status).toLowerCase()));
  const interviewCount = filtered ? (interviews == null ? null : scopedInterviews.length) : numeric(current.internal_interviews);
  const pipeline = [
    { name: 'Uploaded', count: numeric(metrics.total_candidates) },
    { name: 'Screened', count: numeric(metrics.screened_candidates) },
    { name: 'Selected', count: numeric(metrics.selected_candidates) },
    { name: 'Rejected', count: numeric(metrics.rejected_candidates) },
  ];
  // Sources and dates exist on candidate records; unsupported stage history does not.
  const sources = counts(scoped, r => r.candidate_source || 'Unknown');
  const hasSources = scoped.some(r => Boolean(r.candidate_source));
  const trend = counts(scoped.filter(r => date(r.uploaded_at || r.created_at)), r => {
    const d = date(r.uploaded_at || r.created_at);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  }).sort((a, b) => a.name.localeCompare(b.name));
  const scoreRows = scoped.filter(r => numeric(r.match_score) != null && Number(r.match_score) >= 0 && Number(r.match_score) <= 100);
  const scoreBands = ['0–20', '21–40', '41–60', '61–80', '81–100'].map((name, i) => ({ name, count: scoreRows.filter(r => Math.min(4, Math.max(0, Math.ceil(Number(r.match_score) / 20) - 1)) === i).length }));
  const jobReports = filtered ? options.filter(j => matchesJob({ jd_id: j.id })).map(j => {
    const rows = scoped.filter(r => String(r.jd_id) === String(j.id));
    const scores = rows.map(r => numeric(r.match_score)).filter(v => v != null);
    return { id: j.id, title: j.title, total_screened: rows.length, selected: rows.filter(r => outcome(r) === 'Selected').length, rejected: rows.filter(r => outcome(r) === 'Rejected').length, avg_match: scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null };
  }) : list(reports?.jd_reports);
  const activityEvents = [
    ...list(dashboard?.recent_candidates).filter(r => matchesJob(r) && matchesPerson(r)).map(r => ({ id: `candidate-${r.id}`, name: r.name || `Candidate #${r.id}`, candidate_id: r.id, activity: 'Resume uploaded', job: titles.get(String(r.jd_id)) || (r.jd_id ? `Job #${r.jd_id}` : '—'), time: r.uploaded_at || r.created_at, icon: 'fa-file-lines' })),
    ...list(dashboard?.recent_comparisons).filter(r => matchesJob(r) && matchesPerson(r)).map((r, i) => ({ id: `comparison-${r.id ?? i}`, name: r.candidate_name || 'Screening', candidate_id: r.candidate_id, activity: 'Resume compared', job: r.jd_title || titles.get(String(r.jd_id)) || '—', time: r.comparison_date || r.date, icon: 'fa-code-compare' })),
    ...list(dashboard?.recent_jds).filter(r => matchesJob({ jd_id: r.id }) && !(filters.status || filters.source)).map(r => ({ id: `job-${r.id}`, job_id: r.id, name: r.title, activity: 'Job created', job: r.title, time: r.created_at || r.created, icon: 'fa-briefcase' })),
  ].filter(r => inRange(r.time)).sort((a, b) => (date(b.time)?.getTime() || 0) - (date(a.time)?.getTime() || 0));
  const seenActivity = new Set();
  const activities = activityEvents.filter(row => {
    const key = row.candidate_id != null ? `candidate-${row.candidate_id}` : row.job_id != null ? `job-${row.job_id}` : row.id;
    if (seenActivity.has(key)) return false;
    seenActivity.add(key);
    return true;
  }).slice(0, 5);
  const upcoming = interviewRows.filter(r => matchesJob(r) && matchesPerson(r) && date(r.interview_start) >= now && !['cancelled', 'canceled', 'completed'].includes(String(r.status).toLowerCase())).sort((a, b) => date(a.interview_start) - date(b.interview_start)).slice(0, 5);
  const missingDates = candidates.filter(r => !date(r.uploaded_at || r.created_at)).length;
  return {
    metrics, candidates: scoped, jd_reports: jobReports, skill_gaps: list(reports?.skill_gaps).filter(r => Number(r.jd_count) || Number(r.candidate_count)), funnel: pipeline,
    analytics: {
      pipeline, kpis: [{ name: 'Total Candidates', count: numeric(metrics.total_candidates), detail: filtered ? 'Candidates in selected cohort' : 'Current candidate pool' },
        { name: 'Screened', count: numeric(metrics.screened_candidates), detail: 'Candidates with a recorded decision' },
        { name: filtered ? 'My Interviews' : 'Interviews', count: interviewCount, detail: filtered ? 'Scheduled events in this period' : 'Recorded interview events' },
        { name: 'Selected', count: numeric(metrics.selected_candidates), detail: 'Screening selections, not hires' }],
      sources, distribution: hasSources ? sources : byStatus, distribution_title: hasSources ? 'Candidates by Source' : 'Candidates by Status',
      trend, score_bands: scoreRows.length ? scoreBands : [], status_breakdown: byStatus,
      activities, upcoming_interviews: upcoming, interviews_error: warnings.find(w => w.startsWith('Interviews')) || '',
      jobs: options, filter_statuses: [...new Set(candidates.map(outcome))].sort(), filter_sources: [...new Set(candidates.map(r => r.candidate_source || 'Unknown'))].sort(), candidate_data_available: Array.isArray(dashboard?.candidates), filtered,
      notes: [...warnings, filtered ? 'Date filters use candidate upload dates and current outcomes; job filters use the primary JD relationship.' : 'Candidate totals count unique records and their current primary-job screening outcomes. All-time operational comparison totals remain available in Job Analysis.',
        'Selected and Rejected are screening outcomes, not consecutive hiring stages. No offer or hire stages are inferred.',
        'Upcoming interviews are your scheduled future interviews; job, status and source filters apply, but the date filter does not hide future appointments.',
        'Status and source filters narrow candidate analytics and linked interviews. Job-only activity is omitted when a candidate segment is selected.',
        'Skill-gap analysis is the existing all-time report and is labelled separately from filtered candidate charts.',
        `${missingDates} candidate records lack usable upload dates and are excluded from dated views.`,
        'Monthly charts use recorded upload dates. Historical screening, hiring and percentage-change data are not available.'],
    },
  };
}
