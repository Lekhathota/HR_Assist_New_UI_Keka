import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { useAnalytics, AnalyticsStatus, Chart, AnalyticsFilters } from './Analytics.jsx';
import { apiGet } from '../api.js';
jest.mock('../api.js', () => ({ apiGet: jest.fn() }));
let root, container;
beforeEach(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); jest.clearAllMocks(); });
afterEach(() => { act(() => root.unmount()); container.remove(); });
function Probe() {
  const state = useAnalytics('/api/reports');
  return <><AnalyticsStatus {...state} /><output>{state.data?.metrics?.total_candidates}</output><button id="filter" onClick={() => state.setFilters(f => ({ ...f, job: '9' }))}>Change job</button></>;
}
test('failed primary analytics show retry rather than fabricated values', async () => {
  let failed = true;
  apiGet.mockImplementation(path => path === '/api/reports' ? (failed ? Promise.reject(new Error('Unavailable')) : Promise.resolve({ metrics: { total_candidates: 3 } })) : path === '/api/dashboard' ? Promise.resolve({ candidates: [{ id: 1 }, { id: 2 }, { id: 3 }], metrics: {} }) : Promise.resolve([]));
  await act(async () => root.render(<Probe />));
  expect(container.querySelector('[role="alert"]').textContent).toContain('Unavailable');
  expect(container.querySelector('output').textContent).toBe('');
  failed = false;
  await act(async () => container.querySelector('[role="alert"] button').click());
  expect(container.querySelector('output').textContent).toBe('3');
});
test('job filtering uses loaded records without requiring new backend parameters', async () => {
  apiGet.mockImplementation(path => Promise.resolve(path === '/api/dashboard' ? { candidates: [{ id: 1, jd_id: 9 }, { id: 2, jd_id: 10 }], metrics: {} } : path === '/api/jds' ? [{ id: 9, title: 'Engineer' }] : { metrics: {} }));
  await act(async () => root.render(<Probe />));
  expect(container.querySelector('output').textContent).toBe('2');
  await act(async () => container.querySelector('#filter').click());
  expect(container.querySelector('output').textContent).toBe('1');
  expect(apiGet.mock.calls.map(call => call[0])).toEqual(['/api/reports', '/api/dashboard', '/api/jds']);
});
test('charts expose accessible descriptions and distinguish unavailable stages', () => {
  act(() => root.render(<Chart rows={[{ name: 'Uploaded', count: 4 }, { name: 'Hired', count: null, reason: 'No hire dates' }]} label="Pipeline" />));
  expect(container.querySelector('svg').getAttribute('aria-label')).toBe('Pipeline');
  expect(container.textContent).toContain('No hire dates');
});

test('a single recorded month is centered without inventing a trend line', () => {
  act(() => root.render(<Chart kind="line" rows={[{ name: '2026-09', count: 1 }]} label="Uploads" />));
  expect(container.querySelector('circle').getAttribute('cx')).toBe('210');
  expect(container.querySelector('polyline')).toBeNull();
  expect(container.textContent).toContain('a trend needs more history');
});
test('outcome bars retain full labels and render a genuine zero width', () => {
  act(() => root.render(<Chart kind="funnel" rows={[{ name: 'Selected', count: 1 }, { name: 'Rejected', count: 0 }]} label="Outcomes" />));
  expect(container.querySelectorAll('.chart-bar-track')[1].lastElementChild.getAttribute('width')).toBe('0');
  expect(container.textContent).toContain('Rejected');
});

test('score histogram labels axes and bands without a duplicate legend or fractional candidate ticks', () => {
  act(() => root.render(<Chart kind="histogram" rows={[{ name: '0?20', count: 0 }, { name: '81?100', count: 1 }]} label="Scores" />));
  expect(container.querySelector('.chart-legend')).toBeNull();
  expect(container.textContent).toContain('Match score (%)');
  expect(container.textContent).toContain('candidate with a recorded score');
  expect(container.querySelector('svg').textContent).not.toContain('0.5');
  expect(container.querySelectorAll('rect')[0].getAttribute('height')).toBe('0');
});

test('job checkboxes retain multiple selections and clear all resets filters', () => {
  function FiltersProbe() {
    const [filters, setFilters] = React.useState({ allTime: true, job: '', jobs: [], start: '2026-01-01', end: '2026-01-31' });
    return <><AnalyticsFilters filters={filters} setFilters={setFilters} jobs={[{ id: 8, title: 'Engineer' }, { id: 9, title: 'Analyst' }]} /><output>{JSON.stringify(filters.jobs)}</output></>;
  }
  act(() => root.render(<FiltersProbe />));
  act(() => container.querySelectorAll('input[type="checkbox"]')[0].click());
  act(() => container.querySelectorAll('input[type="checkbox"]')[1].click());
  expect(container.querySelector('output').textContent).toBe('["8","9"]');
  expect(container.textContent).toContain('2 jobs selected');
  act(() => [...container.querySelectorAll('button')].find(button => button.textContent === 'Clear all').click());
  expect(container.querySelector('output').textContent).toBe('[]');
});
