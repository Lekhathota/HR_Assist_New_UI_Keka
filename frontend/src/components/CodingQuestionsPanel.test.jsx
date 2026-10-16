import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import CodingQuestionsPanel, { draftProblem } from './CodingQuestionsPanel.jsx';
import AssessmentBuilder, { mcqProblem } from '../pages/AssessmentBuilder.jsx';
import { apiDelete, apiGet, apiPost, apiPut } from '../api.js';

jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiPost: jest.fn(), apiPut: jest.fn(), apiDelete: jest.fn() }));
jest.mock('./Layout.jsx', () => ({ children }) => <main>{children}</main>);
jest.mock('./ReferenceSolutionPanel.jsx', () => () => null);
jest.mock('./ProctoringEvidence.jsx', () => () => null);
jest.mock('../utils/assessmentPdf.js', () => ({ downloadAssessmentPdf: jest.fn() }));

const LANGUAGES = [{ key: 'python', label: 'Python 3' }, { key: 'java', label: 'Java' }, { key: 'cpp', label: 'C++' }];
const SPEC_KEYS = ['prompt', 'language', 'difficulty', 'points', 'topic', 'time_limit_minutes'];
// Existing questions on the assessment (like Q13/Q14 in the screenshot) that must never change.
const BASE_QUESTIONS = [
  { id: 13, question_type: 'mcq', question_text: 'Existing MCQ about REST retries', options: ['A1', 'B1', 'C1', 'D1'], correct_answer: 'B1', explanation: 'B1 is idempotent.', points: 5, sort_order: 0 },
  { id: 14, question_type: 'sql', question_text: 'Existing SQL on microservice_errors', correct_answer: 'SELECT 1', points: 10, sort_order: 1 },
];

function generatedDraft(spec) {
  return {
    question_text: `Generated for: ${spec.prompt}. Read the input from stdin, handle the edge cases and print the result.`,
    input_format: 'n then n integers', output_format: 'one integer', constraints: '1 <= n <= 10^5',
    explanation: 'Single pass.', correct_answer: 'print(1)', skill_tag: spec.topic || 'Coding',
    time_limit_minutes: spec.time_limit_minutes ?? null, tests_verified: true, generation_prompt: spec.prompt,
    test_cases: [
      { id: 't1', input: '1\n', expected_output: '1\n', hidden: false },
      { id: 't2', input: '2\n', expected_output: '2\n', hidden: false },
      { id: 't3', input: '3\n', expected_output: '3\n', hidden: true },
      { id: 't4', input: '4\n', expected_output: '4\n', hidden: true },
      { id: 't5', input: '5\n', expected_output: '5\n', hidden: true },
    ],
  };
}

// In-memory stand-in for /api/assessment/1 and /api/assessment/1/coding/* (mirrors coding_question_service).
function makeServer({ max = 20, status = 'DRAFT' } = {}) {
  const state = { specs: [], clientPrompt: 'Acme default rules', clientDefault: 'Acme default rules', baseCoding: 2, nextId: 1,
    nextQ: 500, failNext: null, failSave: null, saved: [], status, ready: true, approved: false, result: null, attempts: [] };
  const check = () => ({
    ready: state.ready, problems: state.ready ? [] : ['1 generated coding question(s) are still awaiting review: save or cancel them.'],
    questions: state.ready ? [] : [{ question_id: 14, number: 2, question_type: 'sql', problems: ['Add at least one hidden test case.'] }],
    mcq_questions: 1, coding_questions: state.saved.length, approval: { current: state.approved, by: state.approved ? 'rec' : undefined },
    fingerprint: 'fp-1',
  });
  const editable = () => state.status === 'DRAFT';
  const view = s => ({ ...s, status: s.draft ? 'review' : s.status });
  const config = () => ({
    editable: editable(), status: state.status, jd: { id: 20, title: 'Backend Engineer' }, client: { id: 5, name: 'Acme' },
    client_prompt: state.clientPrompt, client_default_prompt: state.clientDefault,
    specs: state.specs.map(view),
    coding_question_count: state.baseCoding + state.specs.filter(s => s.question).length,
    limits: { max_coding_questions: max, max_questions: 60, max_prompt_chars: 4000, max_client_prompt_chars: 4000, max_topic_chars: 200, max_time_limit_minutes: 240 },
    languages: LANGUAGES, difficulties: ['Easy', 'Medium', 'Hard'],
  });
  const ok = data => Promise.resolve({ ok: true, status: 200, data: { success: true, ...data } });
  const fail = (code, error) => Promise.resolve({ ok: false, status: code, data: { error } });
  const spec = id => state.specs.find(s => s.id === id);
  const specFields = body => Object.fromEntries(Object.entries(body || {}).filter(([key]) => SPEC_KEYS.includes(key)));
  apiGet.mockImplementation(path => {
    if (path === '/api/assessment/1/coding') return Promise.resolve(config());
    if (path === '/api/assessment/1') return Promise.resolve({
      assessment: { id: 1, status: state.status, title: 'Exam', candidate_id: 9, jd_id: 20, scoring_policy: state.policy || null,
        candidate_name: 'Asha Rao', candidate_email: 'c@example.com', job_role: 'Backend Engineer', time_limit_minutes: 90, passing_score: 70 },
      questions: [...BASE_QUESTIONS, ...state.saved], answers: [],
    });
    if (path === '/api/assessment/1/publish-check') return Promise.resolve(check());
    if (path === '/api/assessment/result/1') return Promise.resolve({ result: state.result });
    if (path === '/api/assessment/1/code-attempts') return Promise.resolve({ attempts: state.attempts });
    return Promise.resolve({});
  });
  apiPost.mockImplementation((path, body) => {
    if (path === '/api/assessment/1/coding/specs') {
      if (state.specs.length >= max) return fail(409, `An assessment can have at most ${max} custom coding questions.`);
      const created = { id: `s${state.nextId++}`, ...specFields(body), status: 'pending', last_error: '', question: null, draft: null };
      state.specs.push(created);
      return ok({ spec: view(created), config: config() });
    }
    let match = path.match(/^\/api\/assessment\/1\/coding\/specs\/(\w+)\/generate$/);
    if (match) {
      const target = spec(match[1]);
      Object.assign(target, specFields(body));
      if (state.failNext) {
        const message = state.failNext;
        state.failNext = null;
        Object.assign(target, { status: 'failed', last_error: message });
        return fail(502, message);
      }
      Object.assign(target, { last_error: '', draft: generatedDraft(target) });
      return ok({ spec: view(target), draft: target.draft, config: config() });
    }
    match = path.match(/^\/api\/assessment\/1\/coding\/specs\/(\w+)\/save$/);
    if (match) {
      const target = spec(match[1]);
      if (!target.draft) return fail(409, 'Generate the question and review it before saving.');
      if (state.failSave) {
        const message = state.failSave;
        state.failSave = null;
        return fail(400, message);
      }
      Object.assign(target, specFields(body));
      const question = { ...(target.question || { id: state.nextQ++, sort_order: 2 + state.saved.length }), ...target.draft, ...(body.question || {}),
        question_type: 'coding', source: 'custom_coding', points: target.points };
      Object.assign(target, { status: 'generated', draft: null, question });
      state.saved = state.saved.filter(q => q.id !== question.id).concat(question).sort((a, b) => a.sort_order - b.sort_order);
      return ok({ spec: view(target), question, config: config() });
    }
    if (path === '/api/assessment/question') return ok({ question: { ...body, id: 900, sort_order: 99 } });
    if (path === '/api/assessment/1/approve') {
      if (!state.ready) return fail(409, 'The assessment is not ready to approve.');
      state.approved = true;
      return ok(check());
    }
    if (path === '/api/assessment/1/return-to-draft') {
      state.status = 'DRAFT';
      return ok({});
    }
    if (path === '/api/assessment/1/send') {
      state.sendCalls = (state.sendCalls || 0) + 1;
      state.status = 'SENT';
      return ok({ status: 'SENT', published_version: 1, assessment_link: 'https://hr.example.com/assessment/tok', email: { to_email: body.to_email } });
    }
    if (path === '/api/assessment/1/generate-email') return ok({ to_email: 'c@example.com', subject: 'Test', body: 'Link', candidate_test_link: 'https://x/assessment/t' });
    return ok({});
  });
  apiPut.mockImplementation((path, body) => {
    if (path === '/api/assessment/1') {
      state.policy = body.scoring_policy;
      return ok({ assessment: { id: 1, status: state.status, scoring_policy: body.scoring_policy } });
    }
    if (path === '/api/assessment/1/coding/client-prompt') {
      state.clientPrompt = body.prompt;
      if (body.save_as_client_default) state.clientDefault = body.prompt;
      return ok(config());
    }
    const match = path.match(/^\/api\/assessment\/1\/coding\/specs\/(\w+)$/);
    if (match) {
      if (body.language === 'cobol') return fail(400, 'Unsupported language');
      Object.assign(spec(match[1]), body);
      return ok({ spec: view(spec(match[1])), config: config() });
    }
    return ok({});
  });
  apiDelete.mockImplementation(path => {
    const draft = path.match(/^\/api\/assessment\/1\/coding\/specs\/(\w+)\/draft$/);
    if (draft) {
      spec(draft[1]).draft = null;
      return ok(config());
    }
    const id = path.split('/').pop();
    const removed = spec(id);
    state.specs = state.specs.filter(s => s.id !== id);
    if (removed?.question) state.saved = state.saved.filter(q => q.id !== removed.question.id);
    return ok(config());
  });
  return state;
}

let root, container, server, onQuestionsChanged;
const $ = s => container.querySelector(s);
const $$ = s => [...container.querySelectorAll(s)];
const button = (text, scope = container) => [...scope.querySelectorAll('button')].find(b => b.textContent.trim().includes(text));
const heading = () => $('#ab-coding-title').textContent;
const calls = (mock, suffix) => mock.mock.calls.filter(([path]) => path.endsWith(suffix));

function type(el, value) {
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  act(() => {
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, String(value));
    el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
  });
}
async function click(el) { await act(async () => el.click()); }
async function renderPanel() {
  await act(async () => root.render(<CodingQuestionsPanel assessmentId="1" onQuestionsChanged={onQuestionsChanged} />));
}
async function mount(options) {
  server = makeServer(options);
  onQuestionsChanged = jest.fn();
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  await renderPanel();
}
async function remount() {
  act(() => root.unmount());
  root = createRoot(container);
  await renderPanel();
}
async function addAndGenerate(prompt, extra = {}) {
  await click(button('+ Add Coding Question'));
  const card = $$('.ab-coding-card').at(-1);
  type(card.querySelector('textarea'), prompt);
  if (extra.language) type(card.querySelector('select[id^="ab-coding-lang"]'), extra.language);
  if (extra.difficulty) type(card.querySelector('select[id^="ab-coding-diff"]'), extra.difficulty);
  if (extra.topic) type(card.querySelector('input[id^="ab-coding-topic"]'), extra.topic);
  if (extra.time) type(card.querySelector('input[id^="ab-coding-time"]'), extra.time);
  await click(button('Generate Question', card));
  return card;
}
async function addGenerateAndSave(prompt, extra) {
  const card = await addAndGenerate(prompt, extra);
  await click(button('Save Question', card));
  return card;
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  jest.spyOn(window, 'confirm').mockReturnValue(true);
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.restoreAllMocks(); jest.clearAllMocks(); });

describe('Coding Questions panel', () => {
  test.each([1, 2, 5, 10])('adds, generates, reviews and saves %i coding questions, each from its own prompt', async (count) => {
    await mount();
    expect(heading()).toContain('Coding Questions (2)');
    for (let i = 0; i < count; i += 1) await addGenerateAndSave(`Client requirement number ${i}`);
    expect($$('.ab-coding-card')).toHaveLength(count);
    expect(heading()).toContain(`Coding Questions (${2 + count})`);
    expect(calls(apiPost, '/generate').map(([, body]) => body.prompt)).toEqual(Array.from({ length: count }, (_, i) => `Client requirement number ${i}`));
    expect(calls(apiPost, '/save')).toHaveLength(count);
    expect(onQuestionsChanged).toHaveBeenCalledTimes(count);
    expect(server.saved).toHaveLength(count);
    expect(container.textContent).toContain(`${count} saved`);
  });

  test('generating shows an editable review and nothing is added until Save Question', async () => {
    await mount();
    const card = await addAndGenerate('Merge overlapping intervals');
    expect(card.querySelector('.ab-coding-status').textContent).toBe('Review & save');
    expect(server.saved).toHaveLength(0);
    expect(onQuestionsChanged).not.toHaveBeenCalled();
    const review = card.querySelector('[aria-label="Review generated question"]');
    expect(review.querySelector('textarea[id^="ab-draft-question_text"]').value).toContain('Generated for: Merge overlapping intervals');
    for (const key of ['input_format', 'output_format', 'constraints', 'explanation', 'correct_answer']) {
      expect(review.querySelector(`textarea[id^="ab-draft-${key}"]`)).toBeTruthy();
    }
    expect(review.textContent).toContain('2 visible samples, 3 hidden');

    type(review.querySelector('textarea[id^="ab-draft-question_text"]'), 'Edited statement: merge intervals that overlap and print the merged list sorted by start time.');
    type(review.querySelector('textarea[id^="ab-draft-constraints"]'), '1 <= n <= 1000');
    await click(review.querySelector('[aria-label="Remove test 5"]'));
    await click(button('+ Add test case', review));
    type(review.querySelector('[aria-label="Test 5 input"]'), '9\n');
    type(review.querySelector('[aria-label="Test 5 expected output"]'), '9\n');
    await click(button('Save Question', card));

    const [, body] = calls(apiPost, '/save')[0];
    expect(body.question.question_text).toContain('Edited statement');
    expect(body.question.constraints).toBe('1 <= n <= 1000');
    expect(body.question.test_cases.map(t => t.input)).toEqual(['1\n', '2\n', '3\n', '4\n', '9\n']);
    expect(body.question.test_cases.at(-1).hidden).toBe(true);
    expect(server.saved[0].question_text).toContain('Edited statement');
    expect(onQuestionsChanged).toHaveBeenCalledWith(expect.objectContaining({ id: server.saved[0].id }));
    expect(card.querySelector('.ab-coding-status').textContent).toBe('Saved');
    expect(card.textContent).toContain('Saved to the assessment.');
  });

  test('prompt, topic, language, difficulty and time limit are sent with generation', async () => {
    await mount();
    await addAndGenerate('Rate limiter in Java', { language: 'java', difficulty: 'Hard', topic: 'Sliding window', time: 45 });
    const [, body] = calls(apiPost, '/generate')[0];
    expect(body).toEqual(expect.objectContaining({ prompt: 'Rate limiter in Java', language: 'java', difficulty: 'Hard', topic: 'Sliding window', time_limit_minutes: 45 }));
    expect($('.ab-coding-summary').textContent).toContain('Sliding window');
  });

  test('the review is validated before saving', async () => {
    await mount();
    const card = await addAndGenerate('Validate me');
    const review = card.querySelector('[aria-label="Review generated question"]');
    type(review.querySelector('textarea[id^="ab-draft-correct_answer"]'), '  ');
    await click(button('Save Question', card));
    expect($('[role="alert"]').textContent).toContain('reference solution');
    type(review.querySelector('textarea[id^="ab-draft-correct_answer"]'), 'print(1)');
    await click(review.querySelector('[aria-label="Remove test 5"]'));
    await click(button('Save Question', card));
    expect($('[role="alert"]').textContent).toContain('3 hidden tests');
    expect(calls(apiPost, '/save')).toHaveLength(0);
    expect(draftProblem({ question_text: 'too short', correct_answer: 'x', explanation: 'y' })).toContain('12 words');
  });

  test('a server validation error on save is shown and the draft is kept', async () => {
    await mount();
    const card = await addAndGenerate('Server says no');
    server.failSave = 'The reference solution does not pass the test cases: t3';
    await click(button('Save Question', card));
    expect($('[role="alert"]').textContent).toContain('does not pass the test cases');
    expect(card.querySelector('[aria-label="Review generated question"]')).toBeTruthy();
    expect(server.saved).toHaveLength(0);
    expect(onQuestionsChanged).not.toHaveBeenCalled();
  });

  test('Cancel on a new entry removes it; Cancel on a regenerated draft keeps the saved question', async () => {
    await mount();
    await addAndGenerate('Changed my mind');
    await click(button('Cancel', $('.ab-coding-card')));
    expect(apiDelete).toHaveBeenLastCalledWith('/api/assessment/1/coding/specs/s1');
    expect($$('.ab-coding-card')).toHaveLength(0);
    expect(server.saved).toHaveLength(0);

    const card = await addGenerateAndSave('Keep this one');
    const savedText = server.saved[0].question_text;
    await click(button('Regenerate', card));
    expect(window.confirm).toHaveBeenLastCalledWith(expect.stringContaining('review the new version'));
    expect(card.querySelector('[aria-label="Review generated question"]')).toBeTruthy();
    await click(button('Cancel', card));
    expect(apiDelete).toHaveBeenLastCalledWith('/api/assessment/1/coding/specs/s2/draft');
    expect($$('.ab-coding-card')).toHaveLength(1);
    expect(server.saved[0].question_text).toBe(savedText);
    expect(server.specs[0].draft).toBeNull();
  });

  test('bottom add action is present with zero, one, two, three and more entries', async () => {
    await mount();
    for (let count = 0; count <= 5; count += 1) {
      expect($$('.ab-coding-card')).toHaveLength(count);
      expect(heading()).toContain(`Coding Questions (${2 + count})`);
      expect($$('.ab-coding-footer button')).toHaveLength(1);
      expect($('.ab-coding-footer button').textContent).toBe('+ Add Coding Question');
      expect($('.ab-coding-footer button').disabled).toBe(false);
      expect($$('.ab-coding-head-actions button').some(b => b.textContent.includes('+ Add Coding Question'))).toBe(true);
      if (count < 5) {
        await click($('.ab-coding-footer button'));
        expect(document.activeElement).toBe($$('.ab-coding-card textarea').at(-1));
      }
    }
  });

  test('more than two questions can be edited, saved, regenerated, removed and restored', async () => {
    await mount();
    for (let i = 0; i < 4; i += 1) await addGenerateAndSave(`Requirement ${i}`);
    await click(button('Collapse all'));
    const third = $$('.ab-coding-card')[2];
    await click(third.querySelector('[aria-label="Edit coding question 3"]'));
    expect(document.activeElement).toBe(third.querySelector('textarea'));
    type(third.querySelector('textarea'), 'Updated third requirement');
    type(third.querySelector('select[id^="ab-coding-lang"]'), 'java');
    type(third.querySelector('select[id^="ab-coding-diff"]'), 'Hard');
    await click(button('Save changes', third));
    expect(apiPut).toHaveBeenCalledWith('/api/assessment/1/coding/specs/s3', {
      prompt: 'Updated third requirement', language: 'java', difficulty: 'Hard',
    });
    await click(button('Regenerate', third));
    await click(button('Save Question', third));
    expect(server.saved.find(q => q.id === server.specs[2].question.id).question_text).toContain('Updated third requirement');
    const fourth = $$('.ab-coding-card')[3];
    await click(fourth.querySelector('[aria-label="Edit coding question 4"]'));
    await click(button('Remove', fourth));
    expect(apiDelete).toHaveBeenCalledWith('/api/assessment/1/coding/specs/s4');
    await remount();
    expect($$('.ab-coding-card')).toHaveLength(3);
    expect(heading()).toContain('Coding Questions (5)');
    await click($$('.ab-coding-card')[2].querySelector('[aria-label="Edit coding question 3"]'));
    expect($$('.ab-coding-card')[2].querySelector('textarea').value).toBe('Updated third requirement');
    expect($$('.ab-coding-card')[2].querySelector('select[id^="ab-coding-lang"]').value).toBe('java');
    expect($$('.ab-coding-card')[2].querySelector('select[id^="ab-coding-diff"]').value).toBe('Hard');
    expect(container.textContent).not.toContain('Requirement 3');
  });

  test('pending question prompts are saved and restored before generation', async () => {
    await mount();
    for (let i = 0; i < 4; i += 1) {
      await click($('.ab-coding-footer button'));
      const card = $$('.ab-coding-card').at(-1);
      type(card.querySelector('textarea'), `Draft prompt ${i}`);
      await click(button('Save changes', card));
    }
    await remount();
    expect($$('.ab-coding-card')).toHaveLength(4);
    expect(heading()).toContain('Coding Questions (6)');
    for (let i = 0; i < 4; i += 1) expect($$('.ab-coding-card')[i].textContent).toContain(`Draft prompt ${i}`);
    expect(server.specs.every(spec => spec.status === 'pending')).toBe(true);
  });

  test('a generated draft awaiting review survives a reload', async () => {
    await mount();
    await addAndGenerate('Review me after lunch');
    await remount();
    const card = $('.ab-coding-card');
    expect(card.querySelector('.ab-coding-status').textContent).toBe('Review & save');
    expect(card.querySelector('textarea[id^="ab-draft-question_text"]').value).toContain('Review me after lunch');
    await click(button('Save Question', card));
    expect(server.saved).toHaveLength(1);
  });

  test('generation saves the current shared instructions before generating each individual question', async () => {
    await mount();
    type($('#ab-client-prompt'), 'Shared Java performance requirements');
    for (let i = 0; i < 4; i += 1) await addAndGenerate(`Individual prompt ${i}`);
    expect(apiPut).toHaveBeenCalledWith('/api/assessment/1/coding/client-prompt', {
      prompt: 'Shared Java performance requirements', save_as_client_default: false,
    });
    expect(apiPut.mock.invocationCallOrder[0]).toBeLessThan(apiPost.mock.invocationCallOrder[1]);
    expect(server.clientPrompt).toBe('Shared Java performance requirements');
    expect(server.specs.map(spec => spec.prompt)).toEqual(Array.from({ length: 4 }, (_, i) => `Individual prompt ${i}`));
    await remount();
    expect($('#ab-client-prompt').value).toBe('Shared Java performance requirements');
  });

  test('failed shared-instruction save prevents generation and keeps unsaved input', async () => {
    await mount();
    await click($('.ab-coding-footer button'));
    type($('#ab-client-prompt'), 'Unsaved shared instructions');
    type($('.ab-coding-card textarea'), 'Unsaved individual prompt');
    apiPut.mockResolvedValueOnce({ ok: false, data: { error: 'Could not save instructions' } });
    await click(button('Generate Question'));
    expect(calls(apiPost, '/generate')).toHaveLength(0);
    expect($('.ab-coding-card textarea').value).toBe('Unsaved individual prompt');
    expect($('#ab-client-prompt').value).toBe('Unsaved shared instructions');
    expect($('[role="alert"]').textContent).toContain('Could not save instructions');
  });

  test('an empty prompt is rejected before calling the API and Save is disabled until generated', async () => {
    await mount();
    await click(button('+ Add Coding Question'));
    expect(button('Save Question').disabled).toBe(true);
    await click(button('Generate Question'));
    expect($('[role="alert"]').textContent).toContain('requirements');
    expect(calls(apiPost, '/generate')).toHaveLength(0);
  });

  test('regenerating a draft with edits asks first', async () => {
    await mount();
    const card = await addAndGenerate('First version');
    type(card.querySelector('textarea[id^="ab-draft-explanation"]'), 'My edit');
    window.confirm.mockReturnValueOnce(false);
    await click(button('Regenerate', card));
    expect(window.confirm).toHaveBeenLastCalledWith(expect.stringContaining('edits to the generated draft'));
    expect(calls(apiPost, '/generate')).toHaveLength(1);
    await click(button('Regenerate', card));
    expect(calls(apiPost, '/generate')).toHaveLength(2);
    expect(card.querySelector('textarea[id^="ab-draft-explanation"]').value).toBe('Single pass.');
  });

  test('remove deletes the entry and its saved question', async () => {
    await mount();
    await addGenerateAndSave('Entry to delete');
    await click(button('Remove'));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('saved question is removed'));
    expect(apiDelete).toHaveBeenCalledWith('/api/assessment/1/coding/specs/s1');
    expect($$('.ab-coding-card')).toHaveLength(0);
    expect(heading()).toContain('Coding Questions (2)');
    expect(onQuestionsChanged).toHaveBeenCalledTimes(2);
  });

  test('a failed generation shows the error and keeps the prompt', async () => {
    await mount();
    await click(button('+ Add Coding Question'));
    type($('.ab-coding-card textarea'), 'Tricky requirement');
    server.failNext = 'The AI could not produce a valid coding question after three attempts.';
    await click(button('Generate Question'));
    expect($('[role="alert"]').textContent).toContain('three attempts');
    expect($('.ab-coding-card textarea').value).toBe('Tricky requirement');
    expect($('.ab-coding-status').textContent).toBe('Generation failed');
    expect(onQuestionsChanged).not.toHaveBeenCalled();
  });

  test('server validation errors are shown on the entry', async () => {
    await mount();
    await click(button('+ Add Coding Question'));
    apiPut.mockResolvedValueOnce({ ok: false, status: 400, data: { error: 'Unsupported language' } });
    type($('.ab-coding-card textarea'), 'x');
    await click(button('Save changes'));
    expect($('[role="alert"]').textContent).toContain('Unsupported language');
  });

  test('the configurable limit disables adding more; there is no fixed limit of two', async () => {
    await mount({ max: 3 });
    for (let i = 0; i < 3; i += 1) await addGenerateAndSave(`Question ${i}`);
    expect(button('+ Add Coding Question').disabled).toBe(true);
    expect(container.textContent).toContain('limit 3');
  });

  test('client instructions default from the client and can be saved as the client default', async () => {
    await mount();
    const textarea = $('#ab-client-prompt');
    expect(textarea.value).toBe('Acme default rules');
    expect(container.textContent).toContain('Client coding instructions · Acme');
    expect(button('Save instructions').disabled).toBe(true);
    type(textarea, 'Use Java 17 and O(n log n)');
    await click($('.ab-checkbox input'));
    await click(button('Save instructions'));
    expect(apiPut).toHaveBeenCalledWith('/api/assessment/1/coding/client-prompt', { prompt: 'Use Java 17 and O(n log n)', save_as_client_default: true });
    expect(server.clientDefault).toBe('Use Java 17 and O(n log n)');
    expect(container.textContent).toContain("set as Acme's default");
  });

  test('many entries stay manageable: cards collapse and a bottom add button appears', async () => {
    await mount();
    for (let i = 0; i < 5; i += 1) await click(button('+ Add Coding Question'));
    expect($$('.ab-coding-body')).toHaveLength(5);
    await click(button('Collapse all'));
    expect($$('.ab-coding-body')).toHaveLength(0);
    await click($$('.ab-coding-summary')[2]);
    expect($$('.ab-coding-body')).toHaveLength(1);
    expect($$('button').filter(b => b.textContent.includes('+ Add Coding Question'))).toHaveLength(2);
  });

  test('reloading restores saved entries', async () => {
    await mount();
    await addGenerateAndSave('Persisted prompt');
    await remount();
    expect(container.textContent).toContain('Persisted prompt');
    expect($('.ab-coding-status').textContent).toBe('Saved');
  });

  test('once the candidate starts, the button stays visible but questions are locked', async () => {
    await mount({ status: 'IN_PROGRESS' });
    expect(button('+ Add Coding Question').disabled).toBe(true);
    expect(container.textContent).toContain('locked because the candidate has started');
    expect($('#ab-client-prompt')).toBeNull();
  });
});

describe('Assessment Builder integration', () => {
  async function mountBuilder(options) {
    server = makeServer(options);
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    await act(async () => root.render(
      <MemoryRouter initialEntries={['/hiring-pipeline/assessment/1']}>
        <Routes><Route path="/hiring-pipeline/assessment/:assessmentId" element={<AssessmentBuilder />} /></Routes>
      </MemoryRouter>,
    ));
  }
  const questionCards = () => $$('.ab-question-card');

  test('the Add Coding Question panel sits after the last question card', async () => {
    await mountBuilder();
    const lastCard = questionCards().at(-1);
    const panel = $('.ab-coding-panel');
    expect(lastCard.compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(button('+ Add Coding Question', panel)).toBeTruthy();
  });

  test('saved coding questions get the next number and existing questions are kept as they were', async () => {
    await mountBuilder();
    const before = questionCards().map(c => c.textContent);
    await addGenerateAndSave('Builder-level requirement', { topic: 'Intervals', time: 30 });
    await addGenerateAndSave('Second builder requirement');
    await addGenerateAndSave('Third builder requirement');
    const cards = questionCards();
    expect(cards).toHaveLength(5);
    expect(cards.slice(0, 2).map(c => c.textContent)).toEqual(before);
    expect(cards.map(c => c.querySelector('.ab-q-num').textContent)).toEqual(['Q1', 'Q2', 'Q3', 'Q4', 'Q5']);
    expect(cards[2].textContent).toContain('Generated for: Builder-level requirement');
    expect(cards[2].textContent).toContain('Custom prompt');
    expect(cards[2].textContent).toContain('Recruiter prompt: Builder-level requirement');
    expect(cards[2].textContent).toContain('Constraints: 1 <= n <= 10^5');
    expect(cards[2].textContent).toContain('30 min');
    expect(cards[2].id).toMatch(/^ab-q-\d+$/);
    expect($('.ab-notice').textContent).toContain('saved as Q5');
  });

  test('a sent assessment is locked until it is returned to draft', async () => {
    await mountBuilder({ status: 'SENT' });
    expect(button('+ Add Coding Question').disabled).toBe(true);
    expect($('.ab-coding-locked').textContent).toContain('return to draft');
    expect($('.ab-add-bar')).toBeNull();
    expect(questionCards()[0].querySelector('[title="Edit"]')).toBeNull();
    window.confirm.mockReturnValueOnce(true);
    await click(button('Edit questions (return to draft)'));
    expect(apiPost).toHaveBeenCalledWith('/api/assessment/1/return-to-draft', {});
    expect(button('+ Add Coding Question').disabled).toBe(false);
    expect($('.ab-add-bar')).toBeTruthy();
    act(() => root.unmount()); container.remove();
    await mountBuilder({ status: 'IN_PROGRESS' });
    expect(button('+ Add Coding Question').disabled).toBe(true);
    expect(button('Edit questions (return to draft)')).toBeUndefined();
  });

  test('Send Assessment opens the preview; nothing is emailed until the recruiter confirms', async () => {
    await mountBuilder();
    await addGenerateAndSave('Builder-level requirement');
    await click(button('Send Assessment', $('.ab-topbar')));
    const dialog = $('.pv-dialog');
    expect(dialog).toBeTruthy();
    expect(apiGet).toHaveBeenCalledWith('/api/assessment/1/publish-check');  // validated on open
    expect(dialog.textContent).toContain('Coding Questions (2)');            // SQL Q14 + the saved coding question
    expect(server.sendCalls).toBeUndefined();
    await click(button('Send Assessment', $('.pv-footer')));
    expect(server.sendCalls).toBeUndefined();
    await click(button('Confirm & Send', $('.pv-confirm')));
    expect(apiPost).toHaveBeenCalledWith('/api/assessment/1/send', expect.objectContaining({ confirm: true, reviewed_fingerprint: 'fp-1' }));
    expect(server.sendCalls).toBe(1);
    expect($('.pv-success').textContent).toContain('Version 1 published');
    await click(button('Close Preview'));
    expect($('.ab-notice').textContent).toContain('Version 1 published');
    expect($('.ab-sent-link-input').value).toBe('https://hr.example.com/assessment/tok');
  });

  test('validation problems block sending from the preview', async () => {
    await mountBuilder();
    server.ready = false;
    await click(button('Validate', $('.ab-publish')));
    expect($('.ab-publish').textContent).toContain('Add at least one hidden test case.');
    await click(button('Preview & Send', $('.ab-publish')));
    expect($('.pv-invalid').textContent).toContain('still awaiting review');
    expect(button('Send Assessment', $('.pv-footer')).disabled).toBe(true);
  });

  test('arriving from Talent with ?preview=1 opens the preview of the draft', async () => {
    server = makeServer();
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    await act(async () => root.render(
      <MemoryRouter initialEntries={['/hiring-pipeline/assessment/1?preview=1']}>
        <Routes><Route path="/hiring-pipeline/assessment/:assessmentId" element={<AssessmentBuilder />} /></Routes>
      </MemoryRouter>,
    ));
    expect($('.pv-dialog')).toBeTruthy();
    expect($('.pv-status').textContent).toBe('Draft — Not Sent');
    expect($('.pv-summary').textContent).toContain('Asha Rao');
  });

  test('the scoring policy is saved with the draft', async () => {
    await mountBuilder();
    await click($('.ab-policy input[type="checkbox"]'));
    type($('#ab-weight-mcq'), 30);
    expect($('#ab-weight-coding').value).toBe('70');
    type($('#ab-min-coding'), 40);
    await click([...$$('.ab-policy input[type="checkbox"]')][1]);
    await click(button('Save Draft'));
    const [, body] = apiPut.mock.calls.find(([path]) => path === '/api/assessment/1');
    expect(body.scoring_policy).toEqual(expect.objectContaining({
      section_weights: { mcq: 30, coding: 70 }, min_coding_score: 40, coding_section_mandatory: true,
    }));
  });

  test('results show separate MCQ and coding scores, qualification and attempt history', async () => {
    server = null;
    await mountBuilder({ status: 'PASSED' });
    act(() => root.unmount()); container.remove();
    const state = makeServer({ status: 'PASSED' });
    state.result = {
      status: 'PASSED', percentage: 56, score: 28, total_points: 40, pass_basis: 'weighted', assessment_version: 2,
      applied_section_weights: { mcq: 40, coding: 60 },
      evaluation_breakdown: { sections: { mcq: { count: 30, percentage: 80, earned: 24, possible: 30 }, coding: { count: 1, percentage: 40, earned: 4, possible: 10 } } },
      qualification_checks: [{ rule: 'overall', label: 'Overall score at least 50%', met: true, actual: 56 },
        { rule: 'min_coding_score', label: 'Coding score at least 40%', met: true, actual: 40 }],
      question_results: [{ question_id: 14, question_type: 'sql', points_earned: 4, points_possible: 10, evaluation_method: 'executed', answer: 'print(1)',
        metadata: { language: 'python', tests_passed: 2, tests_total: 5, hidden_passed: 0, hidden_total: 3, result_status: 'partially_passed',
          qualification: 'qualified', compile_status: 'compiled', qualification_checks: [{ rule: 'min_tests_passed', label: 'At least 2 test case(s) passed', met: true }], tests: [] } }],
    };
    state.attempts = [{ question_id: 14, kind: 'run', language: 'python', passed: 2, total: 2, code: 'print(1)' },
      { question_id: 14, kind: 'submit', language: 'python', passed: 2, total: 5, marks: 4, max_marks: 10, code: 'print(1)' }];
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    await act(async () => root.render(
      <MemoryRouter initialEntries={['/hiring-pipeline/assessment/1']}>
        <Routes><Route path="/hiring-pipeline/assessment/:assessmentId" element={<AssessmentBuilder />} /></Routes>
      </MemoryRouter>,
    ));
    const tiles = $$('.ab-score-tile').map(t => t.textContent);
    expect(tiles[0]).toContain('MCQ80%');
    expect(tiles[1]).toContain('40%');
    expect(tiles[1]).toContain('weight 60%');
    expect(tiles[2]).toContain('56%');
    expect($('.ab-result-banner').textContent).toContain('assessment version 2');
    const result = $('.ab-coding-result');
    expect(result.textContent).toContain('4/10 marks');
    expect(result.textContent).toContain('Partially passed');
    expect(result.textContent).toContain('Qualified');
    expect(result.textContent).toContain('At least 2 test case(s) passed');
    expect(result.textContent).toContain('Attempt history (2)');
    expect(result.textContent).toContain('Final submission');
  });

  test('a new MCQ needs four options, exactly one correct answer and an explanation', async () => {
    await mountBuilder();
    await click(button('MCQ', $('.ab-add-bar')));
    const form = $('.ab-edit-form');
    type(form.querySelector('textarea'), 'Which retry policy keeps the payment API idempotent?');
    ['Retry with idempotency key', 'Retry blindly', 'Never retry', 'Retry only GETs'].forEach((text, i) => {
      type(form.querySelector(`[aria-label="Option ${'ABCD'[i]}"]`), text);
    });
    await click(button('Save', form));
    expect($('[role="alert"]').textContent).toContain('exactly one of the four options');
    await click(form.querySelector('[aria-label="Option A is correct"]'));
    await click(button('Save', form));
    expect($('[role="alert"]').textContent).toContain('explanation');
    const explanation = [...form.querySelectorAll('textarea')].at(-1);
    type(explanation, 'The idempotency key makes retries safe.');
    // Editing the text of the correct option keeps it correct.
    type(form.querySelector('[aria-label="Option A"]'), 'Retry with an idempotency key');
    await click(button('Save', form));
    const [path, body] = apiPost.mock.calls.find(([p]) => p === '/api/assessment/question');
    expect(path).toBe('/api/assessment/question');
    expect(body.options).toHaveLength(4);
    expect(body.correct_answer).toBe('Retry with an idempotency key');
    expect(body.explanation).toBe('The idempotency key makes retries safe.');
    expect(body).not.toHaveProperty('sort_order');
  });

  test('mcqProblem mirrors the server rules', () => {
    const good = { question_type: 'mcq', question_text: 'Q', options: ['a', 'b', 'c', 'd'], correct_answer: 'c', explanation: 'why' };
    expect(mcqProblem(good)).toBe('');
    expect(mcqProblem({ ...good, options: ['a', 'b', 'c'] })).toContain('four');
    expect(mcqProblem({ ...good, options: ['a', 'A ', 'c', 'd'] })).toContain('different');
    expect(mcqProblem({ ...good, correct_answer: 'z' })).toContain('exactly one');
    expect(mcqProblem({ ...good, explanation: '' })).toContain('explanation');
    expect(mcqProblem({ question_type: 'coding' })).toBe('');
  });
});
