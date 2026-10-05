import React, { useEffect, useState } from 'react';
import { apiGet } from '../api.js';
import { DataTable, Empty } from './Analytics.jsx';

const metrics = [['total_jds', 'Total Jobs'], ['active_jobs', 'Active Jobs'], ['submissions', 'Submissions'], ['client_submissions', 'Client Submissions'], ['client_rejections', 'Client Rejections'], ['internal_interviews', 'Internal Interviews'], ['external_interviews', 'External Interviews'], ['selected_bench_candidates', 'Bench Selected'], ['waitlisted_bench_candidates', 'Bench Waitlisted'], ['vendor_submitted_candidates', 'Vendor Submitted'], ['accepted_vendor_candidates', 'Vendor Accepted'], ['remaining_vendor_requirement', 'Open Shortage']];
export default function HomeDetails() {
  const [data, setData] = useState(null), [team, setTeam] = useState(null), [error, setError] = useState('');
  const [search, setSearch] = useState(''), [limit, setLimit] = useState(10);
  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([apiGet('/api/dashboard'), apiGet('/api/dashboard/team')]).then(([overview, members]) => {
      if (cancelled) return;
      if (overview.status === 'fulfilled') setData(overview.value.metrics || {}); else setError('Operational totals could not be loaded.');
      if (members.status === 'fulfilled') setTeam(Array.isArray(members.value) ? members.value : []); else setError(previous => `${previous} Team report could not be loaded.`);
    });
    return () => { cancelled = true; };
  }, []);
  const filtered = (team || []).filter(r => String(r.name).toLowerCase().includes(search.toLowerCase()));
  return <div className="operational-detail">
    {error && <p role="alert">{error}</p>}
    {data && <DataTable columns={[["name", "Metric"], ["count", "All-time total"]]} rows={metrics.map(([key, name]) => ({ name, count: data[key] }))} />}
    <h3>Team Performance</h3>{team?.length ? <><div className="analytics-filters"><label>Search team<input type="search" value={search} onChange={e => setSearch(e.target.value)} /></label><label>Rows<select value={limit} onChange={e => setLimit(Number(e.target.value))}>{[10, 25, 50].map(n => <option key={n}>{n}</option>)}</select></label></div><DataTable columns={[["name", "Name"], ["submissions", "Submissions"], ["clientSubs", "Client Submissions"], ["interviews", "Interviews"], ["hires", "Hires"]]} rows={filtered.slice(0, limit)} /><small>Showing {Math.min(filtered.length, limit)} of {filtered.length} team members</small></> : <Empty>{team ? 'No team reporting data has been recorded.' : error || 'Loading team report?'}</Empty>}
  </div>;
}
