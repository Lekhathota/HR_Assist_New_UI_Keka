import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ReferenceSolutionPanel from './ReferenceSolutionPanel.jsx';
import { apiGet, apiPost, apiPut } from '../api.js';

jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiPost: jest.fn(), apiPut: jest.fn() }));

const languages = [{ key: 'python', label: 'Python 3' }, { key: 'java', label: 'Java' }];
const config = (overrides = {}) => ({
  question_id: 11, question_type: 'coding', reference_solution: 'print(int(input()) * 2)', reference_language: 'python',
  sql_schema: '', order_matters: false, editable: true,
  execution: { coding: { available: true, languages }, sql: { available: true } },
  test_cases: [
    { id: 't1', name: 'basic', input: '1\n', expected_output: '2\n', hidden: false, enabled: true },
    { id: 't2', name: '', input: '5\n', expected_output: '10\n', hidden: true, enabled: true },
  ],
  verification: { status: 'not_verified', results: [], message: 'The reference solution has not been verified.' },
  ...overrides,
});

let root, container;
const $ = s => container.querySelector(s);
const button = text => [...container.querySelectorAll('button')].find(b => b.textContent.includes(text));
const setValue = async (el, value) => act(async () => {
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value);
  el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
});

async function render(data, onChange = jest.fn()) {
  apiGet.mockResolvedValue(data);
  await act(async () => root.render(<ReferenceSolutionPanel question={{ id: 11, question_type: data.question_type, test_cases: data.test_cases }} onChange={onChange} />));
  await act(async () => { $('details').open = true; $('details').dispatchEvent(new Event('toggle')); });
  return onChange;
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  jest.spyOn(window, 'confirm').mockReturnValue(true);
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.restoreAllMocks(); jest.clearAllMocks(); });

test('loads the configuration with visible/hidden summary and status', async () => {
  await render(config());
  expect(apiGet).toHaveBeenCalledWith('/api/assessment/question/11/reference');
  expect($('summary').textContent).toContain('(1 visible, 1 hidden)');
  expect($('.rs-status').textContent).toBe('Not verified');
  expect($('.rs-code').value).toBe('print(int(input()) * 2)');
  expect(container.querySelectorAll('.rs-case')).toHaveLength(2);
});

test('editing marks unsaved, and Save & verify sends the whole configuration', async () => {
  apiPut.mockResolvedValue({ ok: true, data: config({
    test_cases: config().test_cases.map(c => (c.id === 't2' ? { ...c, expected_output: '11\n' } : c)),
    verification: { status: 'failed', message: '1/2 enabled test cases passed.', results: [
      { id: 't1', passed: true, status: 'passed', actual: '2\n', error: '' },
      { id: 't2', passed: false, status: 'wrong_answer', actual: '10\n', error: '' },
    ] },
  }) });
  const onChange = await render(config());
  const expected = container.querySelectorAll('.rs-case')[1].querySelectorAll('textarea')[1];
  await setValue(expected, '11\n');
  expect(container.textContent).toContain('Unsaved changes');
  expect(button('Verify solution').disabled).toBe(true);
  await act(async () => button('Save & verify').click());
  const [path, body] = apiPut.mock.calls[0];
  expect(path).toBe('/api/assessment/question/11/reference');
  expect(body.verify).toBe(true);
  expect(body.test_cases[1].expected_output).toBe('11\n');
  expect($('.rs-status').textContent).toBe('Failed');
  expect(container.textContent).toContain('wrong answer');
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ verification: expect.objectContaining({ status: 'failed' }) }));
});

test('add, reorder, hide and delete test cases', async () => {
  await render(config());
  await act(async () => button('Add test case').click());
  expect(container.querySelectorAll('.rs-case')).toHaveLength(3);
  await act(async () => container.querySelectorAll('.rs-case')[1].querySelector('[aria-label="Move up"]').click());
  expect(container.querySelectorAll('.rs-name')[0].value).toBe('');
  await setValue(container.querySelectorAll('.rs-case')[0].querySelector('select'), 'visible');
  expect($('summary').textContent).toContain('(2 visible, 1 hidden)');
  await act(async () => container.querySelectorAll('.rs-case')[2].querySelector('[aria-label="Delete test case"]').click());
  expect(container.querySelectorAll('.rs-case')).toHaveLength(2);
});

test('verify shows execution unavailable when no sandbox is configured', async () => {
  apiPost.mockResolvedValue({ ok: true, data: config({
    execution: { coding: { available: false, languages }, sql: { available: true } },
    verification: { status: 'unavailable', results: [], message: 'Code execution is not configured.' },
  }) });
  await render(config({ execution: { coding: { available: false, languages }, sql: { available: true } } }));
  expect(container.textContent).toContain('Code execution is not configured on the server');
  await act(async () => button('Verify solution').click());
  expect(apiPost).toHaveBeenCalledWith('/api/assessment/question/11/verify', {});
  expect($('.rs-status').textContent).toBe('Execution unavailable');
});

test('read-only after the assessment is sent, but verification can still run', async () => {
  await render(config({ editable: false }));
  expect($('.rs-code').disabled).toBe(true);
  expect(button('Add test case')).toBeUndefined();
  expect(button('Save & verify')).toBeUndefined();
  expect(button('Verify solution').disabled).toBe(false);
});

const runtimes = [
  { key: 'python', label: 'Python 3', runtime: 'Python 3.8 (Judge0 CE)', entry_point: 'stdin/stdout', run: 'python3 script.py' },
  { key: 'java', label: 'Java', runtime: 'OpenJDK 13 (Judge0 CE)', entry_point: 'public class Main', run: 'javac Main.java' },
];
const codingConfig = (overrides = {}) => config({
  runtimes,
  comparison_modes: [{ key: 'trim_trailing', label: 'Ignore trailing spaces' }, { key: 'tokens', label: 'Compare tokens' }],
  jd: { id: 20, title: 'Backend Engineer' }, client: { id: 5, name: 'Acme' },
  problems: [],
  config: {
    title: 'Double it', question_text: 'Read n and print twice n for every input line.', skill_tag: 'Arithmetic', difficulty: 'Medium',
    points: 10, allowed_languages: ['python', 'java'], input_format: 'n', output_format: '2n', constraints: '|n| <= 10^9',
    edge_cases: 'negative n', time_limit_seconds: 2, memory_limit_mb: 128, comparison: 'trim_trailing',
    scoring: { partial_credit: true, min_tests_passed: 1, min_score_percent: 50, require_mandatory: true },
    reference_solutions: {}, generation_prompt: 'Simple arithmetic warm-up',
  },
  ...overrides,
});

test('shows the full coding configuration with JD/client, limits, runtimes and a marks table', async () => {
  await render(codingConfig());
  expect($('summary').textContent).toContain('Coding Configuration');
  expect($('summary').textContent).toContain('Ready to publish');
  expect(container.textContent).toContain('For Backend Engineer · client Acme');
  expect(container.textContent).toContain('Recruiter prompt: Simple arithmetic warm-up');
  expect(container.textContent).toContain('OpenJDK 13 (Judge0 CE)');
  const rows = [...container.querySelectorAll('.rs-marks tbody tr')].map(r => r.textContent);
  expect(rows).toEqual(['0 of 2' + '0/10' + 'No', '1 of 2' + '5/10' + 'Yes', '2 of 2' + '10/10' + 'Yes']);
});

test('configuration, weights, mandatory tests and an extra reference language are saved together', async () => {
  apiPut.mockResolvedValue({ ok: true, data: codingConfig() });
  const onChange = await render(codingConfig());
  const inputByLabel = text => [...container.querySelectorAll('.rs-field')].find(f => f.textContent.startsWith(text)).querySelector('input, textarea, select');
  await setValue(inputByLabel('Maximum marks'), '20');
  await setValue(inputByLabel('Time limit per test'), '1.5');
  await setValue(inputByLabel('Memory limit'), '64');
  await setValue(inputByLabel('Minimum tests passed'), '2');
  await setValue(inputByLabel('Constraints'), '1 <= n <= 100');
  await act(async () => [...container.querySelectorAll('.rs-languages input')][1].click()); // drop Java
  await setValue(container.querySelectorAll('[aria-label="Test case weight"]')[1], '3');
  await act(async () => container.querySelectorAll('[aria-label="Mandatory test"]')[1].click());
  await setValue($('[aria-label="Add a reference solution in"]'), 'java');
  await act(async () => button('Add').click());
  await setValue($('#rs-ref-11-java'), 'public class Main {}');
  await act(async () => button('Save & verify').click());
  const [, body] = apiPut.mock.calls[0];
  expect(body.config).toEqual(expect.objectContaining({
    points: 20, time_limit_seconds: 1.5, memory_limit_mb: 64, constraints: '1 <= n <= 100', allowed_languages: ['python'],
    scoring: expect.objectContaining({ min_tests_passed: 2 }), reference_solutions: { java: 'public class Main {}' },
  }));
  expect(body.test_cases[1]).toEqual(expect.objectContaining({ weight: 3, mandatory: true }));
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ title: 'Double it', points: 10 }));
});

test('unequal weights replace the marks table with the weighted formula', async () => {
  await render(codingConfig({ test_cases: config().test_cases.map((c, i) => ({ ...c, weight: i + 1 })) }));
  expect($('.rs-marks')).toBeNull();
  expect(container.textContent).toContain('weight of passed tests ÷ total weight');
});

test('an invalid question lists what blocks publication and shows failing tests per language', async () => {
  await render(codingConfig({
    problems: ['Add at least one hidden test case.', 'The reference solution fails one or more test cases.'],
    verification: { status: 'failed', message: 'The reference solution fails 1 test run(s).', results: [
      { id: 't2', language: 'python', passed: true, status: 'passed', actual: '10\n' },
      { id: 't2', language: 'java', passed: false, status: 'compile_error', error: 'Main.java:1: error' },
    ] },
  }));
  expect($('summary').textContent).toContain('Invalid · 2 issues');
  expect(container.textContent).toContain('Add at least one hidden test case.');
  const results = container.querySelectorAll('.rs-case')[1].querySelectorAll('.rs-case-result');
  expect([...results].map(r => r.textContent)).toEqual([expect.stringContaining('python'), expect.stringContaining('compile error')]);
  expect(results[1].textContent).toContain('Main.java:1: error');
});
