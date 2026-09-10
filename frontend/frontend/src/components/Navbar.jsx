import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { apiPost, clearToken } from '../api.js';

const navigation = [
  ['/dashboard', 'Dashboard', 'fa-chart-line'],
  ['/jobs', 'Jobs', 'fa-briefcase'],
  ['/analyze', 'Analyze', 'fa-code-compare'],
  ['/talent', 'Talent', 'fa-users'],
  ['/clients', 'Clients', 'fa-building'],
  ['/vendors', 'Vendors', 'fa-handshake'],
  ['/admin/workflow', 'Workflow', 'fa-screwdriver-wrench'],
  ['/hiring-pipeline', 'Pipeline', 'fa-route'],
  ['/insights', 'Reports', 'fa-chart-bar'],
];

function Navbar() {
  const navigate  = useNavigate();
  const location  = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef(null);

  useEffect(() => { setMenuOpen(false); }, [location.pathname]);

  const closeMenu = () => {
    setMenuOpen(false);
    if (window.matchMedia('(max-width: 820px)').matches) menuButton.current?.focus();
  };

  const handleLogout = async () => {
    try {
      await apiPost('/api/logout', {});
    } catch {
      // If the API is down, still clear the local session and return to login.
    }
    clearToken();
    navigate('/login');
  };

  const isActive = (path) =>
    location.pathname === path || location.pathname.startsWith(path + '/');

  return (
    <>
        <button ref={menuButton} type="button" className="workspace-menu-toggle"
          aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
          aria-expanded={menuOpen} aria-controls="workspace-navigation"
          onClick={() => setMenuOpen(open => !open)}>
          <i className={`fas ${menuOpen ? 'fa-times' : 'fa-bars'}`} aria-hidden="true"></i>
        </button>
<aside id="workspace-navigation" className={`workspace-sidebar${menuOpen ? ' workspace-sidebar-open' : ''}`}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && menuOpen) { event.preventDefault(); closeMenu(); }
        }}>
        <Link to="/welcome" className="workspace-brand" aria-label="Open welcome page" onClick={closeMenu}>
          <img src="/ShimentoX-Light-Logo.webp" alt="ShimentoX"
            onError={(e) => { e.target.style.display = 'none'; }} />
        </Link>
        <nav className="workspace-links" aria-label="Main navigation">
          {navigation.map(([path, label, icon]) => (
            <Link key={path} to={path}
              className={`workspace-nav-link${isActive(path) ? ' active' : ''}`}
              aria-current={isActive(path) ? 'page' : undefined} onClick={closeMenu}>
              <i className={`fas ${icon}`} aria-hidden="true"></i><span>{label}</span>
            </Link>
          ))}
        </nav>
        <div className="workspace-account">
          <Link to="/profile" className={`workspace-nav-link${isActive('/profile') ? ' active' : ''}`}
            aria-current={isActive('/profile') ? 'page' : undefined} onClick={closeMenu}>
            <i className="fas fa-user-circle"></i><span>Profile</span>
          </Link>
          <button type="button" onClick={handleLogout} className="workspace-nav-link">
            <i className="fas fa-sign-out-alt"></i><span>Exit</span>
          </button>
        </div>
      </aside>
    </>
  );
}

export default Navbar;
