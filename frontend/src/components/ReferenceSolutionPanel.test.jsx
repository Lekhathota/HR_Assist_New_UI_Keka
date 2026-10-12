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
