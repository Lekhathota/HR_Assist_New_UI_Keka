import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import CodingQuestionsPanel from './CodingQuestionsPanel.jsx';
import AssessmentBuilder from '../pages/AssessmentBuilder.jsx';
import { apiDelete, apiGet, apiPost, apiPut } from '../api.js';

jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiPost: jest.fn(), apiPut: jest.fn(), apiDelete: jest.fn() }));
jest.mock('./Layout.jsx', () => ({ children }) => <main>{children}</main>);
jest.mock('./ReferenceSolutionPanel.jsx', () => () => null);
jest.mock('./ProctoringEvidence.jsx', () => () => null);
jest.mock('../utils/assessmentPdf.js', () => ({ downloadAssessmentPdf: jest.fn() }));

const LANGUAGES = [{ key: 'python', label: 'Python 3' }, { key: 'java', label: 'Java' }, { key: 'cpp', label: 'C++' }];

// In-memory stand-in for /api/assessment/1/coding/* (mirrors coding_question_service responses).
function makeServer({ max = 20 } = {}) {
  const state = { specs: [], clientPrompt: 'Acme default rules', clientDefault: 'Acme default rules', baseCoding: 2, nextId: 1, nextQ: 500, failNext: null, generated: [] };
  const config = () => ({
    editable: true, jd: { id: 20, title: 'Backend Engineer' }, client: { id: 5, name: 'Acme' },
    client_prompt: state.clientPrompt, client_default_prompt: state.clientDefault,
    specs: state.specs.map(s => ({ ...s })),
    coding_question_count: state.baseCoding + state.specs.filter(s => s.status === 'generated').length,
    limits: { max_coding_questions: max, max_questions: 60, max_prompt_chars: 4000, max_client_prompt_chars: 4000 },
    languages: LANGUAGES, difficulties: ['Easy', 'Medium', 'Hard'],
  });
  const ok = data => Promise.resolve({ ok: true, status: 200, data: { success: true, ...data } });
  const fail = (status, error) => Promise.resolve({ ok: false, status, data: { error } });
  const spec = id => state.specs.find(s => s.id === id);
  apiGet.mockImplementation(path => {
    if (path === '/api/assessment/1/coding') return Promise.resolve(config());
    if (path === '/api/assessment/1') return Promise.resolve({
      assessment: { id: 1, status: 'DRAFT', title: 'Exam', candidate_id: 9, jd_id: 20 },
      questions: state.generated.map((q, i) => ({ ...q, sort_order: i })), answers: [],
    });
    return Promise.resolve({});
  });
  apiPost.mockImplementation((path, body) => {
    if (path === '/api/assessment/1/coding/specs') {
      if (state.specs.length >= max) return fail(409, `An assessment can have at most ${max} custom coding questions.`);
      const created = { id: `s${state.nextId++}`, prompt: body.prompt, language: body.language, difficulty: body.difficulty,
        points: body.points, status: 'pending', last_error: '', question: null };
      state.specs.push(created);
      return ok({ spec: created, config: config() });
    }
    const match = path.match(/^\/api\/assessment\/1\/coding\/specs\/(\w+)\/generate$/);
    if (match) {
      const target = spec(match[1]);
      Object.assign(target, body);
      if (state.failNext) {
        const message = state.failNext;
        state.failNext = null;
        Object.assign(target, { status: 'failed', last_error: message });
        return fail(502, message);
      }
      const question = target.question || { id: state.nextQ++ };
      Object.assign(question, { question_type: 'coding', source: 'custom_coding', generation_prompt: target.prompt,
        question_text: `Generated for: ${target.prompt}`, points: target.points, tests_verified: true,
        test_cases: [{ hidden: false }, { hidden: true }] });
      Object.assign(target, { status: 'generated', last_error: '', question });
      state.generated = state.generated.filter(q => q.id !== question.id).concat(question);
      return ok({ spec: target, question, config: config() });
    }
    return ok({});
  });
  apiPut.mockImplementation((path, body) => {
    if (path === '/api/assessment/1/coding/client-prompt') {
      state.clientPrompt = body.prompt;
      if (body.save_as_client_default) state.clientDefault = body.prompt;
      return ok(config());
    }
    const match = path.match(/^\/api\/assessment\/1\/coding\/specs\/(\w+)$/);
    if (match) {
      if (body.language === 'cobol') return fail(400, 'Unsupported language');
      Object.assign(spec(match[1]), body);
      return ok({ spec: spec(match[1]), config: config() });
    }
    return ok({});
  });
  apiDelete.mockImplementation(path => {
    const id = path.split('/').pop();
    const removed = spec(id);
    state.specs = state.specs.filter(s => s.id !== id);
    if (removed?.question) state.generated = state.generated.filter(q => q.id !== removed.question.id);
    return ok(config());
  });
  return state;
}

let root, container, server, onQuestionsChanged;
const $ = s => container.querySelector(s);
const $$ = s => [...container.querySelectorAll(s)];
const button = text => $$('button').find(b => b.textContent.trim().includes(text));
const heading = () => $('#ab-coding-title').textContent;

function type(el, value) {
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  act(() => {
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, String(value));
    el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
  });
}
async function click(el) { await act(async () => el.click()); }
async function mount(options) {
  server = makeServer(options);
  onQuestionsChanged = jest.fn();
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  await act(async () => root.render(<CodingQuestionsPanel assessmentId="1" onQuestionsChanged={onQuestionsChanged} />));
}
async function addAndGenerate(prompt, extra = {}) {
  await click(button('+ Add Coding Question'));
  const card = $$('.ab-coding-card').at(-1);
  type(card.querySelector('textarea'), prompt);
  if (extra.language) type(card.querySelector('select[id^="ab-coding-lang"]'), extra.language);
  if (extra.difficulty) type(card.querySelector('select[id^="ab-coding-diff"]'), extra.difficulty);
  await click([...card.querySelectorAll('button')].find(b => b.textContent.includes('Generate Question')));
  return card;
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  jest.spyOn(window, 'confirm').mockReturnValue(true);
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.restoreAllMocks(); jest.clearAllMocks(); });

describe('Coding Questions panel', () => {
  test.each([1, 2, 5, 10])('adds and generates %i coding questions, each from its own prompt', async (count) => {
    await mount();
    expect(heading()).toContain('Coding Questions: 2');
    for (let i = 0; i < count; i += 1) await addAndGenerate(`Client requirement number ${i}`);
    expect($$('.ab-coding-card')).toHaveLength(count);
    expect(heading()).toContain(`Coding Questions: ${2 + count}`);
    const generateCalls = apiPost.mock.calls.filter(([path]) => path.endsWith('/generate'));
    expect(generateCalls.map(([, body]) => body.prompt)).toEqual(Array.from({ length: count }, (_, i) => `Client requirement number ${i}`));
    expect(onQuestionsChanged).toHaveBeenCalledTimes(count);
    expect(container.textContent).toContain(`${count} generated`);
  });

  test('language, difficulty and the prompt are sent with generation and the preview shows the question', async () => {
    await mount();
    const card = await addAndGenerate('Rate limiter in Java', { language: 'java', difficulty: 'Hard' });
    const [, body] = apiPost.mock.calls.find(([path]) => path.endsWith('/generate'));
    expect(body).toEqual(expect.objectContaining({ prompt: 'Rate limiter in Java', language: 'java', difficulty: 'Hard' }));
    expect(card.textContent).toContain('Generated for: Rate limiter in Java');
    expect(card.textContent).toContain('2 test cases (1 hidden)');
    expect(card.querySelector('.ab-coding-status').textContent).toBe('Generated');
    expect(card.querySelector('a[href^="#ab-q-"]')).toBeTruthy();
  });

  test('an empty prompt is rejected before calling the API', async () => {
    await mount();
    await click(button('+ Add Coding Question'));
    await click(button('Generate Question'));
    expect($('[role="alert"]').textContent).toContain('requirements');
    expect(apiPost.mock.calls.filter(([path]) => path.endsWith('/generate'))).toHaveLength(0);
  });

  test('regenerate asks first and keeps the same entry; edits can be saved without generating', async () => {
    await mount();
    const card = await addAndGenerate('First version');
    type(card.querySelector('textarea'), 'Second version');
    await click(button('Save changes'));
    expect(apiPut).toHaveBeenCalledWith('/api/assessment/1/coding/specs/s1', { prompt: 'Second version' });
    window.confirm.mockReturnValueOnce(false);
    await click(button('Regenerate'));
    expect(apiPost.mock.calls.filter(([path]) => path.endsWith('/generate'))).toHaveLength(1);
    await click(button('Regenerate'));
    expect(apiPost.mock.calls.filter(([path]) => path.endsWith('/generate'))).toHaveLength(2);
    expect($$('.ab-coding-card')).toHaveLength(1);
    expect(container.textContent).toContain('Generated for: Second version');
  });

  test('remove deletes the entry and its question', async () => {
    await mount();
    await addAndGenerate('Entry to delete');
    await click(button('Remove'));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('generated question is removed'));
    expect(apiDelete).toHaveBeenCalledWith('/api/assessment/1/coding/specs/s1');
    expect($$('.ab-coding-card')).toHaveLength(0);
    expect(heading()).toContain('Coding Questions: 2');
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

  test('the limit disables adding more', async () => {
    await mount({ max: 2 });
    await click(button('+ Add Coding Question'));
    await click(button('+ Add Coding Question'));
    expect(button('+ Add Coding Question').disabled).toBe(true);
    expect(container.textContent).toContain('limit 2');
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
    await addAndGenerate('Persisted prompt');
    act(() => root.unmount());
    root = createRoot(container);
    await act(async () => root.render(<CodingQuestionsPanel assessmentId="1" />));
    expect(container.textContent).toContain('Persisted prompt');
    expect($('.ab-coding-status').textContent).toBe('Generated');
  });
});

describe('Assessment Builder integration', () => {
  async function mountBuilder() {
    server = makeServer();
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    await act(async () => root.render(
      <MemoryRouter initialEntries={['/hiring-pipeline/assessment/1']}>
        <Routes><Route path="/hiring-pipeline/assessment/:assessmentId" element={<AssessmentBuilder />} /></Routes>
      </MemoryRouter>,
    ));
  }

  test('generated coding questions appear in the question list with their prompt', async () => {
    await mountBuilder();
    expect($('#ab-coding-title')).toBeTruthy();
    await addAndGenerate('Builder-level requirement');
    const card = $$('.ab-question-card').find(c => c.textContent.includes('Generated for: Builder-level requirement'));
    expect(card.textContent).toContain('Custom prompt');
    expect(card.textContent).toContain('Recruiter prompt: Builder-level requirement');
    expect(card.id).toMatch(/^ab-q-\d+$/);
  });

  test('sending warns about entries that were never generated', async () => {
    await mountBuilder();
    await addAndGenerate('Generated one');
    await click(button('+ Add Coding Question'));
    window.confirm.mockReturnValueOnce(false);
    await click(button('Send Assessment'));
    expect(window.confirm).toHaveBeenLastCalledWith(expect.stringContaining('1 coding question entry has no generated question'));
    expect(apiPost.mock.calls.filter(([path]) => path.endsWith('/generate-email'))).toHaveLength(0);
  });
});
