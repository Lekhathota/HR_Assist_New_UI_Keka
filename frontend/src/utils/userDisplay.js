export function readUser() {
  try { return JSON.parse(localStorage.getItem('recruitment_assist_user') || '{}') || {}; } catch { return {}; }
}
export function displayName(user) {
  return String(user.display_name || user.full_name || user.name || user.username || 'Recruiter').trim();
}
export function initials(name) {
  return String(name || '').trim().split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase() || 'U';
}
