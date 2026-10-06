import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getCurrentRole, roleCanAccess } from '../roleAccess.js';
import { apiGet } from '../api.js';

const PolishContext = createContext({ enabled: false, setEnabled: () => {}, toggle: () => {} });
const STORAGE_KEY = 'frontend_motion_polish';

export function FrontendPolishProvider({ children }) {
  const [enabled, setEnabledState] = useState(() => localStorage.getItem(STORAGE_KEY) === 'on');

  const setEnabled = (next) => {
    const value = Boolean(next);
    localStorage.setItem(STORAGE_KEY, value ? 'on' : 'off');
    setEnabledState(value);
  };

  useEffect(() => {
    document.body.classList.toggle('frontend-polish', enabled);
    return () => document.body.classList.remove('frontend-polish');
  }, [enabled]);

  const value = useMemo(() => ({ enabled, setEnabled, toggle: () => setEnabled(!enabled) }), [enabled]);

  return <PolishContext.Provider value={value}>{children}</PolishContext.Provider>;
}

export function useFrontendPolish() {
  return useContext(PolishContext);
}

export function AnimatedNumber({ value, alwaysAnimate = false, from = 0, duration = 720 }) {
  const { enabled } = useFrontendPolish();
  const numeric = Number(value || 0);
  const shouldAnimate = enabled || alwaysAnimate;
  const [shown, setShown] = useState(shouldAnimate ? Number(from || 0) : numeric);

  useEffect(() => {
    if (!shouldAnimate) {
      setShown(numeric);
      return undefined;
    }
    const start = Number(shown || 0);
    const delta = numeric - start;
    if (!delta) return undefined;

    const startTime = performance.now();
    let frame = 0;
    const tick = (now) => {
      const progress = Math.min(1, (now - startTime) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      setShown(Math.round(start + delta * eased));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [shouldAnimate, numeric, duration]); // eslint-disable-line react-hooks/exhaustive-deps

  return <span>{shown}</span>;
}

const PAGE_COMMANDS = [
  { label: 'Open Home', hint: 'Recruiting overview', icon: 'fas fa-house', path: '/welcome' },
  { label: 'Open Jobs', hint: 'Job descriptions', icon: 'fas fa-briefcase', path: '/jobs' },
  { label: 'Create Job Description', hint: 'Upload a JD', icon: 'fas fa-file-circle-plus', path: '/jobs/create' },
  { label: 'Analyze Resumes', hint: 'Screen candidates', icon: 'fas fa-wand-magic-sparkles', path: '/analyze' },
  { label: 'Open Talent', hint: 'Candidate repository', icon: 'fas fa-users', path: '/talent' },
  { label: 'Open Hiring Pipeline', hint: 'Assessments and interviews', icon: 'fas fa-diagram-project', path: '/hiring-pipeline' },
  { label: 'Open Clients', hint: 'Client accounts', icon: 'fas fa-building', path: '/clients' },
  { label: 'Open Vendors', hint: 'Recruitment partners', icon: 'fas fa-handshake', path: '/vendors' },
  { label: 'Open Reports', hint: 'Reports and analytics', icon: 'fas fa-chart-line', path: '/insights' },
  { label: 'Open Profile', hint: 'Account settings', icon: 'fas fa-user-circle', path: '/profile' },
];

const join = (...parts) => parts.filter(Boolean).join(' · ');

// Turns /api/search results into palette entries.
export function searchResultItems(data) {
  if (!data) return [];
  return [
    ...(data.jobs || []).map(job => ({
      group: 'Jobs', key: `job-${job.id}`, icon: 'fas fa-briefcase', path: `/jobs/${job.id}`,
      label: job.title || `JD #${job.id}`, hint: join(job.job_code, job.client_name, job.location, job.status),
    })),
    ...(data.candidates || []).map(c => ({
      group: 'Candidates', key: `candidate-${c.id}`, icon: 'fas fa-user', path: `/talent/${c.id}`,
      label: c.name || `Candidate #${c.id}`, hint: join(c.jd_title, c.primary_category, c.email),
    })),
    ...(data.clients || []).map(c => ({
      group: 'Clients', key: `client-${c.id}`, icon: 'fas fa-building', path: `/clients?client=${c.id}`,
      label: c.name || `Client #${c.id}`, hint: join(c.client_account_id, c.industry),
    })),
    ...(data.vendors || []).map(v => ({
      group: 'Vendors', key: `vendor-${v.id}`, icon: 'fas fa-handshake',
      path: `/vendors?search=${encodeURIComponent(v.company_name || v.vendor_name || '')}`,
      label: v.company_name || v.vendor_name || `Vendor #${v.id}`, hint: join(v.contact_person, v.status),
    })),
  ];
}

export function CommandPalette() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [active, setActive] = useState(0);
  const listRef = useRef(null);

  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener('open-command-palette', onOpen);
    const onKeyDown = (event) => {
      const isPaletteChord = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k';
      if (!isPaletteChord) return;
      event.preventDefault();
      setOpen(true);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => { window.removeEventListener('keydown', onKeyDown); window.removeEventListener('open-command-palette', onOpen); };
  }, []);

  // Live search for JDs, candidates, clients and vendors (debounced).
  const needle = query.trim();
  useEffect(() => {
    if (!open || needle.length < 2) { setResults(null); setSearching(false); setSearchError(''); return undefined; }
    let cancelled = false;
    setSearching(true);
    const timer = setTimeout(() => {
      apiGet(`/api/search?q=${encodeURIComponent(needle)}`)
        .then(data => { if (!cancelled) { setResults(data); setSearchError(''); } })
        .catch(() => { if (!cancelled) { setResults(null); setSearchError('Search is unavailable right now.'); } })
        .finally(() => { if (!cancelled) setSearching(false); });
    }, 220);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [open, needle]);

  const items = useMemo(() => {
    const lower = needle.toLowerCase();
    const pages = PAGE_COMMANDS
      .filter(cmd => roleCanAccess(getCurrentRole(), cmd.path) && `${cmd.label} ${cmd.hint}`.toLowerCase().includes(lower))
      .map(cmd => ({ ...cmd, group: 'Pages', key: `page-${cmd.path}` }));
    return needle.length >= 2 ? [...searchResultItems(results), ...pages] : pages;
  }, [needle, results]);

  useEffect(() => { setActive(0); }, [needle, results]);
  useEffect(() => {
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: 'nearest' });
  }, [active]);

  if (!open) return null;

  const close = () => { setOpen(false); setQuery(''); setResults(null); };
  const run = (item) => { close(); navigate(item.path); };
  const onKeyDown = (event) => {
    if (event.key === 'Escape') close();
    else if (event.key === 'ArrowDown') { event.preventDefault(); setActive(i => Math.min(i + 1, items.length - 1)); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); setActive(i => Math.max(i - 1, 0)); }
    else if (event.key === 'Enter' && items[active]) { event.preventDefault(); run(items[active]); }
  };

  let lastGroup = '';
  return (
    <div className="command-palette-backdrop" role="presentation" onMouseDown={close}>
      <div className="command-palette" role="dialog" aria-label="Search" onMouseDown={(e) => e.stopPropagation()}>
        <div className="command-palette-input">
          <i className={searching ? 'fas fa-spinner fa-spin' : 'fas fa-search'} aria-hidden="true"></i>
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search jobs, candidates, clients, vendors or pages..."
            aria-label="Search jobs, candidates, clients, vendors or pages"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-palette-results"
            aria-activedescendant={items[active] ? `cp-${items[active].key}` : undefined}
          />
          <kbd>Esc</kbd>
        </div>
        <div className="command-palette-list" id="command-palette-results" role="listbox" ref={listRef}>
          {items.map((item, index) => {
            const heading = item.group !== lastGroup ? item.group : null;
            lastGroup = item.group;
            return (
              <React.Fragment key={item.key}>
                {heading && <div className="command-palette-group" role="presentation">{heading}</div>}
                <button type="button" id={`cp-${item.key}`} role="option" aria-selected={index === active}
                  className={index === active ? 'active' : ''} onMouseEnter={() => setActive(index)} onClick={() => run(item)}>
                  <i className={item.icon} aria-hidden="true"></i>
                  <span>
                    <strong>{item.label}</strong>
                    {item.hint && <small>{item.hint}</small>}
                  </span>
                </button>
              </React.Fragment>
            );
          })}
          {searchError && <div className="command-palette-empty" role="alert">{searchError}</div>}
          {!items.length && !searching && !searchError && (
            <div className="command-palette-empty">
              {needle.length >= 2 ? `No jobs, candidates or pages match “${needle}”.` : 'No matching page'}
            </div>
          )}
          {needle.length < 2 && <div className="command-palette-tip">Type 2 or more letters to search jobs, candidates, clients and vendors.</div>}
        </div>
      </div>
    </div>
  );
}
