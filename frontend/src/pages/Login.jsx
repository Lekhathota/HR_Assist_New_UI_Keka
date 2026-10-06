import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiPost, saveToken } from '../api.js';
import '../styles/login.css';
import '../styles/auth.css';


const LOGIN_INTRO_SEEN_KEY = 'shimentox_login_intro_seen';
const LOGIN_USER_KEY = 'recruitment_assist_user';
// "Remember me" keeps only the username on this device, never the password.
const REMEMBERED_USERNAME_KEY = 'shimentox_remembered_username';

function Login() {
  const [username, setUsername] = useState(() => {
    try { return localStorage.getItem(REMEMBERED_USERNAME_KEY) || ''; } catch { return ''; }
  });
  const [remember, setRemember] = useState(() => {
    try { return Boolean(localStorage.getItem(REMEMBERED_USERNAME_KEY)); } catch { return false; }
  });
  const [notice, setNotice] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showIntro, setShowIntro] = useState(() => {
    if (typeof window === 'undefined') return false;
    const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    return !prefersReducedMotion && sessionStorage.getItem(LOGIN_INTRO_SEEN_KEY) !== 'true';
  });
  const navigate = useNavigate();

  useEffect(() => {
    if (!showIntro) return undefined;
    const timer = window.setTimeout(() => {
      sessionStorage.setItem(LOGIN_INTRO_SEEN_KEY, 'true');
      setShowIntro(false);
    }, 2200);
    return () => window.clearTimeout(timer);
  }, [showIntro]);

  const skipIntro = () => {
    sessionStorage.setItem(LOGIN_INTRO_SEEN_KEY, 'true');
    setShowIntro(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setNotice('');
    setSubmitting(true);
    try {
      const { ok, status, data } = await apiPost('/api/login', { username, password });
      if (ok && data.success) {
        saveToken(data.token);
        try {
          if (remember) localStorage.setItem(REMEMBERED_USERNAME_KEY, username.trim());
          else localStorage.removeItem(REMEMBERED_USERNAME_KEY);
        } catch { /* storage unavailable */ }
        if (data.user) {
          const { username: savedUsername, role, email } = data.user;
          localStorage.setItem(LOGIN_USER_KEY, JSON.stringify({ username: savedUsername, role, email }));
        }
        navigate('/welcome');
        return;
      } else {
        setError(data?.message || data?.error || (status === 401
          ? 'Invalid username or password.'
          : 'Login service unavailable. Make sure the backend is running and try again.'));
      }
    } catch {
      setError('Login failed. Please try again.');
    }
    setSubmitting(false);
  };

  return (
    <div className="auth-page">
      {showIntro && (
        <section className="login-startup auth-intro" aria-label="ShimentoX startup sequence">
          <div className="login-startup-logo-wrap">
            <span className="login-startup-ring" aria-hidden="true"></span>
            <img src="/ShimentoX-Light-Logo.webp" alt="ShimentoX" className="login-startup-logo"
              onError={(e) => { e.target.style.display = 'none'; }} />
            <span className="login-startup-scan" aria-hidden="true"></span>
          </div>
          <div className="login-startup-status" aria-live="polite">
            <span>Initializing Talent Intelligence</span>
            <span>Loading Candidate Graph</span>
            <span>Preparing AI Screening Engine</span>
            <span>Ready</span>
          </div>
          <button type="button" className="login-startup-skip" onClick={skipIntro}>Skip</button>
        </section>
      )}

      <span className="auth-blob auth-blob-a" aria-hidden="true" />
      <span className="auth-blob auth-blob-b" aria-hidden="true" />
      <span className="auth-blob auth-blob-c" aria-hidden="true" />

      <main className="auth-main">
        <header className="auth-brand">
          <img src="/ShimentoX-Logo-Dark.png" alt="ShimentoX" className="auth-logo" />
          <span>Talent Intelligence Platform</span>
        </header>

        <section className="auth-card" aria-labelledby="auth-title">
          <div className="auth-heading">
            <h1 id="auth-title">Sign In</h1>
            <p>Welcome back! Please enter your credentials.</p>
          </div>

          <form className="auth-form" onSubmit={handleSubmit}>
            <label className="auth-field" htmlFor="username">
              <i className="far fa-user" aria-hidden="true" />
              <span className="auth-field-body">
                <span className="auth-field-label">Username</span>
                <input type="text" id="username" required autoComplete="username" autoFocus={!showIntro && !username}
                  value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Enter your username" />
              </span>
            </label>
            <label className="auth-field" htmlFor="password">
              <i className="fas fa-lock" aria-hidden="true" />
              <span className="auth-field-body">
                <span className="auth-field-label">Password</span>
                <input type={showPassword ? 'text' : 'password'} id="password" required autoComplete="current-password"
                  autoFocus={!showIntro && Boolean(username)}
                  value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter your password" />
              </span>
              <button type="button" className="auth-reveal" onClick={() => setShowPassword(value => !value)}
                aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}>
                <i className={`far ${showPassword ? 'fa-eye-slash' : 'fa-eye'}`} aria-hidden="true" />
              </button>
            </label>

            <div className="auth-row">
              <label className="auth-remember">
                <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
                <span>Remember me</span>
              </label>
              <button type="button" className="auth-link" onClick={() => { setError(''); setNotice('To reset your password, contact your ShimentoX administrator.'); }}>
                Forgot password?
              </button>
            </div>

            {error && <div className="auth-error" role="alert"><i className="fas fa-circle-exclamation" aria-hidden="true" />{error}</div>}
            {notice && !error && <div className="auth-notice" role="status"><i className="fas fa-circle-info" aria-hidden="true" />{notice}</div>}

            <button type="submit" className="auth-submit" disabled={submitting}>
              {submitting
                ? <><i className="fas fa-spinner fa-spin" aria-hidden="true" /> Signing in…</>
                : <><i className="fas fa-arrow-right-to-bracket" aria-hidden="true" /> Login</>}
            </button>
          </form>

          <p className="auth-foot">New to ShimentoX? <strong>Contact your administrator</strong></p>
        </section>
      </main>
    </div>
  );
}

export default Login;
