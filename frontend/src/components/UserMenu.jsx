import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { apiPost, clearToken, getToken } from '../api.js';
import { readUser, displayName, initials } from '../utils/userDisplay.js';

function UserMenu() {
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const container = useRef(null);
  const button = useRef(null);
  const user = readUser();
  const name = displayName(user);
  const role = String(user.role || '').replaceAll('_', ' ');
  const signedIn = Boolean(getToken());

  useEffect(() => { setOpen(false); }, [location.pathname]);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => {
      if (!container.current?.contains(event.target)) setOpen(false);
    };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') { setOpen(false); button.current?.focus(); }
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const handleLogout = async () => {
    setOpen(false);
    try {
      await apiPost('/api/logout', {});
    } catch {
      // Clear the local session even if the API is unavailable.
    }
    clearToken();
    navigate('/login');
  };

  if (!signedIn) {
    return (
      <Link className="workspace-login" to="/login">
        <i className="fas fa-sign-in-alt" aria-hidden="true" /><span>Login</span>
      </Link>
    );
  }

  return (
    <div className="workspace-user-menu" ref={container}>
      <button ref={button} type="button" className="workspace-user"
        aria-haspopup="menu" aria-expanded={open} aria-controls="workspace-user-dropdown"
        onClick={() => setOpen(value => !value)}>
        <span className="workspace-avatar" aria-hidden="true">{initials(name)}</span>
        <span className="workspace-user-text"><strong>{name}</strong>{role && <small>{role}</small>}</span>
        <i className={`fas fa-chevron-${open ? 'up' : 'down'}`} aria-hidden="true" />
      </button>
      {open && (
        <div id="workspace-user-dropdown" className="workspace-user-dropdown" role="menu">
          <div className="workspace-user-dropdown-header">
            <strong>{name}</strong>
            {user.email && <small>{user.email}</small>}
          </div>
          <Link role="menuitem" to="/profile#edit-profile" className="workspace-user-dropdown-item">
            <i className="fas fa-user-pen" aria-hidden="true" /><span>Edit Profile</span>
          </Link>
          <button role="menuitem" type="button" className="workspace-user-dropdown-item workspace-user-dropdown-logout" onClick={handleLogout}>
            <i className="fas fa-sign-out-alt" aria-hidden="true" /><span>Logout</span>
          </button>
        </div>
      )}
    </div>
  );
}

export default UserMenu;
