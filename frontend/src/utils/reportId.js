import { apiPost } from '../api.js';

let current = '';

// Fallback when the server can't be reached: still unique per second and clearly
// marked as not issued by the server, rather than a random number.
function localId(now = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return `RPT-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-L${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
}

/** Ask the server for a real, sequential report ID (also records who generated it). */
export async function issueReportId(scope, format, extra = {}) {
  try {
    const { ok, data } = await apiPost('/api/reports/issue', { scope, format, ...extra });
    current = ok && data?.report_id ? data.report_id : localId();
  } catch {
    current = localId();
  }
  return current;
}

/** The ID issued for the report currently being generated. */
export function currentReportId() {
  return current || localId();
}
