import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, useLocation } from 'react-router-dom';
import UserMenu from './UserMenu.jsx';
import { apiPost, clearToken, getToken } from '../api.js';

jest.mock('../api.js', () => ({ apiPost: jest.fn(), clearToken: jest.fn(), getToken: jest.fn() }));

let container;
let root;
function LocationProbe() {
  return <output>{useLocation().pathname}</output>;
}
function renderMenu() {
  act(() => root.render(
    <MemoryRouter initialEntries={['/welcome']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <UserMenu />
      <LocationProbe />
    </MemoryRouter>
  ));
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  localStorage.setItem('recruitment_assist_user', JSON.stringify({ username: 'admin', role: 'admin', email: 'admin@example.com' }));
  jest.clearAllMocks();
  getToken.mockReturnValue('token');
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

test('shows the user name and opens a menu with Edit Profile and Logout', () => {
  renderMenu();
  const toggle = container.querySelector('.workspace-user');
  expect(toggle.textContent).toContain('admin');
  expect(container.querySelector('[role="menu"]')).toBeNull();
  act(() => toggle.click());
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
  expect(container.querySelector('a[href="/profile#edit-profile"]').textContent).toBe('Edit Profile');
  expect(container.querySelector('.workspace-user-dropdown-logout').textContent).toBe('Logout');
});

test('shows a Login link when there is no session', () => {
  getToken.mockReturnValue(null);
  renderMenu();
  expect(container.querySelector('.workspace-user')).toBeNull();
  expect(container.querySelector('a[href="/login"]').textContent).toBe('Login');
});

test.each([false, true])('Logout clears the session and returns to login (API failure: %s)', async failure => {
  apiPost.mockImplementation(() => failure ? Promise.reject(new Error('Offline')) : Promise.resolve({ ok: true }));
  renderMenu();
  act(() => container.querySelector('.workspace-user').click());
  await act(async () => container.querySelector('.workspace-user-dropdown-logout').click());
  expect(apiPost).toHaveBeenCalledWith('/api/logout', {});
  expect(clearToken).toHaveBeenCalledTimes(1);
  expect(container.querySelector('output').textContent).toBe('/login');
});
