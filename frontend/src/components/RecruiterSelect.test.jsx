import React, { act, useState } from 'react';
import { createRoot } from 'react-dom/client';
import RecruiterSelect from './RecruiterSelect.jsx';
import { apiGet, apiPost } from '../api.js';

jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiPost: jest.fn() }));
jest.mock('./EnterpriseFeedback.jsx', () => ({ toast: jest.fn() }));

let container;
let root;

function Harness({ initial = '' }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <RecruiterSelect id="r" value={value} onChange={setValue} />
      <output>{value}</output>
    </>
  );
}

async function render(initial) {
  await act(async () => root.render(<Harness initial={initial} />));
}

// React tracks controlled-input values, so set them through the native setter.
function setValue(element, value) {
  const proto = element.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(element, value);
  element.dispatchEvent(new Event(element.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
}

const select = () => container.querySelector('#r');
const optionLabels = () => Array.from(container.querySelectorAll('#r option')).map(o => o.textContent);
const selectedValue = () => container.querySelector('output').textContent;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  apiGet.mockResolvedValue({ recruiters: ['Prajwal P', 'Rajeswari L'] });
  apiPost.mockResolvedValue({ ok: true, data: { name: 'Kiran R', created: true, recruiters: ['Prajwal P', 'Rajeswari L', 'Kiran R'] } });
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

test('lists recruiters from the API with an add option', async () => {
  await render();
  expect(optionLabels()).toEqual(['Select recruiter', 'Prajwal P', 'Rajeswari L', '+ Add new recruiter']);
  act(() => setValue(select(), 'Rajeswari L'));
  expect(selectedValue()).toBe('Rajeswari L');
});

test('keeps a JD recruiter that is not in the list', async () => {
  await render('Old Name');
  expect(optionLabels()).toContain('Old Name');
  expect(select().value).toBe('Old Name');
});

test('adds a new recruiter and selects it', async () => {
  await render();
  act(() => setValue(select(), '__add_recruiter__'));
  expect(selectedValue()).toBe('');
  const input = container.querySelector('input[aria-label="New recruiter name"]');
  act(() => setValue(input, '  Kiran   R '));
  await act(async () => container.querySelector('.recruiter-add-btn').click());
  expect(apiPost).toHaveBeenCalledWith('/api/recruiters', { name: 'Kiran R' });
  expect(selectedValue()).toBe('Kiran R');
  expect(optionLabels()).toContain('Kiran R');
  expect(container.querySelector('input[aria-label="New recruiter name"]')).toBeNull();
});
