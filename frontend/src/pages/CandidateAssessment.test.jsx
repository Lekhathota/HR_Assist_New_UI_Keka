import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import CandidateAssessment from './CandidateAssessment.jsx';
import { publicApiGet, publicApiPost } from '../api.js';

jest.mock('../api.js', () => ({ publicApiGet: jest.fn(), publicApiPost: jest.fn() }));

const makePayload = (total, saved_answers = []) => ({
  assessment: { title: 'Title received from API', candidate_name: 'Candidate received from API', remaining_seconds: 3603 },
  questions: Array.from({ length: total }, (_, index) => ({
    id: index + 101, sort_order: index, question_type: index === total - 2 ? 'coding' : index === total - 1 ? 'sql' : 'mcq',
    skill_tag: `Skill received ${index + 1}`, question_text: `Question content received ${index + 1}`,
    options: ['First API option', 'Second API option'],
    starter_code: index === total - 2 ? 'API supplied starter template\n' : '',
  })),
  saved_answers,
});
let root, container;
const $ = selector => container.querySelector(selector);
const click = element => act(() => element.click());
const answerCount = () => $('.ca-answered-count').textContent;
async function renderPayload(data) {
  publicApiGet.mockResolvedValue(data);
  await act(async () => root.render(
    <MemoryRouter initialEntries={['/assessment/test-token']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes><Route path="/assessment/:token" element={<CandidateAssessment />} /></Routes>
    </MemoryRouter>,
  ));
}
async function typeSolution(value) {
  await act(async () => {
    const editor = $('.ca-code-input');
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(editor, value);
    editor.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  jest.useFakeTimers();
  publicApiPost.mockImplementation(path => Promise.resolve(path === '/api/assessment/submit' ? { result: { status: 'COMPLETED' } } : { success: true }));
  jest.spyOn(window, 'confirm').mockReturnValue(true);
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount()); container.remove(); jest.clearAllTimers(); jest.useRealTimers(); jest.restoreAllMocks(); jest.clearAllMocks();
});

test.each([14, 20])('new %i-question assessment starts at zero despite starter code', async total => {
  await renderPayload(makePayload(total));
  expect(answerCount()).toBe(`0 / ${total} answered`);
  expect($('.ca-progress-track').getAttribute('aria-valuenow')).toBe('0');
  expect($('.ca-progress-track').getAttribute('aria-valuemax')).toBe(String(total));
  expect($('.ca-progress-track > span').style.width).toBe('0%');
  expect(container.querySelectorAll('.ca-nav-item')).toHaveLength(total);
  expect($('.ca-logo').getAttribute('src')).toBe('/ShimentoX-Logo-Dark.png');
  expect($('.ca-assessment-title').textContent).toBe('Title received from API');
  expect($('.ca-candidate').textContent).toBe('Candidate received from API');
  click(container.querySelectorAll('.ca-nav-item')[total - 2]);
  expect($('.ca-code-input').value).toBe('API supplied starter template\n');
  expect(answerCount()).toBe(`0 / ${total} answered`);
  expect(publicApiPost).not.toHaveBeenCalled();
});

test('actual responses update count, indicators and progress and survive navigation', async () => {
  await renderPayload(makePayload(20));
  for (let index = 0; index < 3; index += 1) {
    click(container.querySelectorAll('.ca-nav-item')[index]);
    click($('.ca-option input'));
  }
  expect(answerCount()).toBe('3 / 20 answered');
  expect(container.querySelectorAll('.ca-nav-item.answered')).toHaveLength(3);
  expect($('.ca-progress-track > span').style.width).toBe('15%');
  expect($('.ca-progress-ring').style.getPropertyValue('--ca-progress')).toBe('15%');
  click(container.querySelectorAll('.ca-nav-item')[0]);
  expect($('.ca-option input').checked).toBe(true);
  await act(async () => jest.advanceTimersByTime(600));
  expect(publicApiPost).toHaveBeenCalledWith('/api/assessment/save-answer', { token: 'test-token', question_id: 101, answer: 'First API option' });
});

test('restores only actual saved answers and ignores answers for absent questions', async () => {
  await renderPayload(makePayload(20, [
    { question_id: 101, answer: 'Second API option' }, { question_id: 102, answer: 'First API option' },
    { question_id: 119, answer: 'Actual saved solution' }, { question_id: 9999, answer: 'Outside this exam' },
    { question_id: 103, answer: '   ' },
  ]));
  expect(answerCount()).toBe('3 / 20 answered');
  expect(container.querySelectorAll('.ca-option input')[1].checked).toBe(true);
  click(container.querySelectorAll('.ca-nav-item')[18]);
  expect($('.ca-code-input').value).toBe('Actual saved solution');
  await typeSolution('');
  expect($('.ca-code-input').value).toBe('');
  expect(answerCount()).toBe('2 / 20 answered');
});

test('question position, type, skill and editor content come from the active question', async () => {
  const payload = makePayload(14);
  payload.questions[12].language = 'Language received from API';
  await renderPayload(payload);
  expect($('.ca-step-actions button').disabled).toBe(true);
  expect($('.ca-question-footer .ca-btn-secondary').disabled).toBe(true);
  click(container.querySelectorAll('.ca-nav-item')[12]);
  expect($('#ca-question-position').textContent).toBe('Question 13 of 14');
  expect($('.ca-question-badge').textContent).toBe('Coding');
  expect($('.ca-skill-tag').textContent).toBe('Skill received 13');
  expect($('.ca-question-text').textContent).toBe('Question content received 13');
  expect($('.ca-editor-language').textContent).toBe('Language received from API');
  await typeSolution('Actual first line\nActual second line\nActual third line');
  expect(answerCount()).toBe('1 / 14 answered');
  expect(container.querySelectorAll('.ca-editor-lines span')).toHaveLength(3);
  click($('.ca-expand-editor'));
  expect($('.ca-code-block').classList.contains('ca-editor-expanded')).toBe(true);
  click(container.querySelectorAll('.ca-step-actions button')[1]);
  expect($('#ca-question-position').textContent).toBe('Question 14 of 14');
  expect($('.ca-question-badge').textContent).toBe('SQL');
  expect(container.querySelectorAll('.ca-step-actions button')[1].disabled).toBe(true);
  expect($('.ca-question-footer .ca-btn-primary').textContent).toBe('Submit Assessment');
  click($('.ca-step-actions button'));
  expect($('.ca-code-input').value).toBe('Actual first line\nActual second line\nActual third line');
});

test('timer uses the API duration and existing countdown state', async () => {
  await renderPayload(makePayload(14));
  expect($('.ca-timer span').textContent).toBe('1:00:03');
  await act(async () => jest.advanceTimersByTime(1000));
  expect($('.ca-timer span').textContent).toBe('1:00:02');
});

test('submit uses existing API logic and sends actual responses only', async () => {
  await renderPayload(makePayload(14));
  click($('.ca-option input'));
  click(container.querySelectorAll('.ca-nav-item')[13]);
  await typeSolution('SELECT value FROM actual_response;');
  await act(async () => $('.ca-question-footer .ca-btn-primary').click());
  const call = publicApiPost.mock.calls.find(([path]) => path === '/api/assessment/submit');
  expect(call[1].token).toBe('test-token');
  expect(call[1].answers).toHaveLength(14);
  expect(call[1].answers[0]).toEqual({ question_id: 101, answer: 'First API option' });
  expect(call[1].answers[12]).toEqual({ question_id: 113, answer: '' });
  expect(call[1].answers[13]).toEqual({ question_id: 114, answer: 'SELECT value FROM actual_response;' });
  expect(container.textContent).toContain('Assessment Submitted');
});

test('expiry still automatically submits current responses', async () => {
  const payload = makePayload(14); payload.assessment.remaining_seconds = 1;
  await renderPayload(payload);
  await act(async () => jest.advanceTimersByTime(1000));
  expect(window.confirm).not.toHaveBeenCalled();
  expect(publicApiPost.mock.calls.some(([path]) => path === '/api/assessment/submit')).toBe(true);
  expect(container.textContent).toContain('submitted automatically');
});
