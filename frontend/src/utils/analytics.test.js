import { defaultFilters, analyticsReport } from './analytics.js';

test('default period contains 30 local calendar days', () => {
  const { start, end } = defaultFilters();
  expect((Date.parse(end) - Date.parse(start)) / 86400000).toBe(29);
});
test('all text export formats share filtered real analytics and coverage', () => {
  const output = analyticsReport({ metrics: { total_candidates: 2 }, jd_reports: [], skill_gaps: [], analytics: {
    jobs: [{ id: 7, title: 'Engineer' }], pipeline: [{ name: 'Hired', count: null, reason: 'No hire timestamps' }],
    sources: [{ name: 'Direct', count: 2 }], notes: ['Missing event history'], time_to_hire: { days: null, sample_size: 0 },
  } }, { start: '2026-01-01', end: '2026-01-31', job: '7' });
  expect(output).toContain('Job: Engineer');
  expect(output).toContain('total candidates: 2');
  expect(output).toContain('Hired: Not available');
  expect(output).toContain('Missing event history');
  expect(output).not.toContain('94%');
});

test('export identifies every selected job and candidate segment', () => {
  const text = analyticsReport({ analytics: { jobs: [{ id: 8, title: 'Engineer' }, { id: 9, title: 'Analyst' }] } }, { allTime: true, jobs: ['8', '9'], status: 'Selected', source: 'Vendor' });
  expect(text).toContain('Job: Engineer, Analyst');
  expect(text).toContain('Status: Selected');
  expect(text).toContain('Source: Vendor');
});
