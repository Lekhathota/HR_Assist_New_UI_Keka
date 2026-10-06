import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, useLocation } from 'react-router-dom';
import Navbar from './Navbar.jsx';
import { AppearanceProvider } from './AppearanceProvider.jsx';
import { FrontendPolishProvider } from './FrontendPolish.jsx';
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

test('groups Jobs, Talent, Analyze and Hiring Pipeline under Hire and keeps the other links', () => {
  renderWorkspace('/jobs/123');
  const links = Array.from(container.querySelectorAll('.workspace-links a'));
  expect(links.map(link => [link.textContent, link.getAttribute('href')])).toEqual([
    ['Home', '/welcome'], ['Hire', '/hire'], ['Clients', '/clients'], ['Vendors', '/vendors'], ['Reports', '/insights'],
  ]);
  expect(container.querySelector('[aria-current="page"]').textContent).toBe('Hire');
  expect(container.querySelector('.workspace-brand').getAttribute('href')).toBe('/welcome');
  expect(container.querySelector('.workspace-account a[href="/profile"]')).toBeNull();
  expect(container.querySelector('.workspace-account button')).toBeNull();
});

test('mobile navigation expands, follows the existing route, and closes after selection', () => {
  renderWorkspace();
  const toggle = container.querySelector('.workspace-menu-toggle');
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  click(toggle);
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
  expect(container.querySelector('#workspace-navigation').classList.contains('workspace-sidebar-open')).toBe(true);
  click(container.querySelector('a[href="/clients"]'));
  expect(container.querySelector('output').textContent).toBe('/clients');
  expect(container.querySelector('.workspace-topbar')).toBeNull();
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  expect(document.activeElement).toBe(toggle);
});

test('Escape closes mobile navigation and returns keyboard focus', () => {
  renderWorkspace();
  const toggle = container.querySelector('.workspace-menu-toggle');
  click(toggle);
  const link = container.querySelector('a[href="/hire"]');
  link.focus();
  act(() => link.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  expect(document.activeElement).toBe(toggle);
});

test.each(['/hire', '/talent/5', '/analyze', '/hiring-pipeline', '/job-details.html'])('Hire stays active on %s', path => {
  renderWorkspace(path);
  expect(container.querySelector('.workspace-links [aria-current="page"]').textContent).toBe('Hire');
});

test('Hire is hidden for roles that cannot open any Hire page', () => {
  localStorage.setItem('recruitment_assist_user', JSON.stringify({ role: 'finance' }));
  renderWorkspace('/insights');
  expect(container.querySelector('a[href="/hire"]')).toBeNull();
});

test('fresh public pages receive the shared palette without navigation', () => {
  renderWorkspace('/assessment/example', false);
  expect(document.body.classList.contains('theme-shimento')).toBe(true);
});

test('removes the header and its appearance controls', () => {
  renderWorkspace();
  expect(container.querySelector('header')).toBeNull();
  expect(container.querySelector('.workspace-preferences')).toBeNull();
  expect(container.querySelector('[aria-label="Use current blue theme"]')).toBeNull();
  expect(container.querySelector('[aria-label="Disable interface polish"]')).toBeNull();
});
