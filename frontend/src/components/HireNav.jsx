import React from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { getCurrentRole, roleCanAccess } from '../roleAccess.js';

// Pages grouped under the "Hire" module, in tab order. `match` lists every
// path prefix that belongs to the tab (detail pages, legacy URLs).
export const HIRE_TABS = [
  { path: '/jobs', label: 'Jobs', match: ['/jobs', '/job-details.html'] },
  { path: '/talent', label: 'Talent', match: ['/talent'] },
  { path: '/analyze', label: 'Analyze', match: ['/analyze'] },
  { path: '/hiring-pipeline', label: 'Hiring Pipeline', match: ['/hiring-pipeline'] },
];

const matches = (pathname, prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`);

export function activeHireTab(pathname) {
  return HIRE_TABS.find(tab => tab.match.some(prefix => matches(pathname, prefix)));
}

export function isHirePath(pathname) {
  return pathname === '/hire' || Boolean(activeHireTab(pathname));
}

export function visibleHireTabs(role = getCurrentRole()) {
  return HIRE_TABS.filter(tab => roleCanAccess(role, tab.path));
}

/** /hire opens the first Hire page the signed-in role may use (Jobs by default). */
export function HireRedirect() {
  const [first] = visibleHireTabs();
  return <Navigate to={first ? first.path : '/welcome'} replace />;
}

/** Module tab bar shown at the top of every Hire page. */
export function HireTabs() {
  const { pathname } = useLocation();
  const active = activeHireTab(pathname);
  const tabs = visibleHireTabs();
  if (!active || !tabs.length) return null;
  return (
    <nav className="hire-tabs" aria-label="Hire">
      <span className="hire-tabs-title">Hire</span>
      <div className="hire-tabs-list">
        {tabs.map(tab => {
          const current = tab === active;
          return (
            <Link key={tab.path} to={tab.path} className={`hire-tab${current ? ' active' : ''}`}
              aria-current={current ? 'page' : undefined}>
              {tab.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
