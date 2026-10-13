import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import HiringPipeline from './Interviews.jsx';
import { apiGet, apiPost } from '../api.js';

jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiPost: jest.fn() }));
jest.mock('../components/Layout.jsx', () => ({ children }) => <div>{children}</div>);
jest.mock('../components/EnterpriseFeedback.jsx', () => ({ toast: jest.fn() }));

const pastInterview = {
  id: 7, candidate_id: 3, candidate_name: 'Asha Rao', job_role: 'QA Engineer', status: 'Scheduled',
  interview_start: '2020-01-06T10:00:00', interview_end: '2020-01-06T11:00:00', interviewer: 'Ravi',
};

let root, container, interviews;
const $ = s => container.querySelector(s);
const button = text => [...container.querySelectorAll('button')].find(b => b.textContent.trim().includes(text));

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  interviews = [pastInterview];
  apiGet.mockImplementation(path => {
    if (path.startsWith('/api/interviews/defaults')) return Promise.resolve({});
    if (path.startsWith('/api/interviews')) return Promise.resolve({ interviews });
    if (path.startsWith('/api/interview-recovery/cases/')) return Promise.resolve({ case: {
      id: 1, recovery_type: 'NO_SHOW', status: 'AWAITING_RESPONSE', stage: 'awaiting_consent', attempt_count: 1, max_attempts: 3,
      detected_at: '2026-10-12T09:00:00+00:00',
      history: [
        { id: 1, action: 'no_show_detected', created_at: '2026-10-12T09:00:00+00:00' },
        { id: 2, action: 'no_show_outreach', message_type: 'no_show_outreach', attempt_number: 1, delivery_status: 'sent', created_at: '2026-10-12T09:00:01+00:00' },
      ],
    } });
    return Promise.resolve({ pipeline: [] });
  });
  jest.spyOn(window, 'confirm').mockReturnValue(true);
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  await act(async () => root.render(<MemoryRouter><HiringPipeline /></MemoryRouter>));
  await act(async () => [...container.querySelectorAll('[role="tab"]')].find(t => t.textContent.includes('Interviews')).click());
  await act(async () => [...container.querySelectorAll('button')].find(b => b.textContent.trim().startsWith('Past')).click());
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.restoreAllMocks(); jest.clearAllMocks(); });

test('ended interviews offer explicit attendance outcomes', async () => {
  apiPost.mockResolvedValue({ ok: true, data: { success: true } });
  interviews = [{ ...pastInterview, status: 'No Show', attendance_status: 'no_show', recovery: {
    id: 1, recovery_type: 'NO_SHOW', status: 'AWAITING_RESPONSE', stage: 'awaiting_consent', attempt_count: 1, max_attempts: 3,
    last_outreach_at: '2026-10-12T09:00:01+00:00',
  } }];
  await act(async () => button('No-show').click());
  expect(window.confirm).toHaveBeenCalled();
  expect(apiPost).toHaveBeenCalledWith('/api/interviews/7/attendance', { attendance: 'no_show' });
  expect(container.textContent).toContain('Outreach sent · awaiting reply');
  expect(container.textContent).toContain('Follow-ups sent: 1/3');
  expect(button('No-show')).toBeUndefined();
});

test('follow-up history shows attempts and delivery status', async () => {
  interviews = [{ ...pastInterview, status: 'No Show', recovery: { id: 1, recovery_type: 'NO_SHOW', status: 'ESCALATED', attempt_count: 3, max_attempts: 3 } }];
  apiPost.mockResolvedValue({ ok: true, data: { success: true } });
  await act(async () => button('Attended').click());
  expect(apiPost).toHaveBeenCalledWith('/api/interviews/7/attendance', { attendance: 'attended' });
  await act(async () => button('Escalated to recruiter').click());
  expect(apiGet).toHaveBeenCalledWith('/api/interview-recovery/cases/1');
  expect(container.textContent).toContain('No-show follow-up');
  expect(container.textContent).toContain('Email sent');
  expect(container.textContent).toContain('(attempt 1)');
});
