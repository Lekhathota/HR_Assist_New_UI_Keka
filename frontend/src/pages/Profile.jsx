import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { toast } from '../components/EnterpriseFeedback.jsx';
import { apiGet, apiPost, apiPut } from '../api.js';
import '../styles/profile.css';
import '../styles/profile_extra.css';

// Each preference controls one group of top-bar notifications (saved per user).
const PREFERENCES = [
  ['notify_jobs', 'Jobs & reports', 'New, edited, closed or deleted JDs and exported reports', 'fas fa-briefcase'],
  ['notify_talent', 'Talent & screening', 'Resume uploads, candidate changes and screening results', 'fas fa-users'],
  ['notify_pipeline', 'Pipeline & interviews', 'Stage moves, interviews and assessments', 'fas fa-diagram-project'],
];

function Profile() {
  const location = useLocation();
  const [user, setUser]     = useState({ username: '', email: '', role: '', created_at: '' });
  const [message, setMessage] = useState('');
  const [form, setForm]     = useState({ email: '', current_password: '', new_password: '', confirm_password: '' });
  const [stats, setStats]   = useState(null);
  const [prefs, setPrefs]   = useState(null);
  const [savingPref, setSavingPref] = useState('');

  useEffect(() => {
    apiGet('/api/profile').then(data => {
      setUser(data.user || {});
      setForm(prev => ({ ...prev, email: data.user?.email || '' }));
    }).catch(() => {
      toast({ type: 'error', message: 'Could not load your profile. Please refresh the page.' });
    });
    apiGet('/api/profile/activity').then(setStats).catch(() => setStats({ error: true }));
    apiGet('/api/profile/preferences').then(data => setPrefs(data.preferences || {})).catch(() => setPrefs({ error: true }));
  }, []);

  const togglePreference = async (key) => {
    const next = !prefs[key];
    setPrefs(previous => ({ ...previous, [key]: next }));
    setSavingPref(key);
    try {
      const { ok, data } = await apiPut('/api/profile/preferences', { [key]: next });
      if (!ok) throw new Error(data?.error);
      setPrefs(data.preferences);
      toast({ type: 'success', message: 'Notification preferences saved.' });
    } catch {
      setPrefs(previous => ({ ...previous, [key]: !next }));
      toast({ type: 'error', message: 'Could not save your preference. Please try again.' });
    } finally {
      setSavingPref('');
    }
  };

  useEffect(() => {
    if (location.hash !== '#edit-profile') return;
    const section = document.getElementById('edit-profile');
    section?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    document.getElementById('email')?.focus({ preventScroll: true });
  }, [location.hash]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const { ok, data } = await apiPost('/api/profile', form);
      if (ok && data.success !== false) {
        const message = data.message || 'Profile updated successfully';
        setMessage(message);
        toast({ type: 'success', message });
        setForm(prev => ({ ...prev, current_password: '', new_password: '', confirm_password: '' }));
      } else {
        const message = data.error || 'Could not update profile.';
        setMessage(message);
        toast({ type: 'error', message });
      }
    } catch {
      const message = 'Could not update profile. Check that the API server is running.';
      setMessage(message);
      toast({ type: 'error', message });
    }
  };

  return (
    <Layout>
      <div className="profile-container">
        <div className="profile-header">
          <h1><i className="fas fa-user-circle"></i> My Profile</h1>
        </div>

        {message && <div className="alert alert-info profile-alert-spacing"><i className="fas fa-info-circle"></i> {message}</div>}

        <div className="grid grid-2 profile-grid-gap">
          {/* Account Info */}
          <div className="profile-box">
            <h2 className="profile-box-title"><i className="fas fa-id-card"></i> Account Information</h2>
            <div className="profile-info">
              {[['fas fa-user', 'Username', user.username], ['fas fa-envelope', 'Email', user.email], ['fas fa-shield-alt', 'Role', user.role], ['fas fa-calendar-alt', 'Member Since', (user.created_at || '').slice(0, 10)]].map(([icon, label, val]) => (
                <div key={label} className="profile-field">
                  <strong><i className={icon}></i> {label}</strong>
                  <span>{label === 'Role' ? <span className="badge badge-primary">{val}</span> : val}</span>
                </div>
              ))}
            </div>
            <div className="profile-activity-section">
              <h3 className="profile-activity-title"><i className="fas fa-chart-bar"></i> Your Activity</h3>
              <div className="profile-activity-grid">
                {[['JDs Created', 'jds_created'], ['Screenings Run', 'screenings_run'], ['Candidates Added', 'candidates_added'], ['Reports Generated', 'reports_generated']].map(([label, key]) => (
                  <div key={label} className="profile-activity-card">
                    <div className="profile-activity-label">{label}</div>
                    <div className="profile-activity-value">{stats && !stats.error ? (stats[key] ?? 0) : '—'}</div>
                  </div>
                ))}
              </div>
              <p className="profile-activity-note">
                {stats?.error ? 'Activity could not be loaded.'
                  : stats?.tracking_since ? `Counted from ${new Date(stats.tracking_since).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}, when activity tracking began.`
                  : stats ? 'Your actions in Jobs, Talent and Analyze will be counted here.' : 'Loading…'}
              </p>
            </div>
          </div>

          {/* Update Profile */}
          <div className="profile-box" id="edit-profile">
            <h2 className="profile-update-title"><i className="fas fa-edit"></i> Update Profile</h2>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label htmlFor="email"><i className="fas fa-envelope"></i> Email Address</label>
                <input type="email" id="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="Enter new email" />
              </div>
              <hr className="profile-hr" />
              <h3 className="profile-password-title"><i className="fas fa-lock"></i> Change Password</h3>
              {[['current_password', 'fas fa-key', 'Current Password', 'Enter current password'], ['new_password', 'fas fa-lock', 'New Password', 'Enter new password'], ['confirm_password', 'fas fa-lock', 'Confirm New Password', 'Confirm new password']].map(([field, icon, label, ph]) => (
                <div key={field} className="form-group">
                  <label htmlFor={field}><i className={icon}></i> {label}</label>
                  <input type="password" id={field} value={form[field]} onChange={(e) => setForm({ ...form, [field]: e.target.value })} placeholder={ph} />
                </div>
              ))}
              <button type="submit" className="profile-form-btn"><i className="fas fa-save"></i> Save Changes</button>
            </form>
          </div>
        </div>

        {/* Preferences */}
        <div className="profile-box profile-prefs-box">
          <h2 className="profile-box-title"><i className="fas fa-bell"></i> Notification Preferences</h2>
          <p className="profile-prefs-intro">Choose which activity appears in your notification bell. Changes save automatically.</p>
          {prefs?.error && <p className="profile-activity-note" role="alert">Preferences could not be loaded. Please refresh the page.</p>}
          <div className="profile-prefs-grid">
            {PREFERENCES.map(([key, name, desc, icon]) => (
              <div key={key} className="profile-pref-card">
                <div>
                  <div className="profile-pref-name">
                    <i className={`${icon} profile-pref-icon`}></i>{name}
                  </div>
                  <div className="profile-pref-desc">{desc}</div>
                </div>
                <label className="profile-toggle">
                  <input type="checkbox" aria-label={`${name} notifications`} checked={Boolean(prefs && !prefs.error && prefs[key])}
                    disabled={!prefs || prefs.error || savingPref === key} onChange={() => togglePreference(key)} />
                  <span className="profile-toggle-slider"></span>
                </label>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Layout>
  );
}

export default Profile;
