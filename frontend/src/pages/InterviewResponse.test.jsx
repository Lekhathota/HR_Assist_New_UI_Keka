import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import InterviewResponse from './InterviewResponse.jsx';
import { publicApiGet, publicApiPost } from '../api.js';

jest.mock('../api.js', () => ({ publicApiGet: jest.fn(), publicApiPost: jest.fn() }));

const slot = { id: '2026-10-12T10:00', start: '2026-10-12T10:00', end: '2026-10-12T11:00', label: 'Mon 12 Oct 2026, 10:00 - 11:00' };
const view = (caseData, actions = {}) => ({
  candidate_first_name: 'Asha', job_role: 'QA Engineer', interview_mode: 'Online',
  interview_start: '2026-10-09T10:00', interview_status: 'Scheduled', timezone: 'Asia/Kolkata', case: caseData,
  actions: { can_request_reschedule: false, can_choose_slot: false, can_respond_no_show: false, can_decline: false, ...actions },
});

let root, container;
const $ = selector => container.querySelector(selector);
const buttons = () => [...container.querySelectorAll('button')];
const button = text => buttons().find(b => b.textContent.includes(text));

async function render() {
  await act(async () => root.render(
    <MemoryRouter initialEntries={['/interview/tok-1']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes><Route path="/interview/:token" element={<InterviewResponse />} /></Routes>
    </MemoryRouter>,
  ));
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.clearAllMocks(); });

test('candidate can request a reschedule with availability windows', async () => {
  publicApiGet.mockResolvedValue(view(null, { can_request_reschedule: true }));
  publicApiPost.mockResolvedValue(view({ status: 'SLOT_PROPOSED', proposed_slots: [slot] }, { can_choose_slot: true, can_decline: true }));
  await render();
  expect(container.textContent).toContain('QA Engineer');
  await act(async () => button('I need to reschedule').click());
  await act(async () => button('Add a time').click());
  await act(async () => button('Find new times').click());
  expect(publicApiPost).toHaveBeenCalledWith('/api/interview-recovery/public/tok-1/reschedule', { reason: '', preferred_windows: [] });
  expect(container.textContent).toContain(slot.label);
});

test('choosing a slot confirms it and shows the booking', async () => {
  publicApiGet.mockResolvedValue(view({ status: 'SLOT_PROPOSED', proposed_slots: [slot] }, { can_choose_slot: true }));
  publicApiPost.mockResolvedValue({ ...view({ status: 'RESCHEDULED', confirmed_slot: slot }), booked: true });
  await render();
  await act(async () => $('.ir-slot').click());
  expect(publicApiPost).toHaveBeenCalledWith('/api/interview-recovery/public/tok-1/confirm', { slot_id: slot.id });
  expect(container.textContent).toContain(`You're booked for ${slot.label}`);
});

test('a slot taken meanwhile shows refreshed options instead of an error', async () => {
  const fresh = { ...slot, id: '2026-10-13T10:00', label: 'Tue 13 Oct 2026, 10:00 - 11:00' };
  publicApiGet.mockResolvedValue(view({ status: 'SLOT_PROPOSED', proposed_slots: [slot] }, { can_choose_slot: true }));
  const conflict = Object.assign(new Error('conflict'), {
    status: 409, data: { ...view({ status: 'SLOT_PROPOSED', proposed_slots: [fresh] }, { can_choose_slot: true }), slot_unavailable: true },
  });
  publicApiPost.mockRejectedValue(conflict);
  await render();
  await act(async () => $('.ir-slot').click());
  expect(container.textContent).toContain('That time was just taken');
  expect(container.textContent).toContain(fresh.label);
  expect($('.ca-inline-error')).toBeNull();
});

test('no-show outreach offers yes and no responses', async () => {
  publicApiGet.mockResolvedValue(view({ status: 'AWAITING_RESPONSE', stage: 'awaiting_consent', recovery_type: 'NO_SHOW' },
    { can_respond_no_show: true, can_decline: true }));
  publicApiPost.mockResolvedValue(view({ status: 'CLOSED', recovery_type: 'NO_SHOW' }));
  await render();
  expect(container.textContent).toContain('We missed you');
  await act(async () => button('no longer interested').click());
  expect(publicApiPost).toHaveBeenCalledWith('/api/interview-recovery/public/tok-1/respond', { wants_reschedule: false });
});

test('invalid links show an unavailable message', async () => {
  publicApiGet.mockRejectedValue(new Error('This interview link is invalid or has expired.'));
  await render();
  expect(container.textContent).toContain('Link unavailable');
});
