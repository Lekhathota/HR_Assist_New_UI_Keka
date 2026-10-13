import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { CandidateAnswer } from './AssessmentBuilder.jsx';

jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiPost: jest.fn(), apiPut: jest.fn(), apiDelete: jest.fn(), apiGetBlob: jest.fn() }));

let root, container;
const render = async props => { await act(async () => root.render(<CandidateAnswer {...props} />)); return container; };
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

const mcq = { id: 1, question_type: 'mcq', options: ['GET', 'POST'], correct_answer: 'GET' };

test('a scored choice answer shows the selection, verdict and points', async () => {
  const el = await render({ question: mcq, answer: { answer: 'GET' }, result: { is_correct: true, points_earned: 10, points_possible: 10 } });
  expect(el.textContent).toContain("Candidate's answer");
  expect(el.textContent).toContain('GET');
  expect(el.textContent).toContain('Correct');
  expect(el.textContent).toContain('10/10 pts');
});

test('an unscored (terminated) wrong choice is checked against the key and shows the right answer', async () => {
  const el = await render({ question: mcq, answer: { answer: 'POST' } });
  expect(el.querySelector('.ab-answer-verdict').textContent).toBe('Incorrect');
  expect(el.textContent).toContain('Correct answer: GET');
});

test('coding answers are shown as code with their language', async () => {
  const el = await render({ question: { id: 2, question_type: 'coding' }, answer: { answer: 'def add(a, b):\n    return a + b', language: 'python' } });
  expect(el.querySelector('pre').textContent).toBe('def add(a, b):\n    return a + b');
  expect(el.textContent).toContain('python');
  expect(el.textContent).toContain('Not graded');
});

test('an unanswered question says so', async () => {
  const el = await render({ question: { id: 3, question_type: 'short_answer' }, answer: undefined });
  expect(el.textContent).toContain('Not answered');
  expect(el.textContent).toContain('did not answer');
});
