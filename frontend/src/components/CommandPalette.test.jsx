import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { CommandPalette, searchResultItems } from './FrontendPolish.jsx';
import { apiGet } from '../api.js';

jest.mock('../api.js', () => ({ apiGet: jest.fn() }));

const results = {
  jobs: [{ id: 3, title: 'Senior Data Engineer', job_code: 'DE-01', client_name: 'ABC Corp', status: 'Active' }],
  candidates: [{ id: 9, name: 'Data Dan', jd_title: 'Senior Data Engineer', email: 'dan@x.io' }],
  clients: [],
  vendors: [],
};

let container, root;
const $ = selector => container.querySelector(selector);
function LocationProbe() { const l = useLocation(); return <output>{l.pathname + l.search}</output>; }
const wait = ms => act(() => new Promise(resolve => setTimeout(resolve, ms)));

async function type(value) {
  const input = $('.command-palette-input input');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await wait(300); // debounce
}
const key = (k) => act(() => $('.command-palette-input input').dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true })));

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.setItem('recruitment_assist_user', JSON.stringify({ role: 'admin' }));
  apiGet.mockResolvedValue(results);
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(
    <MemoryRouter initialEntries={['/welcome']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <CommandPalette /><LocationProbe />
    </MemoryRouter>
  ));
  act(() => window.dispatchEvent(new Event('open-command-palette')));
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.clearAllMocks(); localStorage.clear(); });

test('searches jobs and candidates by name and groups the results', async () => {
  await type('data');
  expect(apiGet).toHaveBeenCalledWith('/api/search?q=data');
  const groups = Array.from(container.querySelectorAll('.command-palette-group')).map(g => g.textContent);
  expect(groups).toEqual(['Jobs', 'Candidates']);
  const labels = Array.from(container.querySelectorAll('.command-palette-list strong')).map(s => s.textContent);
  expect(labels).toEqual(['Senior Data Engineer', 'Data Dan']);
});

test('arrow keys move the selection and Enter opens the record', async () => {
  await type('data');
  await key('ArrowDown');
  expect($('.command-palette-list button.active strong').textContent).toBe('Data Dan');
  await key('Enter');
  expect($('output').textContent).toBe('/talent/9');
  expect($('.command-palette')).toBeNull();
});

test('short queries only filter pages and do not call the API', async () => {
  await type('j');
  expect(apiGet).not.toHaveBeenCalled();
  expect($('.command-palette-tip')).not.toBeNull();
});

test('shows a clear message when search fails', async () => {
  apiGet.mockRejectedValue(new Error('offline'));
  await type('zz');
  expect($('[role="alert"]').textContent).toBe('Search is unavailable right now.');
});

test('client and vendor results link to the right record', () => {
  const items = searchResultItems({ clients: [{ id: 4, name: 'ABC Corp' }], vendors: [{ id: 2, company_name: 'Talent & Co' }] });
  expect(items.map(i => i.path)).toEqual(['/clients?client=4', '/vendors?search=Talent%20%26%20Co']);
});
