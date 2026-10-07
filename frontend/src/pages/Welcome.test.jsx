import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import Welcome from './Welcome.jsx';
import ReportAnalytics from '../components/ReportAnalytics.jsx';
import { apiGet } from '../api.js';
import { buildAnalyticsView } from '../utils/analyticsView.js';

jest.mock('../api.js', () => ({ apiGet: jest.fn() }));
jest.mock('../components/Layout.jsx', () => ({ children }) => <main>{children}</main>);
jest.mock('../components/HomeDetails.jsx', () => () => <p>Preserved operational reports</p>);

const dashboard = {
  candidates: [{ id: 7, name: 'Fixture Candidate', status: 'Selected', jd_id: 1, candidate_source: 'Direct', match_score: 80, uploaded_at: '2026-01-15T10:00:00Z' }],
  metrics: { total_candidates: 1, total_jds: 1, active_jobs: 1, internal_interviews: 1 },
  recent_candidates: [{ id: 7, name: 'Fixture Candidate', jd_id: 1, uploaded_at: '2026-01-15T10:00:00Z' }],
};
const reports = { jd_reports: [{ id: 1, title: 'Engineer', total_screened: 1, selected: 1, rejected: 0, avg_match: 80 }], skill_gaps: [{ name: 'Python', jd_count: 1, candidate_count: 2 }] };
const jobs = [{ id: 1, title: 'Engineer' }];
const interviews = { interviews: [{ id: 4, candidate_id: 7, candidate_name: 'Fixture Candidate', jd_id: 1, interview_start: '2027-02-01T10:00:00Z', interviewer: 'Fixture Interviewer' }] };
const fixture = buildAnalyticsView({ dashboard, reports, jobs, interviews }, { allTime: true, job: '' });
let root, container;
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.setItem('recruitment_assist_user', JSON.stringify({ username: 'User', role: 'admin' }));
  apiGet.mockImplementation(path => Promise.resolve(path === '/api/dashboard' ? dashboard : path === '/api/interviews' ? interviews : jobs));
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); localStorage.clear(); });

test('Home renders real cohort charts, activity and interviews without duplicating detailed reports', async () => {
  await act(async () => root.render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><Welcome /></MemoryRouter>));
  expect(container.querySelector('h1').textContent).toBe('Welcome back, User!');
  expect(container.querySelectorAll('.insight-kpi')).toHaveLength(4);
  expect(container.querySelectorAll('svg')).toHaveLength(3);
  expect(container.querySelector('a[href="/talent/7"]')).not.toBeNull();
  expect(container.textContent).toContain('Upcoming Interviews');
  expect(container.textContent).not.toContain('Preserved operational reports');
  expect(container.textContent).not.toContain('Job Performance');
});

test('all report tabs work with keyboard navigation and expose real/unavailable data', () => {
  act(() => root.render(<ReportAnalytics data={fixture} />));
  expect(container.textContent).toContain('Candidates by Job Role');
  const key = value => act(() => container.querySelector('[aria-selected="true"]').dispatchEvent(new KeyboardEvent('keydown', { key: value, bubbles: true })));
  key('ArrowRight');
  expect(container.querySelector('[aria-selected="true"]').textContent).toBe('Job Analysis');
  expect(container.querySelector('[role="tabpanel"]').textContent).toContain('Job Performance');
  key('ArrowRight');
  expect(container.querySelector('[role="tabpanel"]').textContent).toContain('Match Score Distribution');
  key('End');
  expect(container.querySelector('[role="tabpanel"]').textContent).toContain('Python');
  key('Home');
  expect(container.querySelector('[aria-selected="true"]').textContent).toBe('Hiring Overview');
});

test('Reports overview hides rejected in both outcomes and percentages', () => {
  act(() => root.render(<ReportAnalytics data={fixture} />));
  const panels = [...container.querySelectorAll('.insight-panel')];
  const outcomes = panels.find(panel => panel.textContent.includes('Screening Outcomes'));
  const percentages = panels.find(panel => panel.textContent.includes('Screening Percentages'));
  expect(outcomes.textContent).not.toContain('Rejected');
  expect(percentages.textContent).not.toContain('Rejected');
  expect(percentages.textContent).toContain('Selected');
});
