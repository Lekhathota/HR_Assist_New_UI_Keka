import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { apiGet, apiPost, getToken } from '../api.js';

const POLL_MS = 30000;
// Icon and colour tone for each kind of Hire activity.
const KINDS = {
  jd_requirement_fulfilled: ['fa-circle-check', 'success'],
  jd_created: ['fa-file-circle-plus', 'accent'],
  jd_updated: ['fa-pen-to-square', 'neutral'],
  jd_status: ['fa-toggle-on', 'info'],
  jd_deleted: ['fa-trash-can', 'danger'],
  jd_vendors_assigned: ['fa-handshake', 'info'],
  resume_uploaded: ['fa-file-arrow-up', 'accent'],
  candidate_deleted: ['fa-user-minus', 'danger'],
  screening: ['fa-wand-magic-sparkles', 'accent'],
  candidate_status: ['fa-user-check', 'info'],
  candidate_stage: ['fa-diagram-project', 'info'],
  candidate_hold: ['fa-circle-pause', 'warning'],
  interview: ['fa-calendar-check', 'success'],
  assessment: ['fa-clipboard-check', 'info'],
};

export function timeAgo(value, now = Date.now()) {
  const time = new Date(value).getTime();
  if (!value || Number.isNaN(time)) return '';
  const seconds = Math.max(0, Math.round((now - time) / 1000));
  if (seconds < 60) return 'Just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? '' : 's'} ago`;
  return new Date(time).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** Top-bar bell: unread badge plus a dropdown of recent notifications. */
function NotificationBell() {
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const container = useRef(null);
  const button = useRef(null);
  const signedIn = Boolean(getToken());

  const load = useCallback(async () => {
    if (!getToken()) return;
    try {
      const data = await apiGet('/api/notifications');
      setItems(Array.isArray(data.notifications) ? data.notifications : []);
      setUnread(Number(data.unread_count) || 0);
      setError('');
    } catch {
      setError('Notifications could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load, then refresh periodically and whenever the tab regains focus.
  useEffect(() => {
    if (!signedIn) return undefined;
    load();
    const timer = setInterval(load, POLL_MS);
    const onFocus = () => load();
    window.addEventListener('focus', onFocus);
    return () => { clearInterval(timer); window.removeEventListener('focus', onFocus); };
  }, [signedIn, load]);

  useEffect(() => { setOpen(false); }, [location.pathname]);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => { if (!container.current?.contains(event.target)) setOpen(false); };
    const onKeyDown = (event) => { if (event.key === 'Escape') { setOpen(false); button.current?.focus(); } };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const toggle = () => {
    setOpen(value => {
      if (!value) { setLoading(items.length === 0); load(); }
      return !value;
    });
  };

  const markRead = async (ids) => {
    const targets = ids || items.filter(item => !item.read).map(item => item.id);
    if (!targets.length) return;
    // Update immediately; the next refresh reconciles with the server.
    setItems(previous => previous.map(item => (targets.includes(item.id) ? { ...item, read: true } : item)));
    setUnread(previous => Math.max(0, previous - targets.filter(id => items.some(item => item.id === id && !item.read)).length));
    try { await apiPost('/api/notifications/read', ids ? { ids } : {}); } catch { load(); }
  };

  // Clears every notification for this user only (teammates keep theirs).
  const clearAll = async () => {
    if (!items.length) return;
    const previous = { items, unread };
    setItems([]);
    setUnread(0);
    try {
      const { ok } = await apiPost('/api/notifications/clear', {});
      if (!ok) throw new Error('clear failed');
    } catch {
      setItems(previous.items);
      setUnread(previous.unread);
      setError('');
      load();
    }
  };

  const openItem = (item) => {
    if (!item.read) markRead([item.id]);
    setOpen(false);
    const target = item.link || (item.jd_id != null ? `/jobs/${item.jd_id}` : '');
    if (target) navigate(target);
  };

  if (!signedIn) return null;
  const label = unread ? `Notifications, ${unread} unread` : 'Notifications';

  return (
    <div className="workspace-notifications" ref={container}>
      <button ref={button} type="button" className="workspace-notification" aria-label={label} title="Notifications"
        aria-haspopup="true" aria-expanded={open} aria-controls="workspace-notification-panel" onClick={toggle}>
        <i className="far fa-bell" aria-hidden="true" />
        {unread > 0 && <span className="workspace-notification-badge" aria-hidden="true">{unread > 9 ? '9+' : unread}</span>}
      </button>
      {open && (
        <div id="workspace-notification-panel" className="workspace-notification-panel" role="dialog" aria-label="Notifications">
          <div className="workspace-notification-head">
            <strong>Notifications</strong>
            {items.length > 0 && (
              <span className="workspace-notification-actions">
                {unread > 0 && <button type="button" onClick={() => markRead(null)}>Mark all as read</button>}
                <button type="button" className="workspace-notification-clear" onClick={clearAll}>Clear all</button>
              </span>
            )}
          </div>
          {loading ? <p className="workspace-notification-empty">Loading…</p>
            : error ? <p className="workspace-notification-empty" role="alert">{error} <button type="button" onClick={load}>Retry</button></p>
            : items.length === 0 ? (
              <div className="workspace-notification-empty">
                <i className="far fa-bell-slash" aria-hidden="true" />
                <p>You're all caught up.</p>
                <small>Activity from Jobs, Talent, Analyze and the Hiring Pipeline will appear here.</small>
              </div>
            ) : (
              <ul className="workspace-notification-list">
                {items.map(item => {
                  const [icon, tone] = KINDS[item.type] || ['fa-bell', 'neutral'];
                  return (
                  <li key={item.id}>
                    <button type="button" className={`workspace-notification-item${item.read ? '' : ' unread'}`} onClick={() => openItem(item)}>
                      <span className={`workspace-notification-icon tone-${tone}`}><i className={`fas ${icon}`} aria-hidden="true" /></span>
                      <span className="workspace-notification-body">
                        <strong>{item.title}</strong>
                        <span>{item.message}</span>
                        <small>{timeAgo(item.created_at)}</small>
                      </span>
                      {!item.read && <span className="workspace-notification-dot" aria-label="Unread" />}
                    </button>
                  </li>
                  );
                })}
              </ul>
            )}
        </div>
      )}
    </div>
  );
}

export default NotificationBell;
