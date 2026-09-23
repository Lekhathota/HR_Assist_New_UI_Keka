// Central role-based page access, shared by App.jsx (route guarding) and
// Navbar.jsx (nav link visibility) so the two never drift apart.
//
// Only the routes listed in RESTRICTED_ROUTES are scoped to specific roles;
// every other route stays open to any signed-in, recognized role until
// further access rules are defined.
export const ROLES = ['admin', 'finance', 'recruiter', 'hr', 'managers_consultant', 'it'];

const RESTRICTED_ROUTES = [
  { prefix: '/jobs', roles: ['recruiter'] },
  { prefix: '/analyze', roles: ['recruiter'] },
  { prefix: '/talent', roles: ['recruiter'] },
  { prefix: '/clients', roles: ['managers_consultant'] },
  { prefix: '/vendors', roles: ['managers_consultant'] },
  { prefix: '/hiring-pipeline', roles: ['recruiter', 'managers_consultant', 'hr'] },
  { prefix: '/insights', roles: ['finance'] },
  // Only admin (handled by the bypass above) may reach User Management.
  { prefix: '/admin/users', roles: [] },
];

export function getCurrentRole() {
  try {
    const user = JSON.parse(localStorage.getItem('recruitment_assist_user') || '{}');
    return String(user.role || '').trim().toLowerCase().replace(/[\s/-]+/g, '_');
  } catch {
    return '';
  }
}

export function roleCanAccess(role, pathname) {
  if (role === 'admin' || role === 'administrator') return true;
  const restriction = RESTRICTED_ROUTES.find(
    (r) => pathname === r.prefix || pathname.startsWith(`${r.prefix}/`)
  );
  if (!restriction) return true;
  return restriction.roles.includes(role);
}
