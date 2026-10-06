import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import Comparison from './Comparison.jsx';
import { apiGet, apiPostForm } from '../api.js';

jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiPostForm: jest.fn() }));
jest.mock('../components/Layout.jsx', () => ({ children }) => <main>{children}</main>);

const jds = [{ id: 1, title: 'Senior AI Engineer', department: 'Engineering', skills: 'Python, LLMs' }];
const response = {
  mode: 'bench',
  stats: [{ label: 'Required', value: 3 }, { label: 'Analyzed', value: 4 }],
  selected_results: [{ id: 1, name: 'Bea Low', match_score: 70 }, { id: 2, name: 'Al High', match_score: 95, strengths: ['Python'] }],
  waitlisted_results: [{ id: 3, name: 'Wai Ting', match_score: 60 }],
  rejected_results: [],
};

let container, root;
const $ = selector => container.querySelector(selector);
const click = element => act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })));
async function chooseJob() {
  const select = $('#jd_id');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, '1');
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  apiGet.mockResolvedValue(jds);
  apiPostForm.mockResolvedValue({ ok: true, data: response });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><Comparison /></MemoryRouter>));
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.clearAllMocks(); });

test('run stays disabled until a job is chosen, then analyzes the bench without files', async () => {
  expect($('.az-run').disabled).toBe(true);
  expect(container.textContent).toContain('No analysis yet');
  await chooseJob();
  expect($('.az-jd').textContent).toContain('Senior AI Engineer');
  expect($('.az-run').textContent).toContain('Analyze bench');
  await act(async () => $('.az-run').click());
  const form = apiPostForm.mock.calls[0][1];
  expect(apiPostForm.mock.calls[0][0]).toBe('/api/compare');
  expect(form.get('jd_id')).toBe('1');
  expect(form.getAll('resumes')).toHaveLength(0);
});

test('upload source requires at least one resume', async () => {
  await chooseJob();
  click(container.querySelectorAll('.az-segment button')[1]);
  expect($('.az-drop')).not.toBeNull();
  expect($('.az-run').disabled).toBe(true);
  expect($('.az-hint').textContent).toBe('Add at least one resume to continue.');
});

test('shows stats, grouped tabs, score order and search', async () => {
  await chooseJob();
  await act(async () => $('.az-run').click());
  expect(Array.from(container.querySelectorAll('.az-stats strong')).map(el => el.textContent)).toEqual(['3', '4']);
  expect(Array.from(container.querySelectorAll('.az-tabs button')).map(el => el.textContent)).toEqual(['Selected2', 'Waitlisted1', 'Rejected0']);
  expect(Array.from(container.querySelectorAll('.az-result h3')).map(el => el.textContent)).toEqual(['Al High', 'Bea Low']);
  click(container.querySelectorAll('.az-tabs button')[1]);
  expect($('.az-result').classList.contains('tone-waitlisted')).toBe(true);
  expect($('.az-result h3').textContent).toBe('Wai Ting');
  const search = $('.az-search input');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(search, 'zzz');
    search.dispatchEvent(new Event('input', { bubbles: true }));
  });
  expect($('.az-list-empty').textContent).toContain('No waitlisted candidates match');
});
