import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import Profile from './Profile.jsx';
import { apiGet, apiPut } from '../api.js';

jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiPost: jest.fn(), apiPut: jest.fn() }));
jest.mock('../components/Layout.jsx', () => ({ children }) => <main>{children}</main>);
jest.mock('../components/EnterpriseFeedback.jsx', () => ({ toast: jest.fn() }));

let container, root;
beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  apiGet.mockImplementation(path => Promise.resolve({
    '/api/profile': { user: { username: 'lekha', email: 'l@x.io', role: 'admin' } },
    '/api/profile/activity': { jds_created: 4, screenings_run: 2, candidates_added: 17, reports_generated: 3, tracking_since: '2026-10-06T08:00:00Z' },
    '/api/profile/preferences': { preferences: { notify_jobs: true, notify_talent: true, notify_pipeline: false } },
  }[path]));
  apiPut.mockResolvedValue({ ok: true, data: { preferences: { notify_jobs: false, notify_talent: true, notify_pipeline: false } } });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(<MemoryRouter><Profile /></MemoryRouter>));
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.clearAllMocks(); });

test('shows the real activity counts from the server', () => {
  const values = Array.from(container.querySelectorAll('.profile-activity-value')).map(el => el.textContent);
  expect(values).toEqual(['4', '2', '17', '3']);
  expect(container.querySelector('.profile-activity-note').textContent).toContain('when activity tracking began');
});

test('preferences reflect saved values and persist when toggled', async () => {
  const toggles = Array.from(container.querySelectorAll('.profile-toggle input'));
  expect(toggles.map(t => t.checked)).toEqual([true, true, false]);
  await act(async () => toggles[0].click());
  expect(apiPut).toHaveBeenCalledWith('/api/profile/preferences', { notify_jobs: false });
  expect(container.querySelectorAll('.profile-toggle input')[0].checked).toBe(false);
});
