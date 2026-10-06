import React from 'react';
import { Link } from 'react-router-dom';
import Navbar from './Navbar.jsx';
import FloatingRecruiterChat from './FloatingRecruiterChat.jsx';
import { HireTabs } from './HireNav.jsx';
import { readUser, displayName, initials } from '../utils/userDisplay.js';


function Layout({ children }) {
  const user = readUser();
  return (
    <div className="app-shell">
      <img
        src="/ShimentoX-Light-Logo.webp"
        alt=""
        aria-hidden="true"
        className="shimento-bg-logo"
        onError={(e) => { e.currentTarget.style.display = 'none'; }}
      />
      <header className="workspace-topbar">
        <button className="workspace-search" type="button" onClick={() => window.dispatchEvent(new Event('open-command-palette'))}>
          <i className="fas fa-search" aria-hidden="true" /><span>Search pages and actions…</span><kbd>Ctrl K</kbd>
        </button>
        <div className="workspace-header-account"><span className="workspace-notification" role="img" aria-label="Notifications are not configured" title="Notifications are not configured"><i className="far fa-bell" aria-hidden="true" /></span>
        <Link className="workspace-user" to="/profile"><span className="workspace-avatar">{initials(displayName(user))}</span><span><strong>{displayName(user)}</strong><small>{String(user.role || '').replaceAll('_', ' ')}</small></span><i className="fas fa-chevron-down" aria-hidden="true" /></Link></div>
      </header>
      <Navbar />
      <div className="workspace-content">
      <HireTabs />
      <main className="main-container">
        {children}
      </main>
      <footer className="app-footer">
        <div className="app-footer-brand">
  <img
    src="/ShimentoX-Logo.png"
    alt="ShimentoX"
    className="app-footer-logo"
    onError={(e) => { e.currentTarget.style.display = 'none'; }}
  />
</div>
        <nav className="app-footer-social" aria-label="Company social profiles">
          <a href="https://shimentox.ai/" target="_blank" rel="noreferrer" aria-label="ShimentoX website">
            <i className="fas fa-globe"></i>
          </a>
          <a href="https://www.linkedin.com/company/shimento-inc./" target="_blank" rel="noreferrer" aria-label="ShimentoX LinkedIn">
            <i className="fab fa-linkedin"></i>
          </a>
          <a href="https://www.crunchbase.com/organization/shimento" target="_blank" rel="noreferrer" aria-label="ShimentoX Crunchbase">
            <i className="fas fa-building"></i>
          </a>
          <a href="mailto:info@shimento.com" aria-label="Email ShimentoX">
            <i className="fas fa-envelope"></i>
          </a>
        </nav>
      </footer>
      </div>
      <FloatingRecruiterChat />
    </div>
  );
}

export default Layout;
