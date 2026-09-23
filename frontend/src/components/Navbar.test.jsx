import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, useLocation } from 'react-router-dom';
import Navbar from './Navbar.jsx';
import { AppearanceProvider } from './AppearanceProvider.jsx';
import { FrontendPolishProvider } from './FrontendPolish.jsx';
import { apiPost, clearToken } from '../api.js';

jest.mock('../api.js', () => ({ apiPost: jest.fn(), clearToken: jest.fn() }));

let container;
let root;
function LocationProbe() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}
function renderWorkspace(path = '/welcome', showNavigation = true) {
  act(() => root.render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppearanceProvider>
        <FrontendPolishProvider>
          {showNavigation && <Navbar />}
          <LocationProbe />
        </FrontendPolishProvider>
      </AppearanceProvider>
    </MemoryRouter>
  ));
}
const click = element => act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })));

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  localStorage.setItem('recruitment_assist_user', JSON.stringify({ role: 'admin' }));
  document.body.className = '';
  jest.clearAllMocks();
  window.matchMedia = jest.fn(() => ({ matches: true }));
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

test('keeps all existing navigation labels, order, destinations, and the welcome logo link', () => {
  renderWorkspace('/jobs/123');
  const links = Array.from(container.querySelectorAll('.workspace-links a'));
  expect(links.map(link => [link.textContent, link.getAttribute('href')])).toEqual([
    ['Dashboard', '/dashboard'], ['Jobs', '/jobs'], ['Analyze', '/analyze'],
    ['Talent', '/talent'], ['Clients', '/clients'], ['Vendors', '/vendors'],
    ['User Management', '/admin/users'], ['Pipeline', '/hiring-pipeline'], ['Reports', '/insights'],
  ]);
  expect(container.querySelector('[aria-current="page"]').textContent).toBe('Jobs');
  expect(container.querySelector('.workspace-brand').getAttribute('href')).toBe('/welcome');
  expect(container.querySelector('.workspace-account a').getAttribute('href')).toBe('/profile');
  expect(container.querySelector('.workspace-account button').textContent).toBe('Exit');
});

test('mobile navigation expands, follows the existing route, and closes after selection', () => {
  renderWorkspace();
  const toggle = container.querySelector('.workspace-menu-toggle');
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  click(toggle);
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
  expect(container.querySelector('#workspace-navigation').classList.contains('workspace-sidebar-open')).toBe(true);
  click(container.querySelector('a[href="/talent"]'));
  expect(container.querySelector('output').textContent).toBe('/talent');
  expect(container.querySelector('.workspace-topbar')).toBeNull();
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  expect(document.activeElement).toBe(toggle);
});

test('Escape closes mobile navigation and returns keyboard focus', () => {
  renderWorkspace();
  const toggle = container.querySelector('.workspace-menu-toggle');
  click(toggle);
  const link = container.querySelector('a[href="/jobs"]');
  link.focus();
  act(() => link.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  expect(document.activeElement).toBe(toggle);
});

test('fresh public pages receive the warm palette without requiring navigation to mount', () => {
  renderWorkspace('/assessment/example', false);
  expect(document.body.classList.contains('theme-shimento')).toBe(true);
  expect(localStorage.getItem('color_theme_version')).toBe('ember-v1');
  expect(localStorage.getItem('color_theme')).toBe('warm');
});

test('removes the header and its appearance controls', () => {
  renderWorkspace();
  expect(container.querySelector('header')).toBeNull();
  expect(container.querySelector('.workspace-preferences')).toBeNull();
  expect(container.querySelector('[aria-label="Use current blue theme"]')).toBeNull();
  expect(container.querySelector('[aria-label="Disable interface polish"]')).toBeNull();
});

test.each([false, true])('Exit clears the session and returns to login (API failure: %s)', async failure => {
  apiPost.mockImplementation(() => failure ? Promise.reject(new Error('Offline')) : Promise.resolve({ ok: true }));
  renderWorkspace();
  await act(async () => container.querySelector('.workspace-account button').click());
  expect(apiPost).toHaveBeenCalledWith('/api/logout', {});
  expect(clearToken).toHaveBeenCalledTimes(1);
  expect(container.querySelector('output').textContent).toBe('/login');
});
