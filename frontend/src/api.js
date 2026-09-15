// Central API utility
// Attaches X-Session-Token header to every request automatically

const BASE = '';
export const JD_CACHE_KEY = 'recruitment_assist_jds_role_category_v3';
export const TALENT_CACHE_KEY = 'recruitment_assist_talent_role_category_v3';
export const DASHBOARD_CACHE_KEY = 'recruitment_assist_dashboard';
export const DASHBOARD_TEAM_CACHE_KEY = 'recruitment_assist_dashboard_team';
export const VENDOR_CACHE_KEY = 'recruitment_assist_vendors';
const LOGIN_USER_KEY = 'recruitment_assist_user';

export function readSessionCache(key) {
  try {
    const cached = JSON.parse(sessionStorage.getItem(key) || 'null');
    return cached?.data ?? null;
  } catch {
    return null;
  }
}

export function writeSessionCache(key, data) {
  try {
    sessionStorage.setItem(key, JSON.stringify({ savedAt: Date.now(), data }));
  } catch {
    /* storage unavailable */
  }
}

function clearDashboardCaches() {
  sessionStorage.removeItem(DASHBOARD_CACHE_KEY);
  sessionStorage.removeItem(DASHBOARD_TEAM_CACHE_KEY);
}

function clearTalentCache() {
  sessionStorage.removeItem(TALENT_CACHE_KEY);
}

function clearJdCache() {
  sessionStorage.removeItem(JD_CACHE_KEY);
}

function clearVendorCache() {
  sessionStorage.removeItem(VENDOR_CACHE_KEY);
}

export function getToken() {
  return localStorage.getItem('session_token') || '';
}

function authHeaders(extra = {}) {
  const token = getToken();
  return {
    ...(token ? { 'X-Session-Token': token } : {}),
    ...extra,
  };
}

/** Stale tokens (e.g. after server restart when tokens were only in RAM) → send user to login */
function redirectIfUnauthorized(path, status) {
  if (status !== 401 || path.startsWith('/api/login')) return;
  clearToken();
  if (window.location.pathname !== '/login') {
    window.location.assign('/login');
  }
}

function isDirectApi(path) {
  const apiPath = String(path || '').split('?')[0];
  return (
    apiPath.startsWith('/api/login') ||
    apiPath.startsWith('/api/logout') ||
    apiPath === '/api/dashboard' ||
    apiPath === '/api/dashboard/team' ||
    apiPath === '/api/metrics/jd-performance' ||
    apiPath === '/api/reports' ||
    apiPath === '/api/report/email' ||
    apiPath === '/api/profile' ||
    apiPath === '/api/jds' ||
    apiPath.startsWith('/api/jds/') ||
    apiPath === '/api/jds/create' ||
    apiPath === '/api/compare' ||
    apiPath === '/api/candidates' ||
    apiPath.startsWith('/api/candidates/') ||
    apiPath === '/api/clients' ||
    apiPath.startsWith('/api/clients/') ||
    apiPath === '/api/vendors' ||
    apiPath.startsWith('/api/vendors/') ||
    apiPath.startsWith('/api/admin/') ||
    apiPath.startsWith('/api/assessment/') ||
    apiPath === '/api/assessment/generate' ||
    apiPath === '/api/assessment/question' ||
    apiPath === '/api/interviews' ||
    apiPath.startsWith('/api/interviews/') ||
    apiPath.startsWith('/api/agentic/')
  );
}

function agenticPayload(method, path, body = {}) {
  const url = new URL(path, window.location.origin);
  const pathname = url.pathname;
  const params = url.searchParams;

  if (pathname === '/api/dashboard') return { task_type: 'dashboard' };
  if (pathname === '/api/dashboard/team') return { task_type: 'dashboard_team' };
  if (pathname === '/api/metrics/jd-performance') return { task_type: 'jd_performance' };
  if (pathname === '/api/reports') return { task_type: 'reports' };
  if (pathname === '/api/jds') return { task_type: 'jd_list' };
  if (pathname === '/api/clients') return { task_type: 'client_list' };
  if (pathname === '/api/candidates') {
    return {
      task_type: 'candidate_list',
      data: {
        status: params.get('status') || '',
        search: params.get('search') || '',
      },
    };
  }
  if (pathname === '/api/profile') {
    return method === 'POST'
      ? { task_type: 'profile_update', data: body || {} }
      : { task_type: 'profile_get' };
  }
  if (pathname === '/api/interviews/defaults') return { task_type: 'interview_defaults' };
  if (pathname === '/api/interviews/blocked-slots') {
    return { task_type: 'interview_blocked_slots', date: params.get('date') || '' };
  }
  if (pathname === '/api/interviews/generate-email') return { task_type: 'interview_generate_email', data: body || {} };
  if (pathname === '/api/interviews/schedule') return { task_type: 'interview_schedule', data: body || {} };
  if (pathname === '/api/candidates/repair') return { task_type: 'candidate_repair' };

  let match = pathname.match(/^\/api\/jds\/(\d+)$/);
  if (match) return { task_type: 'jd_details', jd_id: Number(match[1]) };
  match = pathname.match(/^\/api\/clients\/(\d+)$/);
  if (match) return { task_type: 'client_details', client_id: Number(match[1]) };
  match = pathname.match(/^\/api\/jds\/(\d+)\/delete$/);
  if (match) return { task_type: 'jd_delete', jd_id: Number(match[1]), confirmed: body?.confirmed === true };
  match = pathname.match(/^\/api\/candidates\/(\d+)$/);
  if (match) return { task_type: 'candidate_profile', candidate_id: Number(match[1]) };
  match = pathname.match(/^\/api\/candidates\/(\d+)\/delete$/);
  if (match) return { task_type: 'candidate_delete', candidate_id: Number(match[1]), confirmed: body?.confirmed === true };

  return null;
}

function unwrapAgentic(data) {
  return data && data.agentic && Object.prototype.hasOwnProperty.call(data, 'data') ? data.data : data;
}

function clearMutableCaches(path, body = {}) {
  const apiPath = String(path || '').split('?')[0];
  const taskType = String(body?.task_type || '');
  const isScreening = apiPath === '/api/compare' || taskType === 'screening';
  const isJdMutation =
    apiPath === '/api/jds/create' ||
    /^\/api\/jds\/\d+\/delete$/.test(apiPath) ||
    taskType === 'jd_create' ||
    taskType === 'jd_delete';
  const isCandidateMutation =
    /^\/api\/candidates\/\d+\/delete$/.test(apiPath) ||
    taskType === 'candidate_delete' ||
    taskType === 'candidate_repair';
  const isAssessmentMutation =
    apiPath === '/api/assessment/generate' ||
    apiPath === '/api/assessment/question' ||
    /^\/api\/assessment\/\d+$/.test(apiPath) ||
    /^\/api\/assessment\/question\/\d+$/.test(apiPath) ||
    /^\/api\/assessment\/\d+\/send$/.test(apiPath);
  const isInterviewMutation =
    apiPath === '/api/interviews/schedule' ||
    apiPath === '/api/interviews/outcome' ||
    /^\/api\/interviews\/\d+\/(reschedule|send-cancellation|send-followup|outcome)$/.test(apiPath);
  const isClientMutation = apiPath === '/api/clients' || /^\/api\/clients\/\d+/.test(apiPath);
  const isVendorMutation =
    apiPath === '/api/vendors' ||
    /^\/api\/vendors\/\d+/.test(apiPath) ||
    /^\/api\/jds\/\d+\/vendors/.test(apiPath);

  if (isScreening || isJdMutation) {
    clearJdCache();
  }
  if (isVendorMutation) {
    clearVendorCache();
  }
  if (isScreening || isCandidateMutation || isAssessmentMutation || isInterviewMutation) {
    clearTalentCache();
  }
  if (isScreening || isJdMutation || isCandidateMutation || isAssessmentMutation || isInterviewMutation || isClientMutation || isVendorMutation) {
    clearDashboardCaches();
  }
}

async function postAgentic(payload, originalPath) {
  const res = await fetch(`${BASE}/api/agentic/run`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    credentials: 'include',
    body: JSON.stringify(payload),
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  redirectIfUnauthorized(originalPath, res.status);
  return { res, data: unwrapAgentic(data) };
}

export async function apiGet(path) {
  const payload = !isDirectApi(path) ? agenticPayload('GET', path) : null;
  if (payload) {
    const { res, data } = await postAgentic(payload, path);
    if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
    return data;
  }

  const res = await fetch(`${BASE}${path}`, {
    headers: authHeaders(),
    credentials: 'include',
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  redirectIfUnauthorized(path, res.status);
  if (!res.ok) throw new Error(data.error || `GET ${path} failed: ${res.status}`);
  return data;
}

export async function apiPost(path, body) {
  const payload = !isDirectApi(path) ? agenticPayload('POST', path, body) : null;
  if (payload) {
    const { res, data } = await postAgentic(payload, path);
    if (res.ok) clearMutableCaches(path, payload);
    return { ok: res.ok, status: res.status, data };
  }

  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    credentials: 'include',
    body: JSON.stringify(body),
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  redirectIfUnauthorized(path, res.status);
  if (res.ok) clearMutableCaches(path, body);
  return { ok: res.ok, status: res.status, data };
}

export async function apiPut(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    credentials: 'include',
    body: JSON.stringify(body),
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  redirectIfUnauthorized(path, res.status);
  if (res.ok) clearMutableCaches(path, body);
  return { ok: res.ok, status: res.status, data };
}

export async function apiDelete(path) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'DELETE',
    headers: authHeaders(),
    credentials: 'include',
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  redirectIfUnauthorized(path, res.status);
  if (res.ok) clearMutableCaches(path);
  return { ok: res.ok, status: res.status, data };
}

export async function apiPostForm(path, formData) {
  let target = path;

  const res = await fetch(`${BASE}${target}`, {
    method: 'POST',
    headers: authHeaders(), // No Content-Type — browser sets multipart boundary
    credentials: 'include',
    body: formData,
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  redirectIfUnauthorized(path, res.status);
  if (res.ok) clearMutableCaches(path, Object.fromEntries(formData.entries()));
  return { ok: res.ok, status: res.status, data: unwrapAgentic(data) };
}

export function saveToken(token) {
  localStorage.setItem('session_token', token);
}

export function clearToken() {
  localStorage.removeItem('session_token');
  localStorage.removeItem(LOGIN_USER_KEY);
  clearJdCache();
  clearTalentCache();
  clearVendorCache();
  clearDashboardCaches();
}

export async function publicApiGet(path) {
  const res = await fetch(`${BASE}${path}`, { credentials: 'include' });
  let data = {};
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const error = new Error(data.error || `Request failed (${res.status})`);
    error.status = res.status;
    error.data = data;
    throw error;
  }
  return data;
}

export async function publicApiPost(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(body),
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const error = new Error(data.error || `Request failed (${res.status})`);
    error.status = res.status;
    error.data = data;
    throw error;
  }
  return data;
}
