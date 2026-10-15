import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import HiringPipeline from './Interviews.jsx';
import { apiGet, apiPost } from '../api.js';
import { toast } from '../components/EnterpriseFeedback.jsx';

jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiPost: jest.fn() }));
jest.mock('../components/Layout.jsx', () => ({ children }) => <div>{children}</div>);
jest.mock('../components/EnterpriseFeedback.jsx', () => ({ toast: jest.fn() }));

const pastInterview = {
  id: 7, candidate_id: 3, candidate_name: 'Asha Rao', job_role: 'QA Engineer', status: 'Scheduled',
  interview_start: '2020-01-06T10:00:00', interview_end: '2020-01-06T11:00:00', interviewer: 'Ravi',
};
const upcomingInterview = { ...pastInterview, interview_start: '2099-01-06T10:00:00', interview_end: '2099-01-06T11:00:00' };
const noShowRecovery = {
  id: 1, recovery_type: 'NO_SHOW', status: 'AWAITING_RESPONSE', stage: 'awaiting_consent', attempt_count: 1, max_attempts: 2,
};

const ALL_LABELS = [
  'Selected', 'Rejected', 'Interested', 'Not Interested', 'Follow-up', 'Outreach Sent · Awaiting Reply',
  'Rescheduled', 'Cancelled', 'No Show', 'Pending Review',
];

let root, container, interviews;
const trigger = () => container.querySelector('.hp-status-trigger');
const options = () => [...container.querySelectorAll('[role="menuitemradio"]')];
const option = label => options().find(o => o.querySelector('.hp-status-option-text > span').textContent === label);
const outcomeCalls = () => apiPost.mock.calls.filter(([path]) => path.endsWith('/outcome'));

async function mount(rows, view = 'Past') {
  interviews = rows;
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  await act(async () => root.render(<MemoryRouter><HiringPipeline /></MemoryRouter>));
  await act(async () => [...container.querySelectorAll('[role="tab"]')].find(t => t.textContent.includes('Interviews')).click());
  await act(async () => [...container.querySelectorAll('button')].find(b => b.textContent.trim().startsWith(view)).click());
}

async function choose(label) {
  await act(async () => trigger().click());
  await act(async () => option(label).click());
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  apiGet.mockImplementation(path => {
    if (path.startsWith('/api/interviews/defaults')) return Promise.resolve({});
    if (path.startsWith('/api/interviews')) return Promise.resolve({ interviews });
    return Promise.resolve({ pipeline: [] });
  });
  apiPost.mockImplementation((path, body) => {
    if (path.endsWith('/outcome')) {
      const row = interviews.find(i => i.id === 7);
      const status = body.outcome === 'selected' ? 'Client Interview Pending' : body.outcome === 'rejected' ? 'Rejected After Interview' : row.status;
      const candidate_status = ['selected', 'rejected'].includes(body.outcome) ? null : body.outcome;
      return Promise.resolve({ ok: true, status: 200, data: { success: true, interview: { ...row, recovery: undefined, status, candidate_status } } });
    }
    if (path.endsWith('/generate-followup')) return Promise.resolve({ ok: true, data: { success: true, subject: 'Thanks', body: 'Hi' } });
    if (path.endsWith('/generate-cancellation')) return Promise.resolve({ ok: true, data: { success: true, subject: 'Cancelled', body: 'Hi' } });
    return Promise.resolve({ ok: true, data: { success: true } });
  });
  jest.spyOn(window, 'confirm').mockReturnValue(true);
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.restoreAllMocks(); jest.clearAllMocks(); });

test('replaces the Selected, Rejected and Follow-up buttons with one dropdown listing every status', async () => {
  await mount([pastInterview]);
  const buttonTexts = [...container.querySelectorAll('.hp-actions > button')].map(b => b.textContent.trim());
  expect(buttonTexts).not.toEqual(expect.arrayContaining(['Selected', 'Rejected', 'Follow-up']));
  expect(trigger().textContent).toContain('Pending Review');
  await act(async () => trigger().click());
  expect(trigger().getAttribute('aria-expanded')).toBe('true');
  expect(options().map(o => o.querySelector('.hp-status-option-text > span').textContent)).toEqual(ALL_LABELS);
  expect(option('Pending Review').getAttribute('aria-checked')).toBe('true');
  expect(option('Interested')).not.toBe(option('Selected'));
});

test.each([
  ['Selected', 'selected', 'Client interview pending'],
  ['Rejected', 'rejected', 'Rejected after interview'],
])('%s records the final outcome through the existing outcome API', async (label, outcome, pill) => {
  await mount([pastInterview]);
  await choose(label);
  expect(apiPost).toHaveBeenCalledWith('/api/interviews/7/outcome', { outcome });
  expect(trigger().textContent).toContain(label);
  expect(container.textContent.toLowerCase()).toContain(pill.toLowerCase());
  expect(toast).toHaveBeenCalledWith(expect.objectContaining({ type: 'success' }));
});

test.each([
  ['Interested', 'interested'],
  ['Not Interested', 'not_interested'],
  ['Outreach Sent · Awaiting Reply', 'awaiting_reply'],
])('%s is saved as a candidate status without touching the no-show follow-up', async (label, value) => {
  await mount([{ ...pastInterview, status: 'No Show', attendance_status: 'no_show', recovery: { ...noShowRecovery, status: 'ESCALATED' } }]);
  await choose(label);
  expect(apiPost).toHaveBeenCalledTimes(1);
  expect(apiPost).toHaveBeenCalledWith('/api/interviews/7/outcome', { outcome: value });
  expect(trigger().textContent).toContain(label);
  // The recovery pill and attempt counter survive the update unchanged.
  expect(container.textContent).toContain('Escalated to recruiter');
  expect(container.textContent).toContain('Follow-ups sent: 1 of 2');
});

test('Pending Review can be chosen from another status', async () => {
  await mount([{ ...pastInterview, candidate_status: 'interested' }]);
  expect(trigger().textContent).toContain('Interested');
  await choose('Pending Review');
  expect(apiPost).toHaveBeenCalledWith('/api/interviews/7/outcome', { outcome: 'pending_review' });
  expect(trigger().textContent).toContain('Pending Review');
});

test('choosing the current status does nothing', async () => {
  await mount([{ ...pastInterview, candidate_status: 'interested' }]);
  await choose('Interested');
  expect(apiPost).not.toHaveBeenCalled();
});

test('Follow-up saves the status and opens the existing follow-up composer', async () => {
  await mount([pastInterview]);
  await choose('Follow-up');
  expect(apiPost).toHaveBeenCalledWith('/api/interviews/7/outcome', { outcome: 'follow_up' });
  expect(apiPost).toHaveBeenCalledWith('/api/interviews/7/generate-followup', { type: 'thanks' });
  expect(container.textContent).toContain('Follow-up Message');
  expect(trigger().textContent).toContain('Follow-up');
});

test('No Show uses the attendance workflow and starts recovery once', async () => {
  await mount([pastInterview]);
  interviews = [{ ...pastInterview, status: 'No Show', attendance_status: 'no_show', recovery: noShowRecovery }];
  await choose('No Show');
  expect(window.confirm).toHaveBeenCalled();
  expect(apiPost).toHaveBeenCalledWith('/api/interviews/7/attendance', { attendance: 'no_show' });
  expect(outcomeCalls()).toHaveLength(0);
  expect(trigger().textContent).toContain('Outreach Sent · Awaiting Reply');
  expect(container.textContent).toContain('Follow-ups sent: 1 of 2');
});

test('No Show is not sent when the recruiter dismisses the confirmation', async () => {
  window.confirm.mockReturnValue(false);
  await mount([pastInterview]);
  await choose('No Show');
  expect(apiPost).not.toHaveBeenCalled();
});

test('Rescheduled opens the existing reschedule dialog for upcoming interviews', async () => {
  await mount([upcomingInterview], 'Upcoming');
  await choose('Rescheduled');
  expect(container.textContent).toContain('Reschedule Interview');
  expect(outcomeCalls()).toHaveLength(0);
});

test('Cancelled opens the existing cancellation dialog for upcoming interviews', async () => {
  await mount([upcomingInterview], 'Upcoming');
  await choose('Cancelled');
  expect(apiPost).toHaveBeenCalledWith('/api/interviews/7/generate-cancellation', { type: 'schedule_conflict' });
  expect(container.textContent).toContain('Cancel Interview');
  expect(outcomeCalls()).toHaveLength(0);
});

test('options that break business rules are disabled with a reason', async () => {
  await mount([upcomingInterview], 'Upcoming');
  expect(trigger().textContent).toContain('Set status');
  await act(async () => trigger().click());
  for (const label of ['Selected', 'Rejected', 'No Show']) {
    expect(option(label).getAttribute('aria-disabled')).toBe('true');
    expect(option(label).textContent).toContain('Available after the interview');
  }
  await act(async () => option('Selected').click());
  expect(apiPost).not.toHaveBeenCalled();
});

test('past interviews cannot be cancelled or manually rescheduled; no-shows cannot be recorded twice', async () => {
  await mount([{ ...pastInterview, status: 'No Show', attendance_status: 'no_show' }]);
  await act(async () => trigger().click());
  expect(option('Cancelled').getAttribute('aria-disabled')).toBe('true');
  expect(option('Rescheduled').getAttribute('aria-disabled')).toBe('true');
  expect(option('No Show').getAttribute('aria-disabled')).toBe('true');
  expect(option('No Show').getAttribute('aria-checked')).toBe('true');
});

test('a recorded outcome keeps only the follow-up email available', async () => {
  await mount([{ ...pastInterview, status: 'Client Interview Pending' }]);
  expect(trigger().textContent).toContain('Selected');
  await act(async () => trigger().click());
  const enabled = options().filter(o => o.getAttribute('aria-disabled') !== 'true').map(o => o.textContent);
  expect(enabled).toEqual(['Follow-up']);
  await act(async () => option('Follow-up').click());
  expect(outcomeCalls()).toHaveLength(0);
  expect(apiPost).toHaveBeenCalledWith('/api/interviews/7/generate-followup', { type: 'thanks' });
});

test('cancelled interviews show the status but cannot change it', async () => {
  await mount([{ ...upcomingInterview, status: 'Cancelled' }], 'Cancelled');
  expect(trigger().textContent).toContain('Cancelled');
  expect(trigger().disabled).toBe(true);
});

test('shows a loading state while the update is saving', async () => {
  let resolve;
  apiPost.mockImplementation(() => new Promise(r => { resolve = r; }));
  await mount([pastInterview]);
  await choose('Interested');
  expect(trigger().textContent).toContain('Saving…');
  expect(trigger().disabled).toBe(true);
  await act(async () => resolve({ ok: true, status: 200, data: { success: true, interview: { ...pastInterview, candidate_status: 'interested' } } }));
  expect(trigger().disabled).toBe(false);
  expect(trigger().textContent).toContain('Interested');
});

test('a rejected update keeps the previous status and shows the error', async () => {
  apiPost.mockResolvedValue({ ok: false, status: 409, data: { error: 'This interview is already Cancelled.' } });
  await mount([pastInterview]);
  await choose('Interested');
  expect(trigger().textContent).toContain('Pending Review');
  expect(container.querySelector('[role="alert"]').textContent).toContain('This interview is already Cancelled.');
  expect(toast).toHaveBeenCalledWith(expect.objectContaining({ type: 'error' }));
});

test('a network failure is reported and cleared on the next successful update', async () => {
  apiPost.mockRejectedValueOnce(new Error('Network down'));
  await mount([pastInterview]);
  await choose('Interested');
  expect(container.querySelector('[role="alert"]').textContent).toContain('Network down');
  await choose('Interested');
  expect(container.querySelector('[role="alert"]')).toBeNull();
  expect(trigger().textContent).toContain('Interested');
});

test('the menu supports keyboard navigation and Escape', async () => {
  await mount([pastInterview]);
  await act(async () => trigger().click());
  expect(document.activeElement).toBe(option('Pending Review'));
  await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true })));
  expect(document.activeElement).toBe(option('Selected'));
  await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
  expect(options()).toHaveLength(0);
  expect(document.activeElement).toBe(trigger());
});
