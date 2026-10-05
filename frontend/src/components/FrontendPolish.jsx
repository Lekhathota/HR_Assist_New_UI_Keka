import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getCurrentRole, roleCanAccess } from '../roleAccess.js';

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

export function CommandPalette() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');

  const commands = useMemo(
    () => [
      { label: 'Open Home', hint: 'Recruiting overview', icon: 'fas fa-house', path: '/welcome' },
      { label: 'Open Jobs', hint: 'Job descriptions', icon: 'fas fa-briefcase', path: '/jobs' },
      { label: 'Create Job Description', hint: 'Upload a JD', icon: 'fas fa-file-circle-plus', path: '/jobs/create' },
      { label: 'Analyze Resumes', hint: 'Screen candidates', icon: 'fas fa-code-compare', path: '/analyze' },
      { label: 'Open Talent', hint: 'Candidate repository', icon: 'fas fa-users', path: '/talent' },
      { label: 'Open Clients', hint: 'Client accounts', icon: 'fas fa-building', path: '/clients' },
      { label: 'Open Insights', hint: 'Reports and analytics', icon: 'fas fa-chart-bar', path: '/insights' },
      { label: 'Open Profile', hint: 'Account settings', icon: 'fas fa-user-circle', path: '/profile' },
    ],
    []
  );

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

  if (!open) return null;

  const needle = query.trim().toLowerCase();
  const visible = commands.filter((cmd) => roleCanAccess(getCurrentRole(), cmd.path) && `${cmd.label} ${cmd.hint}`.toLowerCase().includes(needle));
  const run = (path) => {
    setOpen(false);
    setQuery('');
    navigate(path);
  };

  return (
    <div className="command-palette-backdrop" role="presentation" onMouseDown={() => setOpen(false)}>
      <div className="command-palette" role="dialog" aria-label="Command palette" onMouseDown={(e) => e.stopPropagation()}>
        <div className="command-palette-input">
          <i className="fas fa-search"></i>
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setOpen(false);
              if (e.key === 'Enter' && visible[0]) run(visible[0].path);
            }}
            placeholder="Search pages and actions..."
          />
          <kbd>Esc</kbd>
        </div>
        <div className="command-palette-list">
          {visible.map((cmd) => (
            <button key={cmd.label} type="button" onClick={() => run(cmd.path)}>
              <i className={cmd.icon}></i>
              <span>
                <strong>{cmd.label}</strong>
                <small>{cmd.hint}</small>
              </span>
            </button>
          ))}
          {visible.length === 0 && <div className="command-palette-empty">No matching action</div>}
        </div>
      </div>
    </div>
  );
}
