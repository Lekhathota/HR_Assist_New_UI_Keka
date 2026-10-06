import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, useLocation } from 'react-router-dom';
import Login from './Login.jsx';
import { apiGet, apiPost, getToken, saveToken } from '../api.js';

jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiPost: jest.fn(), getToken: jest.fn(() => ''), saveToken: jest.fn() }));

let container, root;
const $ = selector => container.querySelector(selector);
function LocationProbe() { return <output>{useLocation().pathname}</output>; }
async function type(input, value) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.setItem('shimentox_login_intro_seen', 'true');
  window.matchMedia = jest.fn(() => ({ matches: false }));
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(
    <MemoryRouter initialEntries={['/login']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Login /><LocationProbe />
    </MemoryRouter>
  ));
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.clearAllMocks(); sessionStorage.clear(); localStorage.clear(); });

test('toggles password visibility', async () => {
  expect($('#password').type).toBe('password');
  await act(async () => $('.auth-reveal').click());
  expect($('#password').type).toBe('text');
  expect($('.auth-reveal').getAttribute('aria-label')).toBe('Hide password');
});

test('signs in, stores the session and opens Home', async () => {
  apiPost.mockResolvedValue({ ok: true, status: 200, data: { success: true, token: 't1', user: { username: 'lekha', role: 'admin', email: 'l@x.io' } } });
  await type($('#username'), 'lekha');
  await type($('#password'), 'secret');
  await act(async () => $('.auth-submit').click());
  expect(apiPost).toHaveBeenCalledWith('/api/login', { username: 'lekha', password: 'secret', remember: false });
  expect(saveToken).toHaveBeenCalledWith('t1', false);
  expect(JSON.parse(localStorage.getItem('recruitment_assist_user')).role).toBe('admin');
  expect($('output').textContent).toBe('/welcome');
});

test('shows the server error for bad credentials', async () => {
  apiPost.mockResolvedValue({ ok: false, status: 401, data: {} });
  await type($('#username'), 'lekha');
  await type($('#password'), 'wrong');
  await act(async () => $('.auth-submit').click());
  expect($('.auth-error').textContent).toContain('Invalid username or password.');
  expect($('.auth-submit').disabled).toBe(false);
});

test('Remember me stores only the username and prefills it next time', async () => {
  apiPost.mockResolvedValue({ ok: true, status: 200, data: { success: true, token: 't1', user: { username: 'lekha', role: 'admin' } } });
  await type($('#username'), 'lekha');
  await type($('#password'), 'secret');
  await act(async () => $('.auth-remember input').click());
  await act(async () => $('.auth-submit').click());
  expect(apiPost).toHaveBeenCalledWith('/api/login', { username: 'lekha', password: 'secret', remember: true });
  expect(saveToken).toHaveBeenCalledWith('t1', true);
  expect(localStorage.getItem('shimentox_remembered_username')).toBe('lekha');
  expect(JSON.stringify(localStorage)).not.toContain('secret');

  act(() => root.unmount());
  root = createRoot(container);
  await act(async () => root.render(
    <MemoryRouter initialEntries={['/login']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><Login /></MemoryRouter>
  ));
  expect($('#username').value).toBe('lekha');
  expect($('.auth-remember input').checked).toBe(true);
});

test('forgot password explains how to reset, and no social sign-in is offered', async () => {
  await act(async () => $('.auth-link').click());
  expect($('.auth-notice').textContent).toContain('contact your ShimentoX administrator');
  expect(apiPost).not.toHaveBeenCalled();
  expect($('.auth-sso')).toBeNull();
  expect(container.textContent).not.toMatch(/Google|Microsoft|continue with/i);
});

async function renderFresh(entry = '/login') {
  act(() => root.unmount());
  root = createRoot(container);
  await act(async () => root.render(
    <MemoryRouter initialEntries={[entry]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Login /><LocationProbe />
    </MemoryRouter>
  ));
}

test('a remembered session skips the form and opens the app', async () => {
  getToken.mockReturnValue('saved-token');
  apiGet.mockResolvedValue({ user: { username: 'lekha' } });
  await renderFresh();
  expect(apiGet).toHaveBeenCalledWith('/api/profile');
  expect($('output').textContent).toBe('/welcome');
  expect($('#password')).toBeNull();
});

test('an expired saved session falls back to the sign-in form', async () => {
  getToken.mockReturnValue('expired-token');
  apiGet.mockRejectedValue(new Error('GET /api/profile failed: 401'));
  await renderFresh();
  expect($('#password')).not.toBeNull();
  expect($('output').textContent).toBe('/login');
  getToken.mockReturnValue('');
});
