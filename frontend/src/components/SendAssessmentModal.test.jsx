import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import SendAssessmentModal from './SendAssessmentModal.jsx';
import CandidateAssessments from './CandidateAssessments.jsx';
import { apiGet, apiPost } from '../api.js';
import { toast } from './EnterpriseFeedback.jsx';

jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiPost: jest.fn() }));
jest.mock('./EnterpriseFeedback.jsx', () => ({ toast: jest.fn() }));

const JDS = [
  { id: 20, title: 'QA Engineer', client_name: 'Acme', status: 'Active', skills: ['Selenium', 'SQL'], location: 'Pune' },
  { id: 21, title: 'Data Analyst', client_name: '', status: 'Active' },
  { id: 22, title: 'Old Role', client_name: 'Acme', status: 'Closed' },
];
const LINK = 'https://hr.example.com/assessment/0b7d3c55-6a2e-4a3b-9b3d-1f0e2a3b4c5d';
const sentAssessment = {
  id: 1, jd_id: 20, jd_title: 'QA Engineer', client_name: 'Acme', lifecycle: 'awaiting_response',
  lifecycle_label: 'Email sent · awaiting candidate', candidate_email: 'asha@example.com',
  token_expires_at: '2026-10-22T10:00:00+00:00', assessment_link: LINK,
};
const rejected = { id: 10, name: 'Asha Rao', email: 'asha@example.com', status: 'Rejected', jd_id: 20 };

let root, container, onClose, onSent;
const $ = selector => container.querySelector(selector);
const button = text => [...container.querySelectorAll('button')].find(b => b.textContent.trim().includes(text));
const sendCalls = () => apiPost.mock.calls.filter(([path]) => path.endsWith('/assessments/send'));

async function render(ui) {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  await act(async () => root.render(<MemoryRouter>{ui}</MemoryRouter>));
}
const openModal = (candidate = rejected) => render(<SendAssessmentModal candidate={candidate} onClose={onClose} onSent={onSent} />);
const reply = (status, data) => ({ ok: status < 300, status, data });

function selectJd(value) {
  const select = $('#sa-jd');
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, String(value));
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
}
function typeEmail(value) {
  const input = $('#sa-email');
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
async function clickSend(label = 'Generate & Review Assessment') {
  await act(async () => button(label).click());
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  onClose = jest.fn(); onSent = jest.fn();
  apiGet.mockImplementation(path => (path === '/api/jds' ? Promise.resolve(JDS) : Promise.resolve({})));
  Object.assign(navigator, { clipboard: { writeText: jest.fn().mockResolvedValue() } });
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.clearAllMocks(); });

describe('Generate Assessment modal', () => {
  test('generation stops at a draft and links to the preview; nothing is emailed', async () => {
    apiPost.mockResolvedValue(reply(200, { success: true, code: 'draft_ready', message: 'The assessment was generated as a draft. Review it in the preview, then send it.',
      assessment: { ...sentAssessment, id: 77, lifecycle_label: 'Assessment generated', assessment_link: '' } }));
    await openModal();
    await clickSend();
    expect(container.textContent).toContain('generated as a draft');
    expect(container.textContent).toContain('Will be sent to');
    const review = [...container.querySelectorAll('a')].find(a => a.textContent.includes('Review & Send'));
    expect(review.getAttribute('href')).toBe('/hiring-pipeline/assessment/77?preview=1');
    expect(container.textContent).not.toContain('Copy link');
  });

  test('lists JDs from the API with client, preselects the candidate JD and disables closed JDs', async () => {
    await openModal();
    expect(apiGet).toHaveBeenCalledWith('/api/jds');
    expect(container.textContent).toContain('Generate Assessment');
    expect(container.textContent).toContain('Rejected at screening');
    const options = [...$('#sa-jd').options];
    expect(options.map(o => o.textContent)).toEqual(['Select a job description…', 'QA Engineer · Acme', 'Data Analyst', 'Old Role · Acme (closed)']);
    expect(options[3].disabled).toBe(true);
    expect($('#sa-jd').value).toBe('20');
    expect(container.textContent).toContain('Pune · 2 skills');
    expect(button('Cancel')).toBeTruthy();
  });

  test('Generate & Send is disabled until a JD is selected', async () => {
    await openModal({ ...rejected, jd_id: null });
    expect(button('Generate & Review Assessment').disabled).toBe(true);
    selectJd(21);
    expect(button('Generate & Review Assessment').disabled).toBe(false);
  });

  test('sends a rejected candidate the assessment and offers the link to copy', async () => {
    apiPost.mockResolvedValue(reply(200, { success: true, code: 'sent', message: 'Assessment sent to asha@example.com.', assessment: sentAssessment }));
    await openModal();
    await clickSend();
    const [path, body] = sendCalls()[0];
    expect(path).toBe('/api/candidates/10/assessments/send');
    expect(body).toEqual(expect.objectContaining({ jd_id: 20, to_email: '', resend: false }));
    expect(body.request_id).toEqual(expect.any(String));
    expect(container.textContent).toContain('Assessment sent to asha@example.com.');
    expect(container.textContent).toContain('Email sent · awaiting candidate');
    expect($('input[aria-label="Assessment link"]').value).toBe(LINK);
    await act(async () => button('Copy link').click());
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(LINK);
    expect(onSent).toHaveBeenCalledWith(sentAssessment);
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ type: 'success' }));
    await act(async () => button('Done').click());
    expect(onClose).toHaveBeenCalled();
  });

  test('shows a loading state while generating and blocks closing', async () => {
    let resolve;
    apiPost.mockImplementation(() => new Promise(r => { resolve = r; }));
    await openModal();
    await clickSend();
    expect(button('Generating…').disabled).toBe(true);
    expect(button('Cancel').disabled).toBe(true);
    expect($('.jd-modal-close').disabled).toBe(true);
    expect(container.textContent).toContain('Generating and validating the assessment');
    await act(async () => resolve(reply(200, { success: true, code: 'sent', message: 'Sent', assessment: sentAssessment })));
    expect(button('Done')).toBeTruthy();
  });

  test('a candidate without an email must be given one; the corrected address is sent explicitly', async () => {
    apiPost.mockResolvedValue(reply(200, { success: true, code: 'sent', message: 'Sent', assessment: sentAssessment }));
    await openModal({ ...rejected, email: '' });
    expect($('#sa-email')).toBeTruthy();
    expect(button('Generate & Review Assessment').disabled).toBe(true);
    typeEmail('asha.rao@example.com');
    await clickSend();
    expect(sendCalls()[0][1].to_email).toBe('asha.rao@example.com');
  });

  test('an invalid resume email is shown for correction instead of being replaced silently', async () => {
    apiPost.mockResolvedValueOnce(reply(422, { code: 'email_invalid', error: '“asha@example” is not a valid email address.', email: 'asha@example' }));
    await openModal({ ...rejected, email: 'asha@example' });
    await clickSend();
    expect($('[role="alert"]').textContent).toContain('not a valid email address');
    expect($('#sa-email').value).toBe('asha@example');
    expect($('#sa-email').getAttribute('aria-invalid')).toBe('true');
    apiPost.mockResolvedValueOnce(reply(200, { success: true, code: 'sent', message: 'Sent', assessment: sentAssessment }));
    typeEmail('asha@example.com');
    await clickSend();
    expect(sendCalls()[1][1].to_email).toBe('asha@example.com');
  });

  test('generation failure can be retried with the same request id', async () => {
    apiPost.mockResolvedValueOnce(reply(502, { code: 'generation_failed', error: 'Assessment generation failed: AI unavailable.' }));
    await openModal();
    await clickSend();
    expect($('[role="alert"]').textContent).toContain('Assessment generation failed');
    expect(onSent).not.toHaveBeenCalled();
    apiPost.mockResolvedValueOnce(reply(200, { success: true, code: 'sent', message: 'Sent', assessment: sentAssessment }));
    await clickSend('Retry generation');
    expect(sendCalls()).toHaveLength(2);
    expect(sendCalls()[1][1].request_id).toBe(sendCalls()[0][1].request_id);
  });

  test('a dropped connection is safe to retry: the same request id is reused', async () => {
    apiPost.mockRejectedValueOnce(new Error('Failed to fetch'));
    await openModal();
    await clickSend();
    expect($('[role="alert"]').textContent).toContain('will not create a second assessment or send a second email');
    apiPost.mockResolvedValueOnce(reply(200, { success: true, code: 'replayed', message: 'Already processed', assessment: sentAssessment }));
    await clickSend('Retry');
    expect(sendCalls()[1][1].request_id).toBe(sendCalls()[0][1].request_id);
    expect(container.textContent).toContain('Already processed');
  });

  test('email failure explains the assessment was kept and offers Retry sending', async () => {
    apiPost.mockResolvedValueOnce(reply(502, { code: 'delivery_failed', error: 'The email could not be sent: SMTP down', assessment_id: 1 }));
    await openModal();
    await clickSend();
    expect(container.textContent).toContain('it is not generated again');
    expect(button('Retry sending')).toBeTruthy();
    expect(onSent).toHaveBeenCalledWith(null);
  });

  test('an already-sent assessment is only re-sent on explicit confirmation, with a new request id', async () => {
    apiPost.mockResolvedValueOnce(reply(409, { code: 'already_sent', error: 'This assessment was already emailed to the candidate. Resend the same link?', assessment: sentAssessment }));
    await openModal();
    await clickSend();
    expect(container.textContent).toContain('already emailed');
    expect($('input[aria-label="Assessment link"]').value).toBe(LINK);
    apiPost.mockResolvedValueOnce(reply(200, { success: true, code: 'sent', message: 'Assessment sent.', assessment: sentAssessment }));
    await act(async () => button('Resend same link').click());
    const [first, second] = sendCalls();
    expect(second[1].resend).toBe(true);
    expect(second[1].request_id).not.toBe(first[1].request_id);
  });

  test('uncertain delivery warns and offers a resend instead of resending automatically', async () => {
    apiPost.mockResolvedValueOnce(reply(202, { success: true, code: 'delivery_unknown', message: 'The mail server did not confirm delivery.', assessment: { ...sentAssessment, lifecycle_label: 'Email delivery uncertain' } }));
    await openModal();
    await clickSend();
    expect($('.sa-banner.warn').textContent).toContain('did not confirm delivery');
    expect(button('Resend same link')).toBeTruthy();
    expect(sendCalls()).toHaveLength(1);
  });

  test('an attempt in progress cannot be replaced', async () => {
    apiPost.mockResolvedValueOnce(reply(409, { code: 'attempt_in_progress', error: 'The candidate is taking this assessment now.', assessment: sentAssessment }));
    await openModal();
    await clickSend();
    expect(container.textContent).toContain('taking this assessment now');
    expect(button('Resend same link')).toBeUndefined();
  });

  test('JD loading failure can be retried', async () => {
    apiGet.mockRejectedValueOnce(new Error('offline'));
    await openModal();
    expect(container.textContent).toContain('Could not load job descriptions');
    await act(async () => button('Retry').click());
    expect($('#sa-jd')).toBeTruthy();
  });

  test('Cancel and Escape close the modal', async () => {
    await openModal();
    await act(async () => button('Cancel').click());
    act(() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});

describe('All Details assessments card', () => {
  const evaluated = {
    ...sentAssessment, id: 2, lifecycle: 'evaluated', lifecycle_label: 'Evaluated', assessment_link: '', passing_score: 70,
    screening_override: true, initiated_by: 'rec', created_at: '2026-10-10T09:00:00+00:00', email_sent_at: '2026-10-10T09:01:00+00:00',
    completed_at: '2026-10-11T10:00:00+00:00', email_delivery_status: 'sent',
    result: { percentage: 82.5, passed: true, pending_review_count: 0 },
    delivery_history: [
      { status: 'failed', at: '2026-10-10T09:00:30+00:00', to_email: 'asha@example.com', error: 'SMTP down', by: 'rec' },
      { status: 'sent', at: '2026-10-10T09:01:00+00:00', to_email: 'asha@example.com', by: 'rec' },
    ],
  };

  test('shows status, result, delivery, attempt history and link actions', async () => {
    apiGet.mockResolvedValue({ assessments: [{ ...sentAssessment, email_delivery_status: 'sent', delivery_history: [] }, evaluated], generation_failures: [] });
    const onSend = jest.fn();
    await render(<CandidateAssessments candidateId="10" onSend={onSend} />);
    expect(apiGet).toHaveBeenCalledWith('/api/candidates/10/assessments');
    expect(container.textContent).toContain('Email sent · awaiting candidate');
    expect(container.textContent).toContain('82.5%');
    expect(container.textContent).toContain('Passed');
    expect(container.textContent).toContain('Sent after resume screening by rec');
    expect(container.textContent).toContain('Generated');
    expect(container.textContent).toContain('Submitted');
    expect(container.querySelectorAll('.sa-item')[1].textContent).not.toContain('Copy link');
    await act(async () => button('Copy link').click());
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(LINK);
    expect(container.querySelector('a[href="/hiring-pipeline/assessment/2"]').textContent).toContain('View result');
    await act(async () => button('Email history (2)').click());
    expect(container.querySelector('.sa-history').textContent).toContain('SMTP down');
    await act(async () => button('Send assessment').click());
    expect(onSend).toHaveBeenCalled();
  });

  test('lists generation failures with a retry', async () => {
    apiGet.mockResolvedValue({ assessments: [], generation_failures: [{ jd_id: 20, jd_title: 'QA Engineer', error: 'AI unavailable', at: '2026-10-12T09:00:00+00:00' }] });
    const onSend = jest.fn();
    await render(<CandidateAssessments candidateId="10" onSend={onSend} />);
    expect(container.textContent).toContain('Generation failed for QA Engineer');
    await act(async () => button('Retry').click());
    expect(onSend).toHaveBeenCalled();
  });

  test('empty and error states', async () => {
    apiGet.mockResolvedValueOnce({ assessments: [], generation_failures: [] });
    await render(<CandidateAssessments candidateId="10" />);
    expect(container.textContent).toContain('No assessments yet');
    act(() => root.unmount()); container.remove();
    apiGet.mockRejectedValueOnce(new Error('Forbidden: insufficient role permissions.'));
    await render(<CandidateAssessments candidateId="10" />);
    expect(container.textContent).toContain('Forbidden');
  });

  test('reloads when a new assessment is sent', async () => {
    apiGet.mockResolvedValue({ assessments: [], generation_failures: [] });
    await render(<CandidateAssessments candidateId="10" refreshKey={0} />);
    await act(async () => root.render(<MemoryRouter><CandidateAssessments candidateId="10" refreshKey={1} /></MemoryRouter>));
    expect(apiGet).toHaveBeenCalledTimes(2);
  });
});
