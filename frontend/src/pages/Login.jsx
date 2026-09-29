import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiPost, saveToken } from '../api.js';
import '../styles/login.css';


const LOGIN_INTRO_SEEN_KEY = 'shimentox_login_intro_seen';
const LOGIN_USER_KEY = 'recruitment_assist_user';

function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState('');
  const [submitting, setSubmitting] = useState(false);
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
    setSubmitting(true);
    try {
      const { ok, data } = await apiPost('/api/login', { username, password });
      if (ok && data.success) {
        saveToken(data.token);
        if (data.user) {
          const { username: savedUsername, role, email } = data.user;
          localStorage.setItem(LOGIN_USER_KEY, JSON.stringify({ username: savedUsername, role, email }));
        }
        navigate('/welcome');
        return;
      } else {
        setError(data.message || 'Invalid credentials');
      }
    } catch {
      setError('Login failed. Please try again.');
    }
    setSubmitting(false);
  };

  return (
    <div className="login-page login-full">
      <section className="login-visual-panel" aria-label="ShimentoX talent intelligence">
        <div className="login-visual-brand">
          <img src="/ShimentoX-Light-Logo.webp" alt="ShimentoX" className="login-visual-logo login-logo-alive" />
          <span>Talent Intelligence Platform</span>
        </div>
      </section>
      <section className="login-auth-panel" aria-label="Sign in">
        {showIntro && (
          <section className="login-startup" aria-label="ShimentoX startup sequence">
            <div className="login-startup-logo-wrap">
              <span className="login-startup-ring" aria-hidden="true"></span>
              <img
                src="/ShimentoX-Light-Logo.webp"
                alt="ShimentoX"
                className="login-startup-logo"
                onError={(e) => { e.target.style.display = 'none'; }}
              />
              <span className="login-startup-scan" aria-hidden="true"></span>
            </div>
            <div className="login-startup-status" aria-live="polite">
              <span>Initializing Talent Intelligence</span>
              <span>Loading Candidate Graph</span>
              <span>Preparing AI Screening Engine</span>
              <span>Ready</span>
            </div>
            <button type="button" className="login-startup-skip" onClick={skipIntro}>
              Skip
            </button>
          </section>
        )}

        {!showIntro && (
          <div className="login-container login-container-ready">
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label htmlFor="username"><i className="fas fa-user"></i> Username</label>
                <input
                  type="text" id="username" required autoComplete="username"
                  value={username} onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter username"
                />
              </div>
              <div className="form-group">
                <label htmlFor="password"><i className="fas fa-lock"></i> Password</label>
                <input
                  type="password" id="password" required autoComplete="current-password"
                  value={password} onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password"
                />
              </div>
              <button type="submit" disabled={submitting}>
                {submitting ? (
                  <><i className="fas fa-spinner fa-spin"></i> Signing in...</>
                ) : (
                  <><i className="fas fa-sign-in-alt"></i> Login</>
                )}
              </button>
            </form>

            {error && <ul className="flashes"><li>{error}</li></ul>}
          </div>
        )}
      </section>
    </div>
  );
}

export default Login;
