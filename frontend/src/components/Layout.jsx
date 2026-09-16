import React from 'react';
import { useAppearance } from './AppearanceProvider.jsx';
import Navbar from './Navbar.jsx';
import FloatingRecruiterChat from './FloatingRecruiterChat.jsx';


function Layout({ children }) {
  const { colorTheme } = useAppearance();
  return (
    <div className="app-shell">
      <img
        src="/ShimentoX-Light-Logo.webp"
        alt=""
        aria-hidden="true"
        className="shimento-bg-logo"
        onError={(e) => { e.currentTarget.style.display = 'none'; }}
      />
      <Navbar />
      <div className="workspace-content">
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
