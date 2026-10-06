import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { getCurrentRole, roleCanAccess } from '../roleAccess.js';
import { isHirePath, visibleHireTabs } from './HireNav.jsx';

const navigation = [
  ['/welcome', 'Home', 'fa-house'],
  ['/hire', 'Hire', 'fa-briefcase'],
  ['/clients', 'Clients', 'fa-building'],
  ['/vendors', 'Vendors', 'fa-handshake'],
  ['/insights', 'Reports', 'fa-chart-line'],
];

function Navbar() {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef(null);
  const role = getCurrentRole();

  useEffect(() => { setMenuOpen(false); }, [location.pathname]);

  const closeMenu = () => {
    setMenuOpen(false);
    if (window.matchMedia('(max-width: 820px)').matches) menuButton.current?.focus();
  };

  const isActive = (path) =>
    path === '/hire' ? isHirePath(location.pathname)
      : location.pathname === path || location.pathname.startsWith(path + '/');

  // Hire is shown when the role can open at least one of its pages.
  const visibleNavigation = navigation.filter(([path]) =>
    path === '/hire' ? visibleHireTabs(role).length > 0 : roleCanAccess(role, path));

  return (
    <>
      <button ref={menuButton} type="button" className="workspace-menu-toggle"
        aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
        aria-expanded={menuOpen} aria-controls="workspace-navigation"
        onClick={() => setMenuOpen(open => !open)}>
        <i className={`fas ${menuOpen ? 'fa-times' : 'fa-bars'}`} aria-hidden="true"></i>
      </button>
      <Link to="/welcome" className="workspace-brand" aria-label="Open home page" onClick={closeMenu}>
        <img src="/ShimentoX-Logo-Dark.png" alt="ShimentoX"
          onError={(e) => { e.target.style.display = 'none'; }} />
      </Link>
      <aside id="workspace-navigation" className={`workspace-sidebar${menuOpen ? ' workspace-sidebar-open' : ''}`}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && menuOpen) { event.preventDefault(); closeMenu(); }
        }}>
        <nav className="workspace-links" aria-label="Main navigation">
          {visibleNavigation.map(([path, label, icon]) => (
            <Link key={path} to={path}
              className={`workspace-nav-link${isActive(path) ? ' active' : ''}`}
              aria-current={isActive(path) ? 'page' : undefined} onClick={closeMenu}>
              <i className={`fas ${icon}`} aria-hidden="true"></i><span>{label}</span>
            </Link>
          ))}
        </nav>
        <div className="workspace-account">
          {roleCanAccess(role, '/admin/users') && <Link to="/admin/users" className={`workspace-nav-link${isActive('/admin/users') ? ' active' : ''}`} aria-current={isActive('/admin/users') ? 'page' : undefined} onClick={closeMenu}><i className="fas fa-user-gear" aria-hidden="true" /><span>Users</span></Link>}
        </div>
      </aside>
    </>
  );
}

export default Navbar;
