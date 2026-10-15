import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Candidates from './Candidates.jsx';
import { apiGet, apiPost } from '../api.js';
import { formatApplied, interviewSummary, locationOf, pageWindow, roleOf, scoreTone, stageOf } from '../utils/talentTable.js';

const mockConfirm = jest.fn();
jest.mock('../api.js', () => ({
  TALENT_CACHE_KEY: 'talent',
  apiGet: jest.fn(),
  apiPost: jest.fn(),
  readSessionCache: () => null,
  writeSessionCache: () => {},
}));
jest.mock('../components/Layout.jsx', () => ({ children }) => <main>{children}</main>);
jest.mock('../components/EnterpriseFeedback.jsx', () => ({ toast: jest.fn(), useConfirm: () => mockConfirm, SkeletonBlock: () => null }));
jest.mock('../utils/useRoleCategories.js', () => ({ useRoleCategories: () => [] }));
jest.mock('jspdf', () => function JsPdf() {});
jest.mock('jspdf-autotable', () => ({}));
jest.mock('docx', () => ({}));
jest.mock('file-saver', () => ({ saveAs: jest.fn() }));
jest.mock('xlsx', () => ({}));

const OFFER_STEPS = [{ id: 1, name: 'Screening' }, { id: 2, name: 'Interview' }, { id: 3, name: 'Offer' }];

function candidate(i, overrides = {}) {
  return {
    id: i, name: `Person ${String(i).padStart(2, '0')}`, email: `p${i}@example.com`, status: 'Selected',
    screening_status: 'accepted', match_score: 80, client_name: 'Acme', jd_id: 20,
    job_applications: [{ jd_id: 20, jd_title: 'Backend Developer', status: 'Selected' }],
    uploaded_at: `2026-07-${String(i).padStart(2, '0')}T14:00:00`,
    structured_data: { location: 'Pune, IN' },
    ...overrides,
  };
}

const named = [
  candidate(1, { name: 'Archana Rao', hiring_process_steps: OFFER_STEPS, stage_id: 3, match_score: 85, structured_data: { location: 'San Francisco, CA' } }),
  candidate(2, { name: 'Amira Khan', hiring_stage: 'Interview Scheduled', match_score: 84, client_name: 'Globex',
    job_applications: [{ jd_id: 21, jd_title: 'Data Scientist' }, { jd_id: 22, jd_title: 'ML Engineer' }], jd_id: 21 }),
  candidate(3, { name: 'Maya Iyer', on_hold: true, match_score: 25, structured_data: {} }),
  candidate(4, { name: 'Ravi Shah', status: 'Rejected', screening_status: 'rejected', match_score: 45,
    job_applications: [{ jd_id: 20, jd_title: 'Backend Developer', status: 'Rejected' }] }),
];

let root, container, rows, interviews;
const $ = selector => container.querySelector(selector);
const $$ = selector => [...container.querySelectorAll(selector)];
const button = text => $$('button').find(b => b.textContent.trim().includes(text));
const names = () => $$('.tl-name').map(n => n.textContent);
const menuItem = text => [...document.querySelectorAll('[role="menuitem"]')].find(item => item.textContent.includes(text));

function choose(select, value) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, String(value));
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

async function render(data = named) {
  rows = data;
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  await act(async () => root.render(
    <MemoryRouter initialEntries={['/talent']}>
      <Routes>
        <Route path="/talent" element={<Candidates />} />
        <Route path="/analyze" element={<p>Upload page</p>} />
        <Route path="/talent/:candidateId" element={<p>Details page</p>} />
      </Routes>
    </MemoryRouter>,
  ));
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  mockConfirm.mockResolvedValue(true);
  const at = (days, hours) => { const d = new Date(); d.setDate(d.getDate() + days); d.setHours(hours, 0, 0, 0); return d.toISOString(); };
  // Two today (one cancelled), plus whatever earlier this month has already happened.
  interviews = [
    { id: 1, status: 'Scheduled', interview_start: at(0, 23), interview_end: at(0, 23) },
    { id: 2, status: 'Cancelled', interview_start: at(0, 23), interview_end: at(0, 23) },
  ];
  apiGet.mockImplementation(path => {
    if (path === '/api/candidates') return Promise.resolve(rows);
    if (path === '/api/clients') return Promise.resolve({ clients: [] });
    if (path.startsWith('/api/candidates/stage-options')) return Promise.resolve({ groups: [] });
    if (path === '/api/jds') return Promise.resolve([]);
    if (path === '/api/interviews') return interviews instanceof Error ? Promise.reject(interviews) : Promise.resolve({ interviews });
    return Promise.resolve({});
  });
  apiPost.mockResolvedValue({ ok: true, status: 200, data: { success: true } });
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.clearAllMocks(); });

describe('Talent table layout', () => {
  test('header, toolbar and the mockup columns without Rating', async () => {
    await render();
    expect($('h1').textContent).toBe('Today Interview List');
    expect(apiGet).toHaveBeenCalledWith('/api/interviews');
    expect($('.tl-summary').textContent).toContain('1 interview today');
    expect($('.tl-summary').textContent).toContain('done this month');
    expect($('.tl-summary').textContent).toContain('4 candidates, 2 in process');
    expect($('input[aria-label="Search candidates"]')).toBeTruthy();
    expect(button('Filters')).toBeTruthy();
    expect($('button[aria-label="More actions"]')).toBeTruthy();
    expect($('a.tl-btn-primary').getAttribute('href')).toBe('/analyze');
    expect($$('.tl-quick-filters select').map(s => s.getAttribute('aria-label'))).toEqual(['Stage', 'Role', 'Location', 'Client']);
    const headers = $$('.tl-table thead th').map(th => th.textContent.trim());
    expect(headers).toEqual(['', 'Candidate Name', 'Role', 'Stage', 'AI Score', 'Applied On', 'Location', 'Actions']);
    expect(headers).not.toContain('Rating');
  });

  test('summary degrades gracefully when interviews cannot be loaded', async () => {
    interviews = new Error('offline');
    await render();
    expect($('.tl-summary').textContent).toContain('Interview summary unavailable');
    expect($$('.tl-table tbody tr')).toHaveLength(4);
  });

  test('rows show avatar, role, coloured stage, AI score, applied date and location', async () => {
    await render();
    const row = $$('.tl-table tbody tr').find(tr => tr.textContent.includes('Archana Rao'));
    expect(row.querySelector('.tl-avatar').textContent).toBe('AR');
    expect(row.querySelector('.tl-person').getAttribute('href')).toBe('/talent/1');
    expect(row.querySelector('.tl-role').textContent).toBe('Backend Developer');
    expect(row.querySelector('.tl-stage').textContent).toBe('Offer');
    expect(row.querySelector('.tl-stage').className).toContain('tl-stage-offer');
    expect(row.querySelector('.tl-score').textContent).toBe('85%');
    expect(row.querySelector('.tl-score').className).toContain('tl-score-good');
    expect(row.querySelector('.tl-date').textContent).toBe(formatApplied(new Date('2026-07-01T14:00:00')));
    expect(row.querySelector('.tl-location').textContent).toBe('San Francisco, CA');

    const amira = $$('.tl-table tbody tr').find(tr => tr.textContent.includes('Amira Khan'));
    expect(amira.querySelector('.tl-stage').className).toContain('tl-stage-interview');
    expect(amira.querySelector('.tl-more').textContent).toBe('+1 more');
    const maya = $$('.tl-table tbody tr').find(tr => tr.textContent.includes('Maya Iyer'));
    expect(maya.querySelector('.tl-stage').textContent).toBe('On Hold');
    expect(maya.querySelector('.tl-score').className).toContain('tl-score-low');
    expect(maya.querySelector('[data-label="Location"]').textContent).toBe('—');
    const ravi = $$('.tl-table tbody tr').find(tr => tr.textContent.includes('Ravi Shah'));
    expect(ravi.querySelector('.tl-stage').className).toContain('tl-stage-rejected');
  });

  test('Applied On sorts newest first and toggles', async () => {
    await render();
    expect(names()).toEqual(['Ravi Shah', 'Maya Iyer', 'Amira Khan', 'Archana Rao']);
    await act(async () => $('.tl-sort').click());
    expect(names()).toEqual(['Archana Rao', 'Amira Khan', 'Maya Iyer', 'Ravi Shah']);
    expect($('th[aria-sort]').getAttribute('aria-sort')).toBe('ascending');
  });
});

describe('filters', () => {
  test('quick filters narrow the table and Clear Filters resets them', async () => {
    await render();
    const [stage, role, location, client] = $$('.tl-quick-filters select');
    expect([...stage.options].map(o => o.textContent)).toEqual(['Stage', 'Interview Scheduled', 'Offer', 'On Hold', 'Rejected']);
    expect([...role.options].map(o => o.textContent)).toContain('ML Engineer');
    expect(button('Clear Filters')).toBeUndefined();

    choose(stage, 'Offer');
    expect(names()).toEqual(['Archana Rao']);
    choose(stage, '');
    choose(role, 'ML Engineer');
    expect(names()).toEqual(['Amira Khan']);
    choose(role, '');
    choose(location, 'San Francisco, CA');
    expect(names()).toEqual(['Archana Rao']);
    choose(location, '');
    choose(client, 'Globex');
    expect(names()).toEqual(['Amira Khan']);

    await act(async () => button('Clear Filters').click());
    expect(names()).toHaveLength(4);
    expect(client.value).toBe('');
  });

  test('search filters by name, client or role', async () => {
    await render();
    const search = $('input[aria-label="Search candidates"]');
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(search, 'globex');
      search.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(names()).toEqual(['Amira Khan']);
    expect(button('Clear Filters')).toBeTruthy();
  });

  test('a filter with no matches shows the empty state', async () => {
    await render();
    const search = $('input[aria-label="Search candidates"]');
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(search, 'nobody');
      search.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(container.textContent).toContain('No Matching Candidates');
    expect($('.tl-footer')).toBeNull();
  });

  test('the Filters button still opens the advanced filter panel', async () => {
    await render();
    await act(async () => button('Filters').click());
    expect($('.candidates-filters-panel').textContent).toContain('Requirement');
    expect($('.candidates-filters-panel').textContent).toContain('Interview Date');
  });
});

describe('pagination', () => {
  const many = Array.from({ length: 25 }, (_, i) => candidate(i + 1));

  test('shows 20 rows per page with page controls', async () => {
    await render(many);
    expect($$('.tl-table tbody tr')).toHaveLength(20);
    expect($('.tl-rows').textContent).toContain('1-20 of 25 Entries');
    expect($('.tl-pages').textContent).toContain('of 2');
    expect(button('1').getAttribute('aria-current')).toBe('page');
    expect($('button[aria-label="Previous page"]').disabled).toBe(true);
    await act(async () => $('button[aria-label="Next page"]').click());
    expect($$('.tl-table tbody tr')).toHaveLength(5);
    expect($('.tl-rows').textContent).toContain('21-25 of 25 Entries');
    expect($('button[aria-label="Next page"]').disabled).toBe(true);
  });

  test('rows per page can be changed', async () => {
    await render(many);
    choose($('select[aria-label="Rows per page"]'), 10);
    expect($$('.tl-table tbody tr')).toHaveLength(10);
    expect($('.tl-pages').textContent).toContain('of 3');
  });
});

describe('actions', () => {
  test('row menu renders outside the animated table row so it is positioned against the viewport', async () => {
    await render();
    const trigger = $('button[aria-label="Actions for Archana Rao"]');
    await act(async () => trigger.click());
    const menu = document.querySelector('.kebab-dropdown');
    expect(menu.parentElement).toBe(document.body);
    expect(trigger.closest('tr').contains(menu)).toBe(false);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    // Pressing inside the portalled menu must not count as an outside click.
    await act(async () => menuItem('Send Assessment').dispatchEvent(new MouseEvent('mousedown', { bubbles: true })));
    expect(document.querySelector('.kebab-dropdown')).toBeTruthy();
    await act(async () => document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })));
    expect(document.querySelector('.kebab-dropdown')).toBeNull();
  });

  test('row menu: All Details, Send Assessment and Remove', async () => {
    await render();
    await act(async () => $('button[aria-label="Actions for Archana Rao"]').click());
    expect(menuItem('All Details').getAttribute('href')).toBe('/talent/1');
    await act(async () => menuItem('Send Assessment').click());
    expect(container.textContent).toContain('Generate Assessment');
    await act(async () => button('Cancel').click());

    await act(async () => $('button[aria-label="Actions for Archana Rao"]').click());
    await act(async () => menuItem('Remove').click());
    expect(mockConfirm).toHaveBeenCalledWith(expect.objectContaining({ title: 'Remove candidate' }));
    expect(apiPost).toHaveBeenCalledWith('/api/candidates/1/delete', { confirmed: true });
    expect(names()).not.toContain('Archana Rao');
  });

  test('selection enables bulk delete from the bar and the page menu', async () => {
    await render();
    await act(async () => $('button[aria-label="More actions"]').click());
    expect(menuItem('Delete selected').getAttribute('aria-disabled')).toBe('true');
    await act(async () => $('button[aria-label="More actions"]').click());

    await act(async () => $('input[aria-label="Select Amira Khan"]').click());
    await act(async () => $('input[aria-label="Select Ravi Shah"]').click());
    expect($('.tl-selection-bar').textContent).toContain('2 selected');
    await act(async () => $('button[aria-label="More actions"]').click());
    await act(async () => menuItem('Delete selected (2)').click());
    expect(mockConfirm).toHaveBeenCalledWith(expect.objectContaining({ title: 'Remove candidates' }));
    expect(apiPost).toHaveBeenCalledTimes(2);
    expect(names()).toEqual(['Maya Iyer', 'Archana Rao']);
    expect($('.tl-selection-bar')).toBeNull();
  });

  test('header checkbox selects the current page only', async () => {
    await render(Array.from({ length: 25 }, (_, i) => candidate(i + 1)));
    await act(async () => $('input[aria-label="Select all candidates on this page"]').click());
    expect($('.tl-selection-bar').textContent).toContain('20 selected');
  });

  test('page menu opens the report generator', async () => {
    await render();
    await act(async () => $('button[aria-label="More actions"]').click());
    await act(async () => menuItem('Generate report').click());
    expect(container.textContent).toContain('Report covers the 4 candidates currently shown');
  });

  test('empty repository keeps the upload call to action', async () => {
    await render([]);
    expect(container.textContent).toContain('No Candidates Yet');
    expect($('.tl-table')).toBeNull();
  });
});

describe('talentTable helpers', () => {
  test('stage kinds map to the mockup colours', () => {
    expect(stageOf(named[0]).kind).toBe('offer');
    expect(stageOf(named[1]).kind).toBe('interview');
    expect(stageOf(named[2])).toEqual(expect.objectContaining({ kind: 'hold', label: 'On Hold' }));
    expect(stageOf(named[3]).kind).toBe('rejected');
    expect(stageOf(candidate(9)).kind).toBe('screening');
    expect(stageOf(candidate(9, { hiring_process_steps: [{ id: 1, name: 'Hired' }], stage_id: 1 })).kind).toBe('hired');
  });

  test('interview summary counts today and completed interviews this month only', () => {
    const now = new Date(2026, 9, 15, 12, 0);
    const iso = (d, h) => new Date(2026, 9, d, h, 0).toISOString();
    const summary = interviewSummary([
      { status: 'Scheduled', interview_start: iso(15, 9), interview_end: iso(15, 10) },
      { status: 'Scheduled', interview_start: iso(15, 16), interview_end: iso(15, 17) },
      { status: 'Client Interview Pending', interview_start: iso(3, 9), interview_end: iso(3, 10) },
      { status: 'Cancelled', interview_start: iso(15, 11), interview_end: iso(15, 12) },
      { status: 'No Show', interview_start: iso(5, 9), interview_end: iso(5, 10) },
      { status: 'Scheduled', attendance_status: 'no_show', interview_start: iso(6, 9), interview_end: iso(6, 10) },
      { status: 'Scheduled', interview_start: new Date(2026, 8, 30, 9).toISOString(), interview_end: new Date(2026, 8, 30, 10).toISOString() },
      { status: 'Scheduled', interview_start: 'not a date' },
    ], now);
    expect(summary).toEqual({ today: 2, doneThisMonth: 2 });
    expect(interviewSummary(undefined, now)).toEqual({ today: 0, doneThisMonth: 0 });
  });

  test('role, location, score tone and page window', () => {
    expect(roleOf(named[1])).toEqual({ primary: 'Data Scientist', others: ['ML Engineer'] });
    expect(locationOf({ structured_data: { location: { city: 'Austin', state: 'TX' } } })).toBe('Austin, TX');
    expect([scoreTone(90), scoreTone(60), scoreTone(10), scoreTone(null)]).toEqual(['good', 'mid', 'low', 'muted']);
    expect(pageWindow(1, 100)).toEqual([1, 2, 3, 4, 5]);
    expect(pageWindow(50, 100)).toEqual([48, 49, 50, 51, 52]);
    expect(pageWindow(100, 100)).toEqual([96, 97, 98, 99, 100]);
    expect(pageWindow(1, 2)).toEqual([1, 2]);
    expect(formatApplied(null)).toBe('—');
  });
});
