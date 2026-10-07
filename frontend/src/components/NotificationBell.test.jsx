import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, useLocation } from 'react-router-dom';
import NotificationBell, { timeAgo } from './NotificationBell.jsx';
import { apiGet, apiPost, getToken } from '../api.js';

jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiPost: jest.fn(), getToken: jest.fn() }));

const feed = {
  unread_count: 1,
  notifications: [
    { id: 2, type: 'jd_requirement_fulfilled', title: 'Requirement fulfilled', message: 'Data Engineer has 2 of 2 required candidates selected, so the JD has been closed.', jd_id: 14, read: false, created_at: new Date().toISOString() },
    { id: 1, type: 'jd_requirement_fulfilled', title: 'Requirement fulfilled', message: 'QA closed.', jd_id: 9, read: true, created_at: '2026-01-01T00:00:00Z' },
  ],
};

let container, root;
const $ = selector => container.querySelector(selector);
function LocationProbe() { return <output>{useLocation().pathname}</output>; }
const click = async element => act(async () => element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })));

async function render() {
  await act(async () => root.render(
    <MemoryRouter initialEntries={['/welcome']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <NotificationBell /><LocationProbe />
    </MemoryRouter>
  ));
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  getToken.mockReturnValue('token');
  apiGet.mockResolvedValue(feed);
  apiPost.mockResolvedValue({ ok: true, data: { success: true } });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.clearAllMocks(); });

test('shows the unread count on the bell and lists notifications when opened', async () => {
  await render();
  expect(apiGet).toHaveBeenCalledWith('/api/notifications');
  expect($('.workspace-notification-badge').textContent).toBe('1');
  expect($('.workspace-notification').getAttribute('aria-label')).toBe('Notifications, 1 unread');
  await click($('.workspace-notification'));
  const items = container.querySelectorAll('.workspace-notification-item');
  expect(items).toHaveLength(2);
  expect(items[0].classList.contains('unread')).toBe(true);
  expect(items[0].textContent).toContain('so the JD has been closed');
  expect(items[1].classList.contains('unread')).toBe(false);
});

test('opening a notification marks it read and goes to the job', async () => {
  await render();
  await click($('.workspace-notification'));
  await click(container.querySelector('.workspace-notification-item'));
  expect(apiPost).toHaveBeenCalledWith('/api/notifications/read', { ids: [2] });
  expect($('output').textContent).toBe('/jobs/14');
  expect($('.workspace-notification-badge')).toBeNull();
});

test('mark all as read clears the badge', async () => {
  await render();
  await click($('.workspace-notification'));
  await click($('.workspace-notification-head button'));
  expect(apiPost).toHaveBeenCalledWith('/api/notifications/read', {});
  expect($('.workspace-notification-badge')).toBeNull();
  expect(container.querySelector('.workspace-notification-item.unread')).toBeNull();
});

test('shows an empty state and stays hidden when signed out', async () => {
  apiGet.mockResolvedValue({ unread_count: 0, notifications: [] });
  await render();
  await click($('.workspace-notification'));
  expect($('.workspace-notification-empty').textContent).toContain("You're all caught up.");
  act(() => root.unmount());
  root = createRoot(container);
  getToken.mockReturnValue('');
  await render();
  expect($('.workspace-notification')).toBeNull();
});

test('opens the notification link and shows a kind-specific icon', async () => {
  apiGet.mockResolvedValue({ unread_count: 1, notifications: [
    { id: 5, type: 'resume_uploaded', title: '3 resumes uploaded', message: '3 candidates added to Talent for QA by lekha.', jd_id: 2, link: '/talent', read: false, created_at: new Date().toISOString() },
  ] });
  await render();
  await click($('.workspace-notification'));
  expect($('.workspace-notification-icon').className).toContain('tone-accent');
  expect($('.workspace-notification-icon i').className).toContain('fa-file-arrow-up');
  await click(container.querySelector('.workspace-notification-item'));
  expect($('output').textContent).toBe('/talent');
});

test('Clear all empties the panel and the badge', async () => {
  await render();
  await click($('.workspace-notification'));
  await click($('.workspace-notification-clear'));
  expect(apiPost).toHaveBeenCalledWith('/api/notifications/clear', {});
  expect(container.querySelector('.workspace-notification-item')).toBeNull();
  expect($('.workspace-notification-badge')).toBeNull();
  expect($('.workspace-notification-empty').textContent).toContain("You're all caught up.");
});

test('Clear all restores the list if the server fails', async () => {
  apiPost.mockResolvedValueOnce({ ok: false, data: {} });
  await render();
  await click($('.workspace-notification'));
  await click($('.workspace-notification-clear'));
  expect(container.querySelectorAll('.workspace-notification-item').length).toBeGreaterThan(0);
});

test('formats relative times', () => {
  const now = Date.parse('2026-10-06T12:00:00Z');
  expect(timeAgo('2026-10-06T11:59:30Z', now)).toBe('Just now');
  expect(timeAgo('2026-10-06T11:55:00Z', now)).toBe('5 min ago');
  expect(timeAgo('2026-10-06T10:00:00Z', now)).toBe('2 hours ago');
  expect(timeAgo('2026-10-04T12:00:00Z', now)).toBe('2 days ago');
});
