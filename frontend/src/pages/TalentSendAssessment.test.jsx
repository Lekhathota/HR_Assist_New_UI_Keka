import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Candidates from './Candidates.jsx';
import CandidateProfile from './CandidateProfile.jsx';
import { apiGet, apiPost } from '../api.js';

jest.mock('../api.js', () => ({
  TALENT_CACHE_KEY: 'talent',
  apiGet: jest.fn(),
  apiPost: jest.fn(),
  readSessionCache: () => null,
  writeSessionCache: () => {},
}));
jest.mock('../components/Layout.jsx', () => ({ children }) => <main>{children}</main>);
jest.mock('../components/EnterpriseFeedback.jsx', () => ({ toast: jest.fn(), useConfirm: () => jest.fn(), SkeletonBlock: () => null }));
jest.mock('../utils/useRoleCategories.js', () => ({ useRoleCategories: () => [] }));
jest.mock('jspdf', () => function JsPdf() {});
jest.mock('jspdf-autotable', () => ({}));
jest.mock('docx', () => ({}));
jest.mock('file-saver', () => ({ saveAs: jest.fn() }));
jest.mock('xlsx', () => ({}));

const rejected = { id: 10, name: 'Asha Rao', email: 'asha@example.com', status: 'Rejected', jd_id: 20, client_name: 'Acme', job_applications: [] };
const JDS = [{ id: 20, title: 'QA Engineer', client_name: 'Acme', status: 'Active' }];

let root, container;
const button = text => [...container.querySelectorAll('button')].find(b => b.textContent.trim().includes(text));

async function render(path) {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  await act(async () => root.render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/talent" element={<Candidates />} />
        <Route path="/talent/:candidateId" element={<CandidateProfile />} />
      </Routes>
    </MemoryRouter>,
  ));
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.setItem('recruitment_assist_user', JSON.stringify({ role: 'recruiter' }));
  apiGet.mockImplementation(path => {
    if (path === '/api/candidates') return Promise.resolve([rejected]);
    if (path === '/api/candidates/10') return Promise.resolve({ candidate: rejected, timeline: [] });
    if (path === '/api/candidates/10/assessments') return Promise.resolve({ assessments: [], generation_failures: [] });
    if (path === '/api/jds') return Promise.resolve(JDS);
    return Promise.resolve({});
  });
  apiPost.mockResolvedValue({ ok: true, status: 200, data: {
    success: true, code: 'sent', message: 'Assessment sent to asha@example.com.',
    assessment: { id: 1, jd_title: 'QA Engineer', lifecycle_label: 'Email sent · awaiting candidate', assessment_link: '' },
  } });
});
afterEach(() => { act(() => root.unmount()); container.remove(); localStorage.clear(); jest.clearAllMocks(); });

test('Talent row actions menu offers Send Assessment', async () => {
  await render('/talent');
  await act(async () => container.querySelector('button[aria-label="Actions for Asha Rao"]').click());
  const items = [...container.querySelectorAll('[role="menuitem"]')].map(item => item.textContent.trim());
  expect(items).toEqual(['All Details', 'Send Assessment', 'Remove']);

  await act(async () => [...container.querySelectorAll('[role="menuitem"]')].find(item => item.textContent.includes('Send Assessment')).click());
  expect(container.textContent).toContain('Generate Assessment');
  expect(container.querySelector('#sa-jd').value).toBe('20');
  await act(async () => button('Generate & Send Assessment').click());
  expect(apiPost).toHaveBeenCalledWith('/api/candidates/10/assessments/send', expect.objectContaining({ jd_id: 20 }));
  expect(container.textContent).toContain('Assessment sent to asha@example.com.');
});

test('All Details uses the same workflow, lists assessments and keeps existing actions', async () => {
  await render('/talent/10');
  expect(container.textContent).toContain('Generate report');
  expect(container.textContent).toContain('Remove');
  expect(container.textContent).toContain('Hiring stage');
  expect(container.textContent).toContain('Assessments');
  expect(apiGet).toHaveBeenCalledWith('/api/candidates/10/assessments');

  await act(async () => [...container.querySelectorAll('.cp-hero-actions button')].find(b => b.textContent.includes('Send assessment')).click());
  await act(async () => button('Generate & Send Assessment').click());
  expect(apiPost).toHaveBeenCalledWith('/api/candidates/10/assessments/send', expect.objectContaining({ jd_id: 20 }));
  // The card reloads to show the new attempt.
  expect(apiGet.mock.calls.filter(([p]) => p === '/api/candidates/10/assessments')).toHaveLength(2);
});

test('roles without stage access do not see the All Details assessment controls', async () => {
  localStorage.setItem('recruitment_assist_user', JSON.stringify({ role: 'finance' }));
  await render('/talent/10');
  expect(container.querySelector('.sa-panel')).toBeNull();
  expect(button('Send assessment')).toBeUndefined();
});
