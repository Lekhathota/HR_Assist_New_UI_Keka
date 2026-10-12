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
const navItems = () => container.querySelectorAll('.ca-nav-item');
const tab = name => [...container.querySelectorAll('.ca-tab')].find(el => el.textContent.startsWith(name));
async function renderPayload(data, start = true) {
  publicApiGet.mockResolvedValue(data);
  await act(async () => root.render(
    <MemoryRouter initialEntries={['/assessment/test-token']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes><Route path="/assessment/:token" element={<CandidateAssessment />} /></Routes>
    </MemoryRouter>,
  ));
  if (start) {
    click($('.ca-terms-consent input'));
    await act(async () => $('.ca-exam-rules .ca-btn').click());
  }
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
  sessionStorage.clear();
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: null });
  Object.defineProperty(document.documentElement, 'requestFullscreen', { configurable: true, value: jest.fn(async () => {
    Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: document.documentElement });
    document.dispatchEvent(new Event('fullscreenchange'));
  }) });
  Object.defineProperty(document, 'exitFullscreen', { configurable: true, value: jest.fn(async () => {
    Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: null });
    document.dispatchEvent(new Event('fullscreenchange'));
  }) });
  let violations = 0;
  publicApiPost.mockImplementation(path => {
    if (path === '/api/assessment/proctoring-event') {
      violations += 1;
      return Promise.resolve({ violation_count: violations, terminated: violations >= 2, status: violations >= 2 ? 'TERMINATED' : 'IN_PROGRESS' });
    }
    return Promise.resolve(path === '/api/assessment/submit' ? { result: { status: 'COMPLETED' } } : { success: true });
  });
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
  expect(navItems()).toHaveLength(total - 2);
  expect(navItems()[0].textContent).toContain('Question 1');
  expect(tab('Questions').getAttribute('aria-selected')).toBe('true');
  expect(tab('Coding').textContent).toContain('0/2');
  expect($('.ca-logo').getAttribute('src')).toBe('/ShimentoX-Logo-Dark.png');
  expect($('.ca-assessment-title').textContent).toBe('Title received from API');
  expect($('.ca-candidate').textContent).toBe('Candidate received from API');
  click(tab('Coding'));
  expect(navItems()).toHaveLength(2);
  expect(navItems()[0].textContent).toContain(`Question ${total - 1}`);
  expect($('#ca-question-position').textContent).toBe(`Question ${total - 1} of ${total}`);
  expect($('.ca-code-input').value).toBe('API supplied starter template\n');
  expect(answerCount()).toBe(`0 / ${total} answered`);
  expect(publicApiPost).toHaveBeenCalledTimes(1);
  expect(publicApiPost).toHaveBeenCalledWith('/api/assessment/start', { token: 'test-token', accepted_terms: true });
});

test('actual responses update count, indicators and progress and survive navigation', async () => {
  await renderPayload(makePayload(20));
  for (let index = 0; index < 3; index += 1) {
    click(navItems()[index]);
    click($('.ca-option input'));
  }
  expect(answerCount()).toBe('3 / 20 answered');
  expect(container.querySelectorAll('.ca-nav-item.answered')).toHaveLength(3);
  expect($('.ca-progress-track > span').style.width).toBe('15%');
  expect($('.ca-progress-ring').style.getPropertyValue('--ca-progress')).toBe('15%');
  click(navItems()[0]);
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
  click(tab('Coding'));
  click(navItems()[0]);
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
  click(tab('Coding'));
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
  click(tab('Coding'));
  click(navItems()[1]);
  await typeSolution('SELECT value FROM actual_response;');
  await act(async () => $('.ca-question-footer .ca-btn-primary').click());
  await act(async () => [...container.querySelectorAll('[role="alertdialog"] button')].find(button => button.textContent === 'Confirm submission').click());
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

const events = () => publicApiPost.mock.calls.filter(([path]) => path === '/api/assessment/proctoring-event');
const setVisibility = value => {
  Object.defineProperty(document, 'visibilityState', { configurable: true, value });
  document.dispatchEvent(new Event('visibilitychange'));
};

test('rules gate fullscreen and the timer before the candidate starts', async () => {
  await renderPayload(makePayload(14), false);
  expect($('.ca-welcome-logo').getAttribute('src')).toBe('/ShimentoX-Logo-Dark.png');
  expect($('.ca-welcome-heading h1').textContent).toBe('Welcome, Candidate received from API!');
  expect(container.textContent).toContain('Terms and conditions');
  expect($('.ca-exam-rules .ca-btn').disabled).toBe(true);
  click($('.ca-exam-rules .ca-btn'));
  expect(document.documentElement.requestFullscreen).not.toHaveBeenCalled();
  expect(container.textContent).toContain('two violations end your attempt');
  expect($('.ca-question-card')).toBeNull();
  await act(async () => jest.advanceTimersByTime(3000));
  expect(publicApiPost).not.toHaveBeenCalled();
  click($('.ca-terms-consent input'));
  expect($('.ca-exam-rules .ca-btn').disabled).toBe(false);
  await act(async () => $('.ca-exam-rules .ca-btn').click());
  expect(document.documentElement.requestFullscreen).toHaveBeenCalledTimes(1);
  expect($('.ca-timer span').textContent).toBe('1:00:03');
});

test('fullscreen denial keeps the candidate outside the exam without a violation', async () => {
  document.documentElement.requestFullscreen.mockRejectedValue(new Error('Fullscreen was denied'));
  await renderPayload(makePayload(14));
  expect(container.textContent).toContain('Fullscreen was denied');
  expect($('.ca-question-card')).toBeNull();
  expect(publicApiPost).not.toHaveBeenCalled();
});

test('one departure produces one warning even when blur, hidden and fullscreen exit all fire', async () => {
  await renderPayload(makePayload(14));
  await act(async () => {
    window.dispatchEvent(new Event('blur'));
    setVisibility('hidden');
    await document.exitFullscreen();
  });
  expect(events()).toHaveLength(1);
  expect(container.textContent).toContain('Your exam will be ended if you do this again');
  expect($('.ca-proctoring-status').textContent).toContain('1 / 2');
  expect($('.ca-layout').parentElement.hasAttribute('inert')).toBe(true);
  await act(async () => {
    setVisibility('visible');
    window.dispatchEvent(new Event('focus'));
    jest.advanceTimersByTime(300);
  });
  await act(async () => $('[role="alertdialog"] button').click());
  expect($('[role="alertdialog"]')).toBeNull();
  await act(async () => setVisibility('hidden'));
  expect(events()).toHaveLength(2);
  expect(container.textContent).toContain('Assessment Terminated');
  expect($('.ca-question-card')).toBeNull();
  expect(publicApiPost.mock.calls.some(([path]) => path === '/api/assessment/submit')).toBe(false);
});

test('browser back is restricted while question navigation remains available', async () => {
  await renderPayload(makePayload(14));
  click(container.querySelectorAll('.ca-step-actions button')[1]);
  click(container.querySelectorAll('.ca-step-actions button')[0]);
  expect(events()).toHaveLength(0);
  const url = window.location.href;
  await act(async () => window.dispatchEvent(new PopStateEvent('popstate')));
  expect(window.location.href).toBe(url);
  expect(events()[0][1].reason).toBe('back_navigation');
  expect($('[role="alertdialog"]')).not.toBeNull();
});

test('reload shortcuts and unload warn, while ordinary keyboard tab remains usable', async () => {
  await renderPayload(makePayload(14));
  const tabKey = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
  await act(async () => window.dispatchEvent(tabKey));
  expect(tabKey.defaultPrevented).toBe(false);
  expect(events()).toHaveLength(0);
  const reload = new KeyboardEvent('keydown', { key: 'r', ctrlKey: true, bubbles: true, cancelable: true });
  await act(async () => {
    window.dispatchEvent(reload);
    window.dispatchEvent(new Event('beforeunload', { cancelable: true }));
  });
  expect(reload.defaultPrevented).toBe(true);
  expect(events()).toHaveLength(1);
  expect(events()[0][1].reason).toBe('browser_shortcut');
  expect(events()[0][2]).toEqual({ keepalive: true });
});

test('server warning counts survive a fresh load and the next departure terminates', async () => {
  const data = makePayload(14);
  data.assessment.proctoring_violation_count = 1;
  data.assessment.started_at = '2026-01-01T00:00:00Z';
  publicApiPost.mockImplementation(path => Promise.resolve(path === '/api/assessment/proctoring-event'
    ? { violation_count: 2, terminated: true, status: 'TERMINATED' } : { success: true }));
  await renderPayload(data, false);
  expect(container.textContent).toContain('Warning already recorded: 1 / 2');
  click($('.ca-terms-consent input'));
  await act(async () => $('.ca-exam-rules .ca-btn').click());
  await act(async () => window.dispatchEvent(new Event('blur')));
  expect(container.textContent).toContain('Assessment Terminated');
});

test('connection failure locks continuation and retries the same event without resetting warnings', async () => {
  await renderPayload(makePayload(14));
  publicApiPost.mockRejectedValue(new Error('Offline'));
  await act(async () => window.dispatchEvent(new Event('blur')));
  expect(container.textContent).toContain('Check your connection');
  const firstEvent = events()[0][1];
  publicApiPost.mockResolvedValue({ violation_count: 1, terminated: false });
  await act(async () => $('[role="alertdialog"] button').click());
  expect(events()).toHaveLength(2);
  expect(events()[1][1]).toEqual(firstEvent);
  expect($('[role="alertdialog"]')).toBeNull();
  expect($('.ca-proctoring-status').textContent).toContain('1 / 2');
});

test('completed submissions stop monitoring and release fullscreen without recording a violation', async () => {
  await renderPayload(makePayload(14));
  await act(async () => $('.ca-submit-link').click());
  expect(events()).toHaveLength(0);
  await act(async () => [...container.querySelectorAll('[role="alertdialog"] button')].find(button => button.textContent === 'Confirm submission').click());
  await act(async () => window.dispatchEvent(new Event('blur')));
  expect(events()).toHaveLength(0);
  expect(container.textContent).toContain('Assessment Submitted');
  expect(document.exitFullscreen).toHaveBeenCalled();
});
