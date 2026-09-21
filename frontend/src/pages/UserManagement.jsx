import React, { useCallback, useEffect, useState } from 'react';
import { apiGet, apiPost, apiPut } from '../api.js';
import '../styles/user-management.css';

const ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'recruiter', label: 'Recruiter' },
  { value: 'hiring_manager', label: 'Hiring Manager' },
];

export default function UserManagement() {
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({ username: '', email: '', password: '', role: 'recruiter' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);
  const isAdmin = (() => { try { const u = JSON.parse(localStorage.getItem('recruitment_assist_user') || '{}'); return ['admin','administrator'].includes(String(u.role || '').toLowerCase()); } catch { return false; } })();
  const load = useCallback(async () => { try { const data = await apiGet('/api/admin/users'); setUsers(data.users || []); } catch (e) { setError(e.message || 'Unable to load users.'); } }, []);
  useEffect(() => { load(); }, [load, reload]);
  const submit = async (e) => {
    e.preventDefault(); setError(''); setNotice(''); setBusy(true);
    try {
      const result = await apiPost('/api/admin/users', form);
      if (!result.ok) throw new Error(result.data?.error || 'Could not create user.');
      setForm({ username: '', email: '', password: '', role: 'recruiter' });
      setNotice('User created successfully.'); setReload(v => v + 1);
    } catch (e2) { setError(e2.message || 'Could not create user.'); }
    finally { setBusy(false); }
  };
  const update = async (user, patch) => {
    setError(''); setNotice('');
    try {
      const res = await fetch(`/api/admin/users/${user.id}`, { method: 'PATCH', credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-Session-Token': localStorage.getItem('session_token') || '' }, body: JSON.stringify(patch) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || 'Update failed.');
      setNotice('User updated.'); setReload(v => v + 1);
    } catch (e) { setError(e.message || 'Update failed.'); }
  };
  if (!isAdmin) return <main className="um-page"><section className="um-card"><h1>Administrator access required</h1><p>This page is available only to Admin users.</p></section></main>;
  return <main className="um-page">
    <header className="um-header"><div><p className="um-eyebrow">ACCESS CONTROL</p><h1>User Management</h1><p>Create accounts, assign roles, and manage access to ShimentoX.</p></div><span className="um-count">{users.length} users</span></header>
    {error && <div className="um-alert error" role="alert">{error}</div>}{notice && <div className="um-alert success" role="status">{notice}</div>}
    <section className="um-card"><h2><span>＋</span> Create user</h2><p className="um-muted">New users sign in with the credentials you provide.</p>
      <form className="um-form" onSubmit={submit}>
        <label>Username<input required minLength="3" maxLength="40" pattern="[a-zA-Z0-9][a-zA-Z0-9_.-]{2,39}" value={form.username} onChange={e=>setForm({...form,username:e.target.value})} placeholder="e.g. recruiter.jane" /></label>
        <label>Email<input type="email" required value={form.email} onChange={e=>setForm({...form,email:e.target.value})} placeholder="name@company.com" /></label>
        <label>Password<input type="password" required minLength="12" autoComplete="new-password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})} placeholder="At least 12 characters" /></label>
        <label>Role<select value={form.role} onChange={e=>setForm({...form,role:e.target.value})}>{ROLES.map(r=><option key={r.value} value={r.value}>{r.label}</option>)}</select></label>
        <button disabled={busy} type="submit">{busy ? 'Creating…' : 'Create user'}</button>
      </form>
    </section>
    <section className="um-card"><div className="um-list-heading"><div><h2>Team accounts</h2><p className="um-muted">Change roles or deactivate accounts.</p></div><button className="um-secondary" onClick={()=>setReload(v=>v+1)}>Refresh</button></div>
      <div className="um-table-wrap"><table className="um-table"><thead><tr><th>User</th><th>Email</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead><tbody>
      {users.map(u=><tr key={u.id}><td><strong>{u.username}</strong><small>#{u.id}</small></td><td>{u.email || '—'}</td><td><select aria-label={`Role for ${u.username}`} value={u.role || 'recruiter'} onChange={e=>update(u,{role:e.target.value})}>{ROLES.map(r=><option key={r.value} value={r.value}>{r.label}</option>)}</select></td><td><span className={`um-status ${u.is_active === false ? 'inactive' : 'active'}`}>{u.is_active === false ? 'Inactive' : 'Active'}</span></td><td><button className={u.is_active === false ? 'um-secondary' : 'um-danger'} onClick={()=>update(u,{is_active:u.is_active === false})}>{u.is_active === false ? 'Activate' : 'Deactivate'}</button></td></tr>)}
      {!users.length && <tr><td colSpan="5" className="um-empty">No users found.</td></tr>}
      </tbody></table></div>
    </section>
  </main>;
}
