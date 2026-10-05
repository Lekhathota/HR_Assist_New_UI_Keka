import { buildAnalyticsView } from './analyticsView.js';
const filters = { allTime: true, job: '', start: '2026-01-01', end: '2026-01-31' };
const rows = [
  { id: 1, jd_id: 8, status: 'Selected', match_score: 80, uploaded_at: '2026-01-01T00:00:00', candidate_source: 'Vendor' },
  { id: 2, jd_id: 9, status: 'Rejected', match_score: 20, uploaded_at: '2026-02-01T00:00:00' },
  { id: 3, jd_id: 8, status: 'Pending' },
];
const snapshot = { dashboard: { candidates: rows, metrics: { internal_interviews: 4 } }, reports: { jd_reports: [{ title: 'Engineer', selected: 1, total_screened: 2 }], skill_gaps: [{ name: 'Python', jd_count: 1, candidate_count: 2 }] }, jobs: [{ id: 8, title: 'Engineer' }], interviews: { interviews: [] } };

test('existing contracts provide four real KPIs without invented hiring stages', () => {
  const result = buildAnalyticsView(snapshot, filters);
  expect(result.analytics.kpis.map(r => [r.name, r.count])).toEqual([['Total Candidates', 3], ['Screened', 2], ['Interviews', 4], ['Selected', 1]]);
  expect(result.analytics.pipeline.map(r => r.name)).toEqual(['Uploaded', 'Screened', 'Selected', 'Rejected']);
  expect(result.jd_reports).toEqual(snapshot.reports.jd_reports);
});
test('date and primary-job filters operate on real records with exclusive next-day boundary', () => {
  const result = buildAnalyticsView(snapshot, { ...filters, allTime: false, job: '8' });
  expect(result.metrics.total_candidates).toBe(1);
  expect(result.analytics.score_bands.find(r => r.name === '61–80').count).toBe(1);
  expect(result.jd_reports[0].total_screened).toBe(1);
  expect(result.skill_gaps).toEqual(snapshot.reports.skill_gaps);
});
test('interviews object response uses real interviewer and job fields', () => {
  const upcoming = { id: 3, candidate_name: 'Real Candidate', interview_start: '2026-03-01', interviewer: 'Real Interviewer', job_role: 'Engineer' };
  const result = buildAnalyticsView({ ...snapshot, interviews: { interviews: [upcoming, { ...upcoming, id: 4, status: 'Cancelled' }] } }, filters, new Date('2026-02-01'));
  expect(result.analytics.upcoming_interviews).toEqual([upcoming]);
});
test('deduplicates candidates and uses status distribution when sources are not recorded', () => {
  const result = buildAnalyticsView({ dashboard: { candidates: [{ id: 1, status: 'Selected' }, { id: 1, status: 'Selected' }], metrics: {} } }, filters);
  expect(result.metrics.total_candidates).toBe(1);
  expect(result.analytics.distribution_title).toBe('Candidates by Status');
  expect(result.analytics.distribution).toEqual([{ name: 'Selected', count: 1 }]);
});
test('missing supporting data never becomes a filtered zero or fabricated skill', () => {
  expect(() => buildAnalyticsView({ reports: { metrics: {} } }, { ...filters, allTime: false })).toThrow('unavailable');
  const result = buildAnalyticsView({ reports: { metrics: {}, skill_gaps: [{ name: 'Python', jd_count: 0, candidate_count: 0 }] } }, filters);
  expect(result.skill_gaps).toEqual([]);
  expect(result.analytics.kpis[0].count).toBeNull();
});

test('recent activity keeps the newest event per candidate and job', () => {
  const result = buildAnalyticsView({ dashboard: { candidates: [], recent_candidates: [{ id: 1, name: 'A', uploaded_at: '2026-01-01' }], recent_comparisons: [{ id: 2, candidate_id: 1, candidate_name: 'A', comparison_date: '2026-01-03' }, { id: 3, candidate_id: 1, comparison_date: '2026-01-02' }], recent_jds: [{ id: 8, title: 'Job', created_at: '2026-01-01' }] } }, filters);
  expect(result.analytics.activities).toHaveLength(2);
  expect(result.analytics.activities[0].activity).toBe('Resume compared');
  expect(result.analytics.activities[1].job_id).toBe(8);
});

test('multiple jobs combine as a union, then status and source narrow the cohort', () => {
  expect(buildAnalyticsView(snapshot, { ...filters, jobs: ['8', '9'] }).metrics.total_candidates).toBe(3);
  const result = buildAnalyticsView(snapshot, { ...filters, jobs: ['8', '9'], status: 'Selected', source: 'Vendor' });
  expect(result.metrics.total_candidates).toBe(1);
  expect(result.analytics.filter_statuses).toEqual(['Pending', 'Rejected', 'Selected']);
  expect(result.analytics.filter_sources).toEqual(['Unknown', 'Vendor']);
  expect(buildAnalyticsView(snapshot, { ...filters, jobs: ['9'], source: 'Vendor' }).metrics.total_candidates).toBe(0);
});
