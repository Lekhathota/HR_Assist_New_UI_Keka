import React, { act, useState } from 'react';
import { createRoot } from 'react-dom/client';
import AssessmentPreviewModal from './AssessmentPreviewModal.jsx';
import { apiGet, apiPost, apiPut } from '../api.js';

jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiPost: jest.fn(), apiPut: jest.fn(), apiDelete: jest.fn() }));
jest.mock('./ReferenceSolutionPanel.jsx', () => ({ question, onDirtyChange }) => (
  <div data-testid="config-panel">Coding Configuration for {question.id}
    <button type="button" onClick={() => onDirtyChange(true)}>make dirty</button></div>
));

const ASSESSMENT = { id: 1, status: 'DRAFT', title: 'Senior Full Stack Assessment', job_role: 'Senior Full Stack Engineer · Uber',
  candidate_name: 'Asha Rao', candidate_email: 'asha@example.com', time_limit_minutes: 90, passing_score: 60 };
const mcq = (i, extra = {}) => ({ id: i, question_type: 'mcq', sort_order: i, points: 1, difficulty: i % 2 ? 'Easy' : 'Medium',
  question_text: `MCQ question ${i}?`, options: ['Option A', 'Option B', 'Option C', 'Option D'], correct_answer: 'Option C',
  explanation: `Because of reason ${i}.`, ...extra });
const CODING = { id: 40, question_type: 'coding', sort_order: 40, points: 20, difficulty: 'Medium', title: 'Rate limiter',
  question_text: 'Implement a sliding-window rate limiter.', allowed_languages: ['python', 'java'], input_format: 'n then events',
  output_format: 'allowed count', constraints: 'n <= 10^5', correct_answer: 'print(42)', reference_language: 'python',
  time_limit_seconds: 2, memory_limit_mb: 128, scoring: { min_tests_passed: 2, min_score_percent: 40, partial_credit: true },
  verification: { status: 'not_verified', message: 'The reference solution has not been verified.' },
  test_cases: [
    { id: 't1', hidden: false, input: '3\n1 2 3\n', expected_output: '2\n' },
    { id: 't2', hidden: true, input: 'SECRET-INPUT', expected_output: 'SECRET-OUTPUT', weight: 2, mandatory: true },
  ] };
const SQL = { id: 41, question_type: 'sql', sort_order: 41, points: 10, question_text: 'Latest status per order.', difficulty: 'Medium',
  sql_schema: 'CREATE TABLE orders (id INTEGER);', test_cases: [{ id: 's1', hidden: false, setup_sql: 'INSERT INTO orders VALUES (1);' }], tests_verified: true };
const VERIFIED = [...Array.from({ length: 30 }, (_, i) => mcq(i + 1)), { ...CODING, verification: { status: 'verified', message: 'Verified.' } }, SQL];
const READY = { ready: true, problems: [], questions: [], fingerprint: 'fp-1', mcq_questions: 30, coding_questions: 1, approval: {} };

let root, container, props, current;
const $ = s => container.querySelector(s);
const $$ = s => [...container.querySelectorAll(s)];
const button = (text, scope = container) => [...scope.querySelectorAll('button')].find(b => b.textContent.trim().includes(text));
async function click(el) { await act(async () => el.click()); }
function type(el, value) {
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  act(() => {
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, String(value));
    el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
  });
}

function Harness({ initial, assessment, ...rest }) {
  const [questions, setQuestions] = useState(initial);
  current = questions;
  return <AssessmentPreviewModal assessment={assessment} questions={questions} onQuestionsChange={setQuestions} {...rest} />;
}

async function mount({ questions = [...Array.from({ length: 30 }, (_, i) => mcq(i + 1)), CODING, SQL], assessment = ASSESSMENT, ...rest } = {}) {
  props = { onClose: jest.fn(), onSent: jest.fn(), onSaveDraft: jest.fn().mockResolvedValue(true), ...rest };
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  await act(async () => root.render(<Harness initial={questions} assessment={assessment} {...props} />));
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  jest.spyOn(window, 'confirm').mockReturnValue(true);
  apiGet.mockResolvedValue(READY);
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.restoreAllMocks(); jest.clearAllMocks(); });

test('header, tabs and MCQ cards reflect the saved questions', async () => {
  await mount();
  const summary = $('.pv-summary').textContent;
  expect(summary).toContain('Senior Full Stack Engineer · Uber');
  expect(summary).toContain('Asha Rao');
  expect(summary).toContain('asha@example.com');
  expect(summary).toContain('32 (30 MCQ + 2 Coding)');
  expect(summary).toContain('1 coding · 1 SQL');
  expect(summary).toContain('60');                    // 30 x 1 + 20 + 10 marks
  expect(summary).toContain('90 min');
  expect($('.pv-status').textContent).toBe('Draft — Not Sent');
  expect($$('.pv-tabs button').map(b => b.textContent)).toEqual(['MCQ Questions (30)', 'Coding Questions (2)']);
  const first = $('.pv-card');
  expect(first.textContent).toContain('Question 1 of 30');
  expect(first.textContent).toContain('Easy');
  expect(first.textContent).toContain('1 mark');
  expect(first.querySelector('.pv-correct').textContent).toContain('Option C');
  expect(first.querySelectorAll('.pv-correct')).toHaveLength(1);
  expect(first.textContent).toContain('Because of reason 1.');
  expect($$('.pv-card')).toHaveLength(30);
});

test('coding cards show requirements, samples and summaries but never hidden test data', async () => {
  await mount();
  await click(button('Coding Questions (2)'));
  const card = $('#pv-q-40');
  for (const text of ['Rate limiter', 'Python, Java', 'n then events', 'n <= 10^5', '2s CPU · 128 MB', '3\n1 2 3', '1 public sample, 1 hidden',
    'weighted', '1 mandatory', 'at least 2 test(s) and 40% of the marks', 'Not validated', '20 marks']) {
    expect(card.textContent).toContain(text);
  }
  expect(card.querySelector('.pv-reference').textContent).toContain('print(42)');
  expect(card.textContent).not.toContain('SECRET-INPUT');
  expect(card.textContent).not.toContain('SECRET-OUTPUT');
  expect($('#pv-q-41').textContent).toContain('SQL (SQLite)');
  expect($('#pv-q-41').textContent).toContain('Reference verified');
});

test('Validate Code runs the reference in the sandbox and updates the status', async () => {
  apiPost.mockResolvedValue({ ok: true, data: { verification: { status: 'failed', message: 'The reference solution fails 1 test run(s).' }, test_cases: CODING.test_cases } });
  await mount();
  await click(button('Coding Questions (2)'));
  await click(button('Validate Code', $('#pv-q-40')));
  expect(apiPost).toHaveBeenCalledWith('/api/assessment/question/40/verify', {});
  expect($('#pv-q-40').textContent).toContain('Reference fails tests');
  expect($('#pv-q-40').textContent).toContain('fails 1 test run');
});

test('Validate Assessment first runs references that were never verified', async () => {
  apiPost.mockResolvedValue({ ok: true, data: { verification: { status: 'verified', message: 'Every reference solution passed.' }, test_cases: CODING.test_cases } });
  await mount();
  await click(button('Validate Assessment'));
  expect(apiPost).toHaveBeenCalledTimes(1);  // the coding question only; the SQL one is already verified
  expect(apiPost).toHaveBeenCalledWith('/api/assessment/question/40/verify', {});
  expect(current.find(q => q.id === 40).verification.status).toBe('verified');
  expect($('.pv-valid').textContent).toContain('Ready to send');
});

test('Edit Question opens the coding configuration and its unsaved changes block sending', async () => {
  await mount();
  await click(button('Validate Assessment'));
  expect(button('Send Assessment').disabled).toBe(false);
  await click(button('Coding Questions (2)'));
  await click(button('Edit Question', $('#pv-q-40')));
  expect($('[data-testid="config-panel"]').textContent).toContain('Coding Configuration for 40');
  await click(button('make dirty'));
  expect($('.pv-unsaved')).toBeTruthy();
  expect(button('Send Assessment').disabled).toBe(true);
  window.confirm.mockReturnValueOnce(false);
  await click(button('Close Preview'));
  expect(window.confirm).toHaveBeenLastCalledWith(expect.stringContaining('unsaved changes'));
  expect(props.onClose).not.toHaveBeenCalled();
});

test('editing an MCQ validates one correct answer, saves explanation and difficulty, and requires re-validation', async () => {
  apiPut.mockImplementation((path, body) => Promise.resolve({ ok: true, data: { question: { ...mcq(1), ...body, id: 1 } } }));
  await mount();
  await click(button('Validate Assessment'));
  expect(button('Send Assessment').disabled).toBe(false);
  const card = $('#pv-q-1');
  await click(button('Edit', card));
  const edit = $('#pv-q-1');
  type(edit.querySelector('[aria-label="Option C"]'), 'Option D'); // now duplicates D
  await click(button('Save Changes', edit));
  expect(edit.querySelector('[role="alert"]').textContent).toContain('different');
  expect(apiPut).not.toHaveBeenCalled();
  type(edit.querySelector('[aria-label="Option C"]'), 'Option C2');
  type(edit.querySelector('#pv-expl-1'), 'Edited explanation.');
  type(edit.querySelector('select'), 'Hard');
  await click(button('Save Changes', edit));
  expect(apiPut).toHaveBeenCalledWith('/api/assessment/question/1', expect.objectContaining({
    correct_answer: 'Option C2', explanation: 'Edited explanation.', difficulty: 'Hard',
    options: ['Option A', 'Option B', 'Option C2', 'Option D'] }));
  expect($('#pv-q-1').textContent).toContain('Edited explanation.');
  expect(current.find(q => q.id === 1).correct_answer).toBe('Option C2');
  expect(button('Send Assessment').disabled).toBe(true); // the validated version changed
});

test('Regenerate replaces one question in place', async () => {
  apiPost.mockResolvedValue({ ok: true, data: { question: mcq(2, { question_text: 'A brand new question?' }) } });
  await mount();
  await click(button('Regenerate', $('#pv-q-2')));
  expect(apiPost).toHaveBeenCalledWith('/api/assessment/question/2/regenerate', {});
  expect($('#pv-q-2').textContent).toContain('A brand new question?');
  expect($('#pv-q-2').textContent).toContain('Question 2 of 30');
});

test('validation errors are listed and link to the question', async () => {
  apiGet.mockResolvedValue({ ready: false, fingerprint: 'fp', problems: ['Set a time limit between 5 and 480 minutes.'],
    questions: [{ question_id: 40, number: 31, question_type: 'coding', problems: ['Add at least one hidden test case.'] }] });
  await mount();
  await click(button('Validate Assessment'));
  const panel = $('.pv-invalid');
  expect(panel.textContent).toContain('Set a time limit');
  expect(panel.textContent).toContain('Add at least one hidden test case.');
  expect(button('Send Assessment').disabled).toBe(true);
  await click(button('Question 31', panel));
  expect($('.pv-tabs .active').textContent).toBe('Coding Questions (2)');
  expect($('#pv-q-40')).toBeTruthy();
});

test('an invalid candidate email fails validation', async () => {
  await mount({ assessment: { ...ASSESSMENT, candidate_email: 'not-an-email' } });
  await click(button('Validate Assessment'));
  expect($('.pv-invalid').textContent).toContain('valid candidate email');
  expect(button('Send Assessment').disabled).toBe(true);
});

test('sending needs validation and an explicit confirmation, then publishes the reviewed version once', async () => {
  apiPost.mockResolvedValueOnce({ ok: false, data: { error: 'SMTP authentication failed.' } })
    .mockResolvedValueOnce({ ok: true, data: { status: 'SENT', published_version: 1, assessment_link: 'https://hr.example.com/assessment/tok',
      sent_at: '2026-10-16T10:00:00Z', email: { to_email: 'asha@example.com' } } });
  await mount({ questions: VERIFIED });
  expect(button('Send Assessment').disabled).toBe(true);
  await click(button('Validate Assessment'));
  expect($('.pv-valid').textContent).toContain('Ready to send');
  await click(button('Send Assessment'));
  const dialog = $('.pv-confirm');
  expect(dialog.textContent).toContain('Senior Full Stack Engineer · Uber');
  expect(dialog.textContent).toContain('32 (30 MCQ + 2 Coding)');
  expect(dialog.textContent).toContain('60');
  expect($('#pv-confirm-email').value).toBe('asha@example.com');
  expect(apiPost).not.toHaveBeenCalled(); // nothing is sent before confirming
  await click(button('Confirm & Send', dialog));
  expect($('.pv-confirm [role="alert"]').textContent).toContain('SMTP authentication failed.');
  await click(button('Confirm & Send', $('.pv-confirm')));
  const [first, second] = apiPost.mock.calls;
  expect(first[0]).toBe('/api/assessment/1/send');
  expect(first[1]).toEqual(expect.objectContaining({ confirm: true, reviewed_fingerprint: 'fp-1', to_email: 'asha@example.com' }));
  expect(second[1].request_id).toBe(first[1].request_id); // the retry cannot email twice
  expect($('.pv-success').textContent).toContain('Assessment sent to asha@example.com.');
  expect($('.pv-success').textContent).toContain('Version 1 published');
  expect($('.pv-success input').value).toBe('https://hr.example.com/assessment/tok');
  expect(props.onSent).toHaveBeenCalledWith(expect.objectContaining({ published_version: 1 }));
  expect(button('Send Assessment')).toBeUndefined();
});

test('cancelling the confirmation sends nothing', async () => {
  await mount({ questions: VERIFIED });
  await click(button('Validate Assessment'));
  await click(button('Send Assessment'));
  await click(button('Cancel', $('.pv-confirm')));
  expect($('.pv-confirm')).toBeNull();
  expect(apiPost).not.toHaveBeenCalled();
});

test('Save as Draft saves open edits first and never sends', async () => {
  apiPut.mockImplementation((path, body) => Promise.resolve({ ok: true, data: { question: { ...mcq(3), ...body, id: 3 } } }));
  await mount();
  await click(button('Edit', $('#pv-q-3')));
  type($('#pv-text-3'), 'Reworded question three?');
  await click(button('Save as Draft'));
  expect(apiPut).toHaveBeenCalledWith('/api/assessment/question/3', expect.objectContaining({ question_text: 'Reworded question three?' }));
  expect(props.onSaveDraft).toHaveBeenCalled();
  expect($('.pv-notice').textContent).toContain('Nothing has been sent');
  expect(apiPost).not.toHaveBeenCalled();
});

test('a sent assessment is read-only in the preview', async () => {
  await mount({ assessment: { ...ASSESSMENT, status: 'SENT' } });
  expect($('.pv-status').textContent).toBe('Sent — awaiting candidate');
  expect(button('Send Assessment')).toBeUndefined();
  expect(button('Edit', $('#pv-q-1'))).toBeUndefined();
  expect(button('Regenerate')).toBeUndefined();
});
