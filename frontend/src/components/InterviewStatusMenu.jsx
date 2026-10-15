import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';

// Candidate status options shown on an interview row, in display order.
export const INTERVIEW_STATUS_OPTIONS = [
  { value: 'selected', label: 'Selected', icon: 'fa-circle-check', tone: 'good' },
  { value: 'rejected', label: 'Rejected', icon: 'fa-circle-xmark', tone: 'bad' },
  { value: 'interested', label: 'Interested', icon: 'fa-thumbs-up', tone: 'good' },
  { value: 'not_interested', label: 'Not Interested', icon: 'fa-thumbs-down', tone: 'bad' },
  { value: 'follow_up', label: 'Follow-up', icon: 'fa-reply', tone: 'warn' },
  { value: 'awaiting_reply', label: 'Outreach Sent · Awaiting Reply', icon: 'fa-paper-plane', tone: 'info' },
  { value: 'rescheduled', label: 'Rescheduled', icon: 'fa-calendar-check', tone: 'info' },
  { value: 'cancelled', label: 'Cancelled', icon: 'fa-ban', tone: 'muted' },
  { value: 'no_show', label: 'No Show', icon: 'fa-user-slash', tone: 'warn' },
  { value: 'pending_review', label: 'Pending Review', icon: 'fa-hourglass-half', tone: 'muted' },
];

const MENU_WIDTH = 260;
const MENU_GAP = 4;

// value: current status (or null); disabledReasons: { [value]: reason } for options that cannot be chosen.
function InterviewStatusMenu({ value, onChange, busy = false, disabled = false, disabledTitle = '', disabledReasons = {}, error = '', label = 'Candidate status' }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState(null);
  const container = useRef(null);
  const trigger = useRef(null);
  const menu = useRef(null);
  const current = INTERVIEW_STATUS_OPTIONS.find(option => option.value === value) || null;

  const close = (refocus = false) => {
    setOpen(false);
    if (refocus) trigger.current?.focus();
  };

  // The row container clips overflow, so the menu is fixed to the viewport and flips up near the bottom.
  useLayoutEffect(() => {
    if (!open || !trigger.current) return;
    const rect = trigger.current.getBoundingClientRect();
    const height = menu.current?.offsetHeight || 0;
    const below = window.innerHeight - rect.bottom;
    const top = height && below < height + MENU_GAP && rect.top > below ? rect.top - height - MENU_GAP : rect.bottom + MENU_GAP;
    const left = Math.max(8, Math.min(rect.right - MENU_WIDTH, window.innerWidth - MENU_WIDTH - 8));
    setPosition({ top, left });
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const items = () => [...(menu.current?.querySelectorAll('[role="menuitemradio"]:not([aria-disabled="true"])') || [])];
    (items().find(item => item.getAttribute('aria-checked') === 'true') || items()[0])?.focus();
    const onPointerDown = (event) => {
      if (!container.current?.contains(event.target)) close();
    };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); close(true); return; }
      if (event.key === 'Tab') { close(); return; }
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
      const list = items();
      if (!list.length) return;
      event.preventDefault();
      const index = list.indexOf(document.activeElement);
      const next = event.key === 'Home' ? 0
        : event.key === 'End' ? list.length - 1
          : event.key === 'ArrowDown' ? (index + 1) % list.length
            : (index - 1 + list.length) % list.length;
      list[next].focus();
    };
    const onViewportChange = () => close();
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    window.addEventListener('resize', onViewportChange);
    window.addEventListener('scroll', onViewportChange, true);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('resize', onViewportChange);
      window.removeEventListener('scroll', onViewportChange, true);
    };
  }, [open]);

  const choose = (option) => {
    if (disabledReasons[option.value]) return;
    close(true);
    onChange(option.value);
  };

  const triggerTone = current ? current.tone : 'muted';
  const triggerIcon = busy ? 'fa-spinner fa-spin' : (current ? current.icon : 'fa-circle-dot');

  return (
    <div className="hp-status-menu" ref={container}>
      <button ref={trigger} type="button" className={`hp-status-trigger ${triggerTone}${current ? '' : ' is-empty'}`}
        aria-haspopup="menu" aria-expanded={open} aria-label={`${label}: ${current ? current.label : 'not set'}`}
        aria-busy={busy || undefined} disabled={disabled || busy} title={disabled ? disabledTitle : (current ? current.label : 'Set status')}
        onClick={() => setOpen(prev => !prev)}>
        <i className={`fas ${triggerIcon}`} aria-hidden="true"></i>
        <span className="hp-status-trigger-label">{busy ? 'Saving…' : (current ? current.label : 'Set status')}</span>
        <i className={`fas fa-chevron-${open ? 'up' : 'down'} hp-status-caret`} aria-hidden="true"></i>
      </button>
      {open && (
        <div ref={menu} className="hp-status-dropdown" role="menu" aria-label={label}
          style={position ? { top: position.top, left: position.left, width: MENU_WIDTH } : { visibility: 'hidden', width: MENU_WIDTH }}>
          {INTERVIEW_STATUS_OPTIONS.map(option => {
            const reason = disabledReasons[option.value];
            const checked = option.value === value;
            return (
              <button key={option.value} type="button" role="menuitemradio" aria-checked={checked}
                aria-disabled={reason ? 'true' : undefined} tabIndex={-1} title={reason || undefined}
                className={`hp-status-option ${option.tone}${checked ? ' is-current' : ''}`}
                onClick={() => choose(option)}>
                <i className={`fas ${option.icon} hp-status-option-icon`} aria-hidden="true"></i>
                <span className="hp-status-option-text">
                  <span>{option.label}</span>
                  {reason && <small>{reason}</small>}
                </span>
                {checked && <i className="fas fa-check hp-status-option-check" aria-hidden="true"></i>}
              </button>
            );
          })}
        </div>
      )}
      {error && <span className="hp-status-error" role="alert">{error}</span>}
    </div>
  );
}

export default InterviewStatusMenu;
