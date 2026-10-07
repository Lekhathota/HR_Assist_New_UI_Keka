import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { HireRedirect, HireTabs } from './HireNav.jsx';

let container;
let root;
function LocationProbe() {
  return <output>{useLocation().pathname}</output>;
}
function render(path, role = 'admin') {
  localStorage.setItem('recruitment_assist_user', JSON.stringify({ role }));
  act(() => root.render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/hire" element={<HireRedirect />} />
        <Route path="*" element={<><HireTabs /><LocationProbe /></>} />
      </Routes>
    </MemoryRouter>
  ));
}
const tabs = () => Array.from(container.querySelectorAll('.hire-tab')).map(tab => [tab.textContent, tab.getAttribute('href')]);

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  localStorage.clear();
});

test('opening Hire lands on Jobs', () => {
  render('/hire');
  expect(container.querySelector('output').textContent).toBe('/jobs');
});

test('Hire falls back to the first page the role may open', () => {
  render('/hire', 'hr');
  expect(container.querySelector('output').textContent).toBe('/hiring-pipeline');
});

test('shows the Hire tabs in order and marks the current page, including detail pages', () => {
  render('/talent/42');
  expect(tabs()).toEqual([['Jobs', '/jobs'], ['Analyze', '/analyze'], ['Talent', '/talent'], ['Hiring Pipeline', '/hiring-pipeline']]);
  expect(container.querySelector('.hire-tab[aria-current="page"]').textContent).toBe('Talent');
});

test('clicking a tab opens that page', () => {
  render('/jobs');
  act(() => container.querySelector('a[href="/analyze"]').dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })));
  expect(container.querySelector('output').textContent).toBe('/analyze');
  expect(container.querySelector('.hire-tab[aria-current="page"]').textContent).toBe('Analyze');
});

test('only lists tabs the role can access', () => {
  render('/hiring-pipeline', 'managers_consultant');
  expect(tabs()).toEqual([['Hiring Pipeline', '/hiring-pipeline']]);
});

test('stays off pages outside Hire', () => {
  render('/clients');
  expect(container.querySelector('.hire-tabs')).toBeNull();
});
