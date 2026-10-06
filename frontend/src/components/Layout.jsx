import React from 'react';
import Navbar from './Navbar.jsx';
import FloatingRecruiterChat from './FloatingRecruiterChat.jsx';
import { HireTabs } from './HireNav.jsx';
import UserMenu from './UserMenu.jsx';
import NotificationBell from './NotificationBell.jsx';


function Layout({ children }) {
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
        <div className="workspace-header-account"><NotificationBell />
        <UserMenu /></div>
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
