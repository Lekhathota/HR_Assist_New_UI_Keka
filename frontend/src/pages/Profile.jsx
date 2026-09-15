import React, { useState, useEffect } from 'react';
import Layout from '../components/Layout.jsx';
import { toast } from '../components/EnterpriseFeedback.jsx';
import { apiGet, apiPost } from '../api.js';
import '../styles/profile.css';
import '../styles/profile_extra.css';

function Profile() {
  const [user, setUser]     = useState({ username: '', email: '', role: '', created_at: '' });
  const [message, setMessage] = useState('');
  const [form, setForm]     = useState({ email: '', current_password: '', new_password: '', confirm_password: '' });

  useEffect(() => {
    apiGet('/api/profile').then(data => {
      setUser(data.user || {});
      setForm(prev => ({ ...prev, email: data.user?.email || '' }));
    }).catch(() => {});
  }, []);

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
                {[['JDs Created', user.jds_created || 0, 'blue'], ['Screenings Run', user.screenings_run || 0, 'green'], ['Candidates Added', user.candidates_added || 0, 'orange'], ['Reports Generated', user.reports_generated || 0, 'purple']].map(([label, val, color]) => (
                  <div key={label} className="profile-activity-card">
                    <div className="profile-activity-label">{label}</div>
                    <div className={`profile-activity-value profile-activity-${color}`}>{val}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Update Profile */}
          <div className="profile-box">
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
          <h2 className="profile-box-title"><i className="fas fa-cog"></i> Preferences</h2>
          <div className="profile-prefs-grid">
            {[['Email Notifications', 'Get notified when screenings complete', 'fas fa-bell'], ['Auto-screening', 'Automatically screen new resumes', 'fas fa-robot'], ['Weekly Reports', 'Receive weekly recruitment summaries', 'fas fa-chart-bar']].map(pref => (
              <div key={pref[0]} className="profile-pref-card">
                <div>
                  <div className="profile-pref-name">
                    <i className={`${pref[2]} profile-pref-icon`}></i>{pref[0]}
                  </div>
                  <div className="profile-pref-desc">{pref[1]}</div>
                </div>
                <label className="profile-toggle">
                  <input type="checkbox" defaultChecked />
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
