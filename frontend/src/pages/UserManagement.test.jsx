import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import UserManagement, { roleAccessSummary } from './UserManagement.jsx';
import { apiGet, apiPatch, apiPost } from '../api.js';

const mockConfirm = jest.fn();
jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiPatch: jest.fn(), apiPost: jest.fn() }));
jest.mock('../components/Layout.jsx', () => ({ children }) => <main>{children}</main>);
jest.mock('../components/EnterpriseFeedback.jsx', () => ({ toast: jest.fn(), useConfirm: () => mockConfirm }));

const USERS = [
  { id: 1, username: 'lekha', email: 'lekha@x.io', role: 'admin', is_active: true, created_at: '2026-01-12T00:00:00Z' },
  { id: 2, username: 'ravi', email: 'ravi@x.io', role: 'recruiter', is_active: true },
  { id: 3, username: 'meera', email: 'meera@x.io', role: 'finance', is_active: false },
];

let container, root;
const $ = s => container.querySelector(s);
const $$ = s => Array.from(container.querySelectorAll(s));
const names = () => $$('.um-user strong').map(el => el.firstChild.textContent);
async function setValue(el, value, event = 'input') {
  const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  await act(async () => {
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value);
    el.dispatchEvent(new Event(event, { bubbles: true }));
  });
}

async function render(role = 'admin') {
  localStorage.setItem('recruitment_assist_user', JSON.stringify({ username: 'lekha', role }));
  await act(async () => root.render(<MemoryRouter><UserManagement /></MemoryRouter>));
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  mockConfirm.mockResolvedValue(true);
  apiGet.mockResolvedValue({ users: USERS.map(u => ({ ...u })) });
  apiPatch.mockResolvedValue({ ok: true, data: { success: true } });
  apiPost.mockResolvedValue({ ok: true, data: { success: true } });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.clearAllMocks(); localStorage.clear(); });

test('shows real summary counts and lists active users first', async () => {
  await render();
  expect($$('.um-stat strong').map(el => el.textContent)).toEqual(['3', '2', '1', '1']);
  expect(names()).toEqual(['lekha', 'ravi', 'meera']);
  expect($('.um-you')).not.toBeNull();
});

test('search, role and status filters narrow the list', async () => {
  await render();
  await setValue($('.um-search input'), 'rav');
  expect(names()).toEqual(['ravi']);
  await setValue($('.um-search input'), '');
  await setValue($('.um-toolbar select'), 'finance', 'change');
  expect(names()).toEqual(['meera']);
  await setValue($('.um-toolbar select'), '', 'change');
  await act(async () => $$('.um-segment button')[2].click());
  expect(names()).toEqual(['meera']);
});

test('you cannot change your own role or deactivate yourself', async () => {
  await render();
  const selfRow = $$('tbody tr')[0];
  expect(selfRow.querySelector('.um-role-select').disabled).toBe(true);
  expect(selfRow.querySelector('.um-actions button').disabled).toBe(true);
});

test('role changes and deactivation are confirmed, then saved', async () => {
  await render();
  const raviRow = $$('tbody tr')[1];
  await setValue(raviRow.querySelector('.um-role-select'), 'hr', 'change');
  expect(mockConfirm).toHaveBeenCalled();
  expect(apiPatch).toHaveBeenCalledWith('/api/admin/users/2', { role: 'hr' });
  await act(async () => $$('tbody tr')[1].querySelector('.um-actions button').click());
  expect(apiPatch).toHaveBeenCalledWith('/api/admin/users/2', { is_active: false });
  expect($$('.um-status').map(el => el.textContent)).toContain('Inactive');
});

test('nothing changes when the confirmation is cancelled', async () => {
  mockConfirm.mockResolvedValueOnce(false);
  await render();
  await setValue($$('tbody tr')[1].querySelector('.um-role-select'), 'hr', 'change');
  expect(apiPatch).not.toHaveBeenCalled();
});

test('the Add user dialog creates the account and reloads the list', async () => {
  await render();
  await act(async () => $('.um-header .um-btn').click());
  const inputs = $$('.um-dialog input');
  await setValue(inputs[0], 'jane.doe');
  await setValue(inputs[1], 'jane@x.io');
  await setValue(inputs[2], 'a-long-password-123');
  await act(async () => $$('.um-role-option input').find(i => i.value === 'hr').click());
  await act(async () => $('.um-dialog').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(apiPost).toHaveBeenCalledWith('/api/admin/users', { username: 'jane.doe', email: 'jane@x.io', password: 'a-long-password-123', role: 'hr' });
  expect($('.um-dialog')).toBeNull();
  expect(apiGet).toHaveBeenCalledTimes(2);
});

test('non-admins see an access message and no user data is requested', async () => {
  await render('recruiter');
  expect(container.textContent).toContain('Administrator access required');
  expect(apiGet).not.toHaveBeenCalled();
});

test('role descriptions follow the real page access rules', () => {
  expect(roleAccessSummary('admin')).toContain('Full access');
  expect(roleAccessSummary('recruiter')).toBe('Home, Jobs, Talent, Analyze, Hiring Pipeline');
  expect(roleAccessSummary('it')).toBe('Home and Profile only');
});
