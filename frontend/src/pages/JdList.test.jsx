import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import JdList from './JdList.jsx';
import { apiGet } from '../api.js';

jest.mock('../api.js', () => ({
  JD_CACHE_KEY: 'jds',
  apiGet: jest.fn(),
  apiPost: jest.fn(),
  readSessionCache: () => null,
  writeSessionCache: () => {},
}));
jest.mock('../components/Layout.jsx', () => ({ children }) => <main>{children}</main>);
jest.mock('../components/EnterpriseFeedback.jsx', () => ({ toast: jest.fn(), useConfirm: () => jest.fn(), SkeletonBlock: () => null }));
jest.mock('../utils/useRoleCategories.js', () => ({ useRoleCategories: () => [] }));
jest.mock('jspdf', () => function JsPdf() {});
jest.mock('docx', () => ({}));
jest.mock('file-saver', () => ({ saveAs: jest.fn() }));
jest.mock('xlsx', () => ({}));

const JDS = [
  { id: 1, title: 'Data Engineer', status: 'Active', created_date: '2026-09-05' },
  { id: 2, title: 'ML Engineer', status: 'Active', created_date: '2026-09-18' },
  { id: 3, title: 'QA Analyst', status: 'Active', created: '2026-10-02T08:30:00' },
];

let container, root;
const $ = s => container.querySelector(s);
const titles = () => Array.from(container.querySelectorAll('.jobs-title-link')).map(a => a.textContent);

async function setValue(el, value) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
const click = async el => act(async () => el.click());

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  apiGet.mockResolvedValue(JDS);
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(<MemoryRouter><JdList /></MemoryRouter>));
  await click($('.jobs-more-btn'));
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

test('filters jobs posted on one date', async () => {
  expect(titles()).toEqual(['Data Engineer', 'ML Engineer', 'QA Analyst']);
  await setValue($('input[aria-label="Posted on"]'), '2026-09-18');
  expect(titles()).toEqual(['ML Engineer']);
  expect($('.jobs-filter-count').textContent).toBe('1');
});

test('filters jobs between two dates, open-ended or reversed', async () => {
  await click(Array.from(container.querySelectorAll('.jobs-date-mode button'))[1]);
  const [from, to] = container.querySelectorAll('.jobs-date-range input');
  await setValue(from, '2026-09-10');
  expect(titles()).toEqual(['ML Engineer', 'QA Analyst']);
  await setValue(to, '2026-09-30');
  expect(titles()).toEqual(['ML Engineer']);
  await setValue(from, '');
  expect(titles()).toEqual(['Data Engineer', 'ML Engineer']);
});

test('clear filters removes the date filter', async () => {
  await setValue($('input[aria-label="Posted on"]'), '2026-09-05');
  expect(titles()).toEqual(['Data Engineer']);
  await click($('.jobs-clear-btn'));
  expect(titles()).toEqual(['Data Engineer', 'ML Engineer', 'QA Analyst']);
});
