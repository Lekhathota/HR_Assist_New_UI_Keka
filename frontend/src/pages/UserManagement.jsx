import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiDelete, apiGet, apiPatch, apiPost } from '../api.js';
import Layout from '../components/Layout.jsx';
import { toast, useConfirm } from '../components/EnterpriseFeedback.jsx';
import { roleCanAccess } from '../roleAccess.js';
import { readUser, initials } from '../utils/userDisplay.js';
import '../styles/user-management.css';

const ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'recruiter', label: 'Recruiter' },
  { value: 'hr', label: 'HR' },
  { value: 'managers_consultant', label: 'Managers/Consultant' },
  { value: 'finance', label: 'Finance' },
  { value: 'it', label: 'IT' },
];
const ROLE_LABEL = Object.fromEntries(ROLES.map(r => [r.value, r.label]));

// Role descriptions come from the real page-access rules, so they never drift.
const PAGES = [['/jobs', 'Jobs'], ['/talent', 'Talent'], ['/analyze', 'Analyze'], ['/hiring-pipeline', 'Hiring Pipeline'],
  ['/clients', 'Clients'], ['/vendors', 'Vendors'], ['/insights', 'Reports']];
export function roleAccessSummary(role) {
  if (role === 'admin') return 'Full access, including user management';
  const pages = PAGES.filter(([path]) => roleCanAccess(role, path)).map(([, label]) => label);
  return pages.length ? `Home, ${pages.join(', ')}` : 'Home and Profile only';
}

const EMPTY_FORM = { username: '', email: '', password: '', role: 'recruiter' };
const isActive = user => user.is_active !== false;
const formatDate = value => {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime())
    ? date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
};

function AddUserDialog({ onClose, onCreated }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const firstField = useRef(null);

  useEffect(() => {
    firstField.current?.focus();
    const onKey = event => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const set = (key, value) => setForm(previous => ({ ...previous, [key]: value }));
  const submit = async event => {
    event.preventDefault();
    setError('');
    setBusy(true);
    try {
      const { ok, data } = await apiPost('/api/admin/users', form);
      if (!ok) throw new Error(data?.error || 'Could not create the user.');
      toast({ type: 'success', message: `${form.username} can now sign in.` });
      onCreated();
    } catch (err) {
      setError(err.message || 'Could not create the user.');
    } finally {
      setBusy(false);
    }
  };

  const passwordShort = form.password.length > 0 && form.password.length < 12;
  return (
    <div className="um-dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <form className="um-dialog" role="dialog" aria-modal="true" aria-labelledby="um-dialog-title"
        onMouseDown={event => event.stopPropagation()} onSubmit={submit}>
        <header className="um-dialog-head">
          <div>
            <h2 id="um-dialog-title">Add user</h2>
            <p>They sign in with the username and password you set here.</p>
          </div>
          <button type="button" className="um-icon-btn" aria-label="Close" onClick={onClose}><i className="fas fa-xmark" aria-hidden="true" /></button>
        </header>

        <div className="um-dialog-body">
          <label className="um-field">
            <span>Username</span>
            <input ref={firstField} required minLength="3" maxLength="40" pattern="[a-zA-Z0-9][a-zA-Z0-9_.\-]{2,39}"
              autoComplete="off" value={form.username} onChange={e => set('username', e.target.value)} placeholder="e.g. jane.doe" />
            <small>3–40 characters: letters, numbers, dot, underscore or hyphen.</small>
          </label>
          <label className="um-field">
            <span>Email</span>
            <input type="email" required autoComplete="off" value={form.email} onChange={e => set('email', e.target.value)} placeholder="name@company.com" />
          </label>
          <label className="um-field">
            <span>Temporary password</span>
            <span className="um-password">
              <input type={showPassword ? 'text' : 'password'} required minLength="12" autoComplete="new-password"
                value={form.password} onChange={e => set('password', e.target.value)} placeholder="At least 12 characters" />
              <button type="button" className="um-icon-btn" onClick={() => setShowPassword(v => !v)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}>
                <i className={`far ${showPassword ? 'fa-eye-slash' : 'fa-eye'}`} aria-hidden="true" />
              </button>
            </span>
            <small className={passwordShort ? 'um-warn' : ''}>
              {passwordShort ? `${12 - form.password.length} more characters needed.` : 'Share it securely; they can change it from their profile.'}
            </small>
          </label>
          <fieldset className="um-field um-roles">
            <legend>Role</legend>
            {ROLES.map(role => (
              <label key={role.value} className={`um-role-option${form.role === role.value ? ' selected' : ''}`}>
                <input type="radio" name="role" value={role.value} checked={form.role === role.value} onChange={() => set('role', role.value)} />
                <span><strong>{role.label}</strong><small>{roleAccessSummary(role.value)}</small></span>
              </label>
            ))}
          </fieldset>
          {error && <div className="um-alert error" role="alert"><i className="fas fa-circle-exclamation" aria-hidden="true" />{error}</div>}
        </div>

        <footer className="um-dialog-foot">
          <button type="button" className="um-btn um-btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="um-btn um-btn-primary" disabled={busy}>
            {busy ? <><i className="fas fa-spinner fa-spin" aria-hidden="true" /> Creating…</> : <><i className="fas fa-user-plus" aria-hidden="true" /> Create user</>}
          </button>
        </footer>
      </form>
    </div>
  );
}

export default function UserManagement() {
  const confirm = useConfirm();
  const me = readUser();
  const canManageUsers = ['admin', 'administrator'].includes(String(me.role || '').toLowerCase());
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [adding, setAdding] = useState(false);
  const [pending, setPending] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet('/api/admin/users');
      setUsers(Array.isArray(data.users) ? data.users : []);
      setError('');
    } catch (e) {
      setError(e.message || 'Unable to load users.');
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { if (canManageUsers) load(); }, [canManageUsers, load]);

  const stats = useMemo(() => ({
    total: users.length,
    active: users.filter(isActive).length,
    inactive: users.filter(u => !isActive(u)).length,
    admins: users.filter(u => u.role === 'admin' && isActive(u)).length,
  }), [users]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return users
      .filter(u => !needle || `${u.username} ${u.email || ''}`.toLowerCase().includes(needle))
      .filter(u => !roleFilter || u.role === roleFilter)
      .filter(u => statusFilter === 'all' || (statusFilter === 'active') === isActive(u))
      .sort((a, b) => Number(isActive(b)) - Number(isActive(a)) || String(a.username).localeCompare(String(b.username)));
  }, [users, query, roleFilter, statusFilter]);

  const update = async (user, patch, successMessage) => {
    setPending(user.id);
    try {
      const { ok, data } = await apiPatch(`/api/admin/users/${user.id}`, patch);
      if (!ok) throw new Error(data?.error || 'Update failed.');
      setUsers(previous => previous.map(u => (u.id === user.id ? { ...u, ...patch } : u)));
      toast({ type: 'success', message: successMessage });
    } catch (e) {
      toast({ type: 'error', message: e.message || 'Update failed.' });
    } finally {
      setPending(null);
    }
  };

  const changeRole = async (user, role) => {
    if (role === user.role) return;
    const approved = await confirm({
      title: 'Change role?',
      message: `${user.username} will change from ${ROLE_LABEL[user.role] || user.role} to ${ROLE_LABEL[role]}. New access: ${roleAccessSummary(role)}.`,
      confirmLabel: 'Change role',
      icon: 'fas fa-user-shield',
    });
    if (approved) update(user, { role }, `${user.username} is now ${ROLE_LABEL[role]}.`);
  };

  const toggleActive = async user => {
    const deactivating = isActive(user);
    const approved = await confirm({
      title: deactivating ? 'Deactivate user?' : 'Reactivate user?',
      message: deactivating
        ? `${user.username} will be signed out everywhere and won't be able to sign in until reactivated.`
        : `${user.username} will be able to sign in again.`,
      confirmLabel: deactivating ? 'Deactivate' : 'Reactivate',
      danger: deactivating,
      icon: deactivating ? 'fas fa-user-slash' : 'fas fa-user-check',
    });
    if (approved) update(user, { is_active: !deactivating }, `${user.username} was ${deactivating ? 'deactivated' : 'reactivated'}.`);
  };

  const removeUser = async user => {
    const approved = await confirm({
      title: 'Remove user?',
      message: `${user.username} will be permanently removed and signed out everywhere. This can't be undone - to block access temporarily, deactivate the user instead.`,
      confirmLabel: 'Remove user',
      danger: true,
      icon: 'fas fa-user-minus',
    });
    if (!approved) return;
    setPending(user.id);
    try {
      const { ok, data } = await apiDelete(`/api/admin/users/${user.id}`);
      if (!ok) throw new Error(data?.error || 'Could not remove user.');
      setUsers(previous => previous.filter(u => u.id !== user.id));
      toast({ type: 'success', message: `${user.username} was removed.` });
    } catch (e) {
      toast({ type: 'error', message: e.message || 'Could not remove user.' });
    } finally {
      setPending(null);
    }
  };

  if (!canManageUsers) {
    return <Layout><div className="um-page"><section className="um-card um-denied">
      <i className="fas fa-lock" aria-hidden="true" />
      <h1>Administrator access required</h1>
      <p>Only administrators can manage users. Ask an admin if you need access changed.</p>
    </section></div></Layout>;
  }

  const filtersActive = query || roleFilter || statusFilter !== 'all';
  return <Layout><div className="um-page">
    <header className="um-header">
      <div>
        <span className="um-eyebrow">Access control</span>
        <h1>Users</h1>
        <p>Invite people, assign roles and control who can sign in to ShimentoX.</p>
      </div>
      <button type="button" className="um-btn um-btn-primary" onClick={() => setAdding(true)}>
        <i className="fas fa-user-plus" aria-hidden="true" /> Add user
      </button>
    </header>

    <section className="um-stats" aria-label="User summary">
      {[['Total users', stats.total, 'fa-users', ''], ['Active', stats.active, 'fa-circle-check', 'good'],
        ['Inactive', stats.inactive, 'fa-circle-pause', 'muted'], ['Active admins', stats.admins, 'fa-user-shield', 'accent']].map(([label, value, icon, tone]) => (
        <div key={label} className={`um-stat ${tone}`}>
          <span className="um-stat-icon"><i className={`fas ${icon}`} aria-hidden="true" /></span>
          <div><span>{label}</span><strong>{loading ? '—' : value}</strong></div>
        </div>
      ))}
    </section>

    <section className="um-card">
      <div className="um-toolbar">
        <label className="um-search">
          <i className="fas fa-magnifying-glass" aria-hidden="true" />
          <span className="sr-only">Search users</span>
          <input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search by name or email" />
        </label>
        <label>
          <span className="sr-only">Filter by role</span>
          <select value={roleFilter} onChange={e => setRoleFilter(e.target.value)}>
            <option value="">All roles</option>
            {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </label>
        <div className="um-segment" role="group" aria-label="Filter by status">
          {[['all', 'All'], ['active', 'Active'], ['inactive', 'Inactive']].map(([value, label]) => (
            <button key={value} type="button" aria-pressed={statusFilter === value} className={statusFilter === value ? 'active' : ''}
              onClick={() => setStatusFilter(value)}>{label}</button>
          ))}
        </div>
        <span className="um-count">{loading ? 'Loading…' : `Showing ${visible.length} of ${users.length}`}</span>
      </div>

      {error ? (
        <div className="um-empty" role="alert">
          <i className="fas fa-triangle-exclamation" aria-hidden="true" />
          <p>{error}</p>
          <button type="button" className="um-btn um-btn-ghost" onClick={load}>Try again</button>
        </div>
      ) : (
        <div className="um-table-wrap">
          <table className="um-table">
            <thead><tr><th scope="col">User</th><th scope="col">Role</th><th scope="col">Status</th><th scope="col">Member since</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {loading && !users.length ? [0, 1, 2].map(i => <tr key={i} className="um-skeleton"><td colSpan="5"><span /></td></tr>)
                : visible.map(user => {
                  const self = user.username === me.username;
                  const busy = pending === user.id;
                  return (
                    <tr key={user.id} className={isActive(user) ? '' : 'um-row-inactive'}>
                      <td>
                        <div className="um-user">
                          <span className="um-avatar" aria-hidden="true">{initials(user.username)}</span>
                          <span>
                            <strong>{user.username}{self && <em className="um-you">You</em>}</strong>
                            <small>{user.email || 'No email'}</small>
                          </span>
                        </div>
                      </td>
                      <td>
                        <select className="um-role-select" aria-label={`Role for ${user.username}`} value={user.role || 'recruiter'}
                          disabled={busy || self} title={self ? 'You cannot change your own role' : roleAccessSummary(user.role)}
                          onChange={e => changeRole(user, e.target.value)}>
                          {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                        </select>
                      </td>
                      <td><span className={`um-status ${isActive(user) ? 'active' : 'inactive'}`}>{isActive(user) ? 'Active' : 'Inactive'}</span></td>
                      <td className="um-date">{formatDate(user.created_at)}</td>
                      <td className="um-actions">
                        <button type="button" className={`um-btn um-btn-sm ${isActive(user) ? 'um-btn-danger-ghost' : 'um-btn-ghost'}`}
                          disabled={busy || self} title={self ? 'You cannot deactivate your own account' : undefined}
                          onClick={() => toggleActive(user)}>
                          {busy ? <i className="fas fa-spinner fa-spin" aria-hidden="true" />
                            : isActive(user) ? <><i className="fas fa-user-slash" aria-hidden="true" /> Deactivate</>
                              : <><i className="fas fa-user-check" aria-hidden="true" /> Reactivate</>}
                        </button>
                        <button type="button" className="um-btn um-btn-sm um-btn-remove"
                          disabled={busy || self} title={self ? 'You cannot remove your own account' : `Remove ${user.username}`}
                          aria-label={`Remove ${user.username}`}
                          onClick={() => removeUser(user)}>
                          <i className="fas fa-trash-can" aria-hidden="true" /> Remove
                        </button>
                      </td>
                    </tr>
                  );
                })}
              {!loading && !visible.length && (
                <tr><td colSpan="5">
                  <div className="um-empty">
                    <i className="fas fa-user-group" aria-hidden="true" />
                    <p>{filtersActive ? 'No users match these filters.' : 'No users yet.'}</p>
                    {filtersActive && <button type="button" className="um-btn um-btn-ghost" onClick={() => { setQuery(''); setRoleFilter(''); setStatusFilter('all'); }}>Clear filters</button>}
                  </div>
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>

    {adding && <AddUserDialog onClose={() => setAdding(false)} onCreated={() => { setAdding(false); load(); }} />}
  </div></Layout>;
}
