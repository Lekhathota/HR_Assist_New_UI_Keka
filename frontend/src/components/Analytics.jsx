import React, { useEffect, useMemo, useState, useRef } from 'react';
import { apiGet } from '../api.js';
import { defaultFilters } from '../utils/analytics.js';
import { buildAnalyticsView } from '../utils/analyticsView.js';

export function useAnalytics(endpoint) {
  const [filters, setFilters] = useState(defaultFilters);
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(''); setSnapshot(null);
    const home = endpoint === '/api/dashboard';
    // Keep the existing API URLs and contracts. Supplemental panels may fail independently.
    Promise.allSettled([apiGet(endpoint), apiGet(home ? '/api/interviews' : '/api/dashboard'), apiGet('/api/jds')]).then(results => {
      if (cancelled) return;
      if (results[0].status === 'rejected') throw results[0].reason;
      const primary = results[0].value;
      const supplementary = results[1].status === 'fulfilled' ? results[1].value : null;
      setSnapshot({ dashboard: home ? primary : supplementary, reports: home ? null : primary,
        interviews: home ? supplementary : null, jobs: results[2].status === 'fulfilled' ? results[2].value : [],
        warnings: [results[1].status === 'rejected' ? (home ? 'Interviews could not be loaded. Retry to refresh appointments.' : 'Candidate details could not be loaded. Retry to enable candidate analysis.') : '', results[2].status === 'rejected' ? 'The full job list could not be loaded; available job identifiers are shown.' : ''].filter(Boolean) });
    }).catch(e => { if (!cancelled) setError(e.message || 'Analytics unavailable.'); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [endpoint, version]);
  const view = useMemo(() => {
    if (!snapshot) return {};
    try { return { data: buildAnalyticsView(snapshot, filters) }; } catch (e) { return { error: e.message }; }
  }, [snapshot, filters]);
  return { filters, setFilters, data: view.data, jobs: view.data?.analytics.jobs || [], error: error || view.error || '', loading,
    warnings: snapshot?.warnings || [], candidateDataAvailable: Array.isArray(snapshot?.dashboard?.candidates), retry: () => setVersion(v => v + 1) };
}

export function AnalyticsFilters({ filters, setFilters, jobs, data, candidateDataAvailable = true }) {
  const [search, setSearch] = useState('');
  const container = useRef(null);
  useEffect(() => { const close = event => { if (!container.current?.contains(event.target)) container.current?.querySelectorAll('details[open]').forEach(el => { el.open = false; }); }; document.addEventListener('pointerdown', close); return () => document.removeEventListener('pointerdown', close); }, []);
  const selectedJobs = filters.jobs?.length ? filters.jobs.map(String) : filters.job ? [String(filters.job)] : [];
  const toggleJob = id => setFilters(previous => ({ ...previous, job: '', jobs: selectedJobs.includes(String(id)) ? selectedJobs.filter(value => value !== String(id)) : [...selectedJobs, String(id)] }));
  const update = (key, value) => setFilters(previous => ({ ...previous, [key]: value, ...(['start', 'end'].includes(key) ? { datePreset: 'custom' } : {}) }));
  const applyPreset = preset => {
    if (preset === 'all') { update('allTime', true); return; }
    const end = new Date();
    const start = new Date(end.getFullYear(), end.getMonth(), end.getDate());
    if (preset === '7' || preset === '30' || preset === '90') start.setDate(start.getDate() - Number(preset) + 1);
    if (preset === 'month') start.setDate(1);
    if (preset === 'year') start.setMonth(0, 1);
    const local = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    setFilters(previous => ({ ...previous, allTime: false, datePreset: preset, start: local(start), end: local(end) }));
  };
  return <div className="analytics-filters analytics-filter-bar" ref={container} onKeyDown={event => { if (event.key === 'Escape') { const open = container.current.querySelector('details[open]'); if (open) { open.open = false; open.querySelector('summary').focus(); } } }} onToggle={event => { if (event.target.open) container.current.querySelectorAll('details[open]').forEach(el => { if (el !== event.target) el.open = false; }); }}>
    <details className="date-filter multi-job-filter"><summary><i className="fas fa-briefcase" aria-hidden="true" />{selectedJobs.length ? `${selectedJobs.length} jobs selected` : 'All Jobs'}<i className="fas fa-chevron-down" aria-hidden="true" /></summary>
      <div className="date-filter-popover job-filter-popover"><input type="search" aria-label="Search jobs" placeholder="Search jobs..." value={search} onChange={event => setSearch(event.target.value)} /><button type="button" className="filter-clear" onClick={() => setFilters(previous => ({ ...previous, job: '', jobs: [] }))}>Clear job selection</button><div className="job-filter-options">{jobs.filter(job => job.title.toLowerCase().includes(search.toLowerCase())).map(job => <label key={job.id}><input type="checkbox" disabled={!candidateDataAvailable} checked={selectedJobs.includes(String(job.id))} onChange={() => toggleJob(job.id)} /><span>{job.title}</span></label>)}{!jobs.some(job => job.title.toLowerCase().includes(search.toLowerCase())) && <p>No matching jobs.</p>}</div></div>
    </details>
    <label className="segment-filter"><span className="sr-only">Candidate status</span><select aria-label="Candidate status" value={filters.status || ''} disabled={!candidateDataAvailable} onChange={event => update('status', event.target.value)}><option value="">All statuses</option>{(data?.analytics.filter_statuses || []).map(value => <option key={value}>{value}</option>)}</select></label>
    <label className="segment-filter"><span className="sr-only">Candidate source</span><select aria-label="Candidate source" value={filters.source || ''} disabled={!candidateDataAvailable} onChange={event => update('source', event.target.value)}><option value="">All sources</option>{(data?.analytics.filter_sources || []).map(value => <option key={value}>{value}</option>)}</select></label>
    <details className="date-filter"><summary><i className="far fa-calendar" aria-hidden="true" />{filters.allTime ? 'All time' : `${filters.start} to ${filters.end}`}<i className="fas fa-chevron-down" aria-hidden="true" /></summary>
      <div className="date-filter-popover"><label className="date-preset-select">Date range<select aria-label="Date range preset" value={filters.allTime ? 'all' : filters.datePreset || 'custom'} disabled={!candidateDataAvailable} onChange={event => { if (event.target.value === 'custom') setFilters(previous => ({ ...previous, allTime: false, datePreset: 'custom' })); else applyPreset(event.target.value); }}><option value="all">All time</option><option value="today">Today</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option><option value="month">This month</option><option value="year">This year</option><option value="custom">Custom dates</option></select></label>
        <label>From<input type="date" value={filters.start} max={filters.end} disabled={filters.allTime || !candidateDataAvailable} onChange={e => update('start', e.target.value)} /></label>
        <label>Through<input type="date" value={filters.end} min={filters.start} disabled={filters.allTime || !candidateDataAvailable} onChange={e => update('end', e.target.value)} /></label>
        <button type="button" className="analytics-reset" onClick={() => setFilters(defaultFilters())}>Reset filters</button><small>Dates filter candidate uploads.</small>
      </div>
    </details>
    {(selectedJobs.length > 0 || filters.status || filters.source || !filters.allTime) && <button type="button" className="analytics-reset" onClick={() => setFilters(defaultFilters())}>Clear all</button>}
  </div>;
}

export function AnalyticsStatus({ loading, error, warnings = [], retry }) {
  if (loading) return <div className="analytics-status" role="status">Loading your hiring analytics...</div>;
  if (error) return <div className="analytics-status" role="alert">{error} <button onClick={retry}>Retry</button></div>;
  if (warnings.length) return <div className="analytics-warning" role="status">{warnings.join(' ')} <button onClick={retry}>Retry</button></div>;
  return null;
}

export function Panel({ title, children, action }) {
  return <section className="insight-panel"><div className="insight-panel-heading"><h2>{title}</h2>{action}</div>{children}</section>;
}

export function Empty({ children = 'No data for this period.' }) { return <p className="insight-empty">{children}</p>; }

const colors = ['#f97316', '#4b5563', '#fdba74', '#9ca3af', '#fb923c', '#d1d5db'];
export function Chart({ rows = [], kind = 'bar', label }) {
  const valid = rows.filter(r => r.count != null);
  const total = valid.reduce((s, r) => s + r.count, 0);
  if (!valid.length || !total) return <Empty>{rows.some(r => r.count == null) ? 'Not available — supporting events have not been recorded.' : 'No data for this period.'}</Empty>;
  const max = Math.max(...valid.map(r => r.count), 1);
  if (kind === 'histogram') {
    const step = Math.max(1, Math.ceil(max / 4));
    const ceiling = Math.ceil(max / step) * step;
    const ticks = Array.from({ length: ceiling / step + 1 }, (_, i) => i * step);
    const slot = 330 / valid.length;
    return <div className="insight-chart insight-chart-histogram">
      <svg viewBox="0 0 420 230" role="img" aria-label={label}>
        <title>{label}</title><desc>{valid.map(r => `${r.name}: ${r.count} candidates`).join('; ')}</desc>
        <text x="48" y="16" fontSize="12" fill="#6b7280">Candidates</text>
        {ticks.map(tick => { const y = 178 - tick / ceiling * 135; return <g key={tick}><line x1="48" x2="390" y1={y} y2={y} stroke="#f0f1f4" /><text x="36" y={y + 4} textAnchor="end" fontSize="12" fill="#6b7280">{tick}</text></g>; })}
        {valid.map((row, i) => { const x = 54 + i * slot; const height = row.count / ceiling * 135; return <g key={row.name}>
          <title>{row.name}: {row.count} candidates</title>
          <rect x={x + 8} y={178 - height} width={slot - 16} height={height} rx="4" fill="#f97316" />
          {row.count > 0 && <text x={x + slot / 2} y={168 - height} textAnchor="middle" fontSize="13" fontWeight="600">{row.count}</text>}
          <text x={x + slot / 2} y="199" textAnchor="middle" fontSize="12">{row.name}</text>
        </g>; })}
        <text x="219" y="223" textAnchor="middle" fontSize="12" fill="#6b7280">Match score (%)</text>
      </svg>
      <p className="histogram-summary"><strong>{total}</strong> {total === 1 ? 'candidate with a recorded score' : 'candidates with recorded scores'}</p>
    </div>;
  }
  if (kind === 'horizontal' || kind === 'funnel') return <div className="insight-chart chart-bars" role="img" aria-label={`${label}: ${valid.map(r => `${r.name}: ${r.count}`).join('; ')}`}>
    {valid.map((r, i) => <div key={`${r.name}-${i}`}><div className="chart-bar-heading"><span>{r.name}</span><strong>{r.count}</strong></div><svg className="chart-bar-track" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true"><rect width="100" height="10" rx="3" fill="#f3f4f6" /><rect width={r.count / max * 100} height="10" rx="3" fill={colors[i % colors.length]} /></svg></div>)}
  </div>;
  let offset = 0;
  return <div className={`insight-chart insight-chart-${kind}`}>
    <svg viewBox={kind === 'donut' ? '0 0 220 200' : '0 0 420 200'} role="img" aria-label={label}>
      <title>{label}</title><desc>{valid.map(r => `${r.name}: ${r.count}`).join('; ')}</desc>
      {kind === 'donut' ? <>
        {valid.map((r, i) => { const size = r.count / total * 100; const before = offset; offset += size; return <circle key={r.name} cx="110" cy="100" r="68" fill="none" stroke={colors[i % colors.length]} strokeWidth="30" pathLength="100" strokeDasharray={`${size} ${100 - size}`} strokeDashoffset={-before} transform="rotate(-90 110 100)" />; })}
        <text x="110" y="100" textAnchor="middle" fontSize="25" fontWeight="700">{total}</text><text x="110" y="122" textAnchor="middle" fontSize="12">Total</text>
      </> : kind === 'horizontal' ? <>{valid.map((r, i) => <g key={`${r.name}-${i}`}>
        <text x="0" y={18 + i * 180 / valid.length} fontSize="10">{r.name.length > 24 ? `${r.name.slice(0, 23)}…` : r.name}</text>
        <rect x="145" y={6 + i * 180 / valid.length} width={r.count / max * 235} height={Math.min(20, 140 / valid.length)} rx="3" fill={colors[i % colors.length]} />
        <text x={150 + r.count / max * 235} y={18 + i * 180 / valid.length} fontSize="10">{r.count}</text>
      </g>)}</> : kind === 'funnel' ? <>{valid.map((r, i) => {
        const width = r.count / max * 340; const next = Math.max(width * .85, 6); const y = 10 + i * 180 / valid.length; const height = Math.min(35, 160 / valid.length);
        return <g key={r.name}><path d={`M${210 - width / 2},${y} h${width} L${210 + next / 2},${y + height} h${-next} Z`} fill={colors[i % colors.length]} /><text x="210" y={y + height / 2 + 4} textAnchor="middle" fill={i < 2 ? '#fff' : '#1f2937'} fontSize="12">{r.count}</text></g>;
      })}</> : <>
        {[0, 1, 2, 3].map(i => <line key={i} x1="20" x2="405" y1={170 - i * 50} y2={170 - i * 50} stroke="#f1f2f4" />)}
        {kind === 'line' && valid.length > 1 && <polyline fill="none" stroke={colors[0]} strokeWidth="3" points={valid.map((r, i) => `${(valid.length === 1 ? 210 : 40 + i * 340 / (valid.length - 1))},${170 - r.count / max * 135}`).join(' ')} />}
        {valid.map((r, i) => { const width = 370 / valid.length; const x = kind === 'line' ? (valid.length === 1 ? 210 : 40 + i * 340 / (valid.length - 1)) : 25 + i * width; const y = 170 - r.count / max * 135; return <g key={`${r.name}-${i}`}>
          {kind === 'line' ? <circle cx={x} cy={y} r="4" fill={colors[0]} /> : <rect x={x} y={y} width={width * .65} height={170 - y} rx="3" fill={colors[i % colors.length]} />}
          <text x={kind === 'line' ? x : x + width * .325} y={y - 8} textAnchor="middle" fontSize="13">{r.count}</text>{kind === 'line' && <text x={x} y="194" textAnchor="middle" fontSize="12">{valid.length <= 6 || i % Math.ceil(valid.length / 6) === 0 ? r.name : ''}</text>}
        </g>; })}
      </>}
    </svg>
    {kind === 'line' && valid.length === 1 && <p className="chart-single-note">One recorded month; a trend needs more history.</p>}
    <ul className="chart-legend">{rows.map((r, i) => <li key={`${r.name}-${i}`}><span className="legend-dot" style={{ background: colors[i % colors.length] }} /><span>{r.name}</span><strong title={kind === 'donut' ? `${r.count} candidates` : undefined}>{kind === 'donut' ? `${Math.round(r.count / total * 100)}%` : r.count ?? 'N/A'}</strong>{r.reason && <small>{r.reason}</small>}</li>)}</ul>
  </div>;
}

export function SourceTrend({ rows }) {
  const sources = [...new Set(rows.flatMap(r => Object.keys(r.sources)))];
  const max = Math.max(1, ...rows.flatMap(r => Object.values(r.sources)));
  if (!rows.length) return <Empty />;
  return <div className="insight-chart"><svg viewBox="0 0 420 210" role="img" aria-label="Candidate source trend by upload month"><title>Candidate source trend</title><desc>{rows.map(r => `${r.month}: ${Object.entries(r.sources).map(([name, count]) => `${name} ${count}`).join(', ')}`).join('; ')}</desc>
    {rows.map((r, i) => { const group = 370 / rows.length; const width = group * .8 / sources.length; return <g key={r.month}>{sources.map((source, j) => <rect key={source} x={25 + group * i + width * j} y={170 - (r.sources[source] || 0) / max * 140} width={Math.max(width - 2, 1)} height={(r.sources[source] || 0) / max * 140} fill={colors[j % colors.length]} rx="2" />)}<text x={25 + group * i + group * .4} y="194" textAnchor="middle" fontSize="10">{r.month}</text></g>; })}
  </svg><ul className="chart-legend">{sources.map((name, i) => <li key={name}><span className="legend-dot" style={{ background: colors[i % colors.length] }} />{name}</li>)}</ul></div>;
}

export function Kpis({ data }) {
  return <div className="insight-kpis">{data.analytics.kpis.map((row, i) => <section className="insight-kpi" key={row.name}>
    <span className={`insight-kpi-icon tone-${i}`}><i className={`fas ${['fa-users', 'fa-file-lines', 'fa-calendar-check', 'fa-circle-check'][i]}`} aria-hidden="true" /></span>
    <div><h2>{row.name}</h2><strong>{row.count ?? '?'}</strong><small>{row.count == null ? 'Not recorded' : row.detail}</small></div>
  </section>)}</div>;
}

export function DataTable({ columns, rows, empty = 'No data for this period.' }) {
  return <div className="insight-table"><table><thead><tr>{columns.map(c => <th key={c[0]} scope="col">{c[1]}</th>)}</tr></thead><tbody>{rows.length ? rows.map((r, i) => <tr key={r.id ?? i}>{columns.map(c => <td key={c[0]}>{r[c[0]] ?? 'Not available'}</td>)}</tr>) : <tr><td colSpan={columns.length}>{empty}</td></tr>}</tbody></table></div>;
}

export function Coverage({ notes }) { return <details className="analytics-coverage"><summary>About these metrics &amp; data coverage</summary><ul>{notes.map(n => <li key={n}>{n}</li>)}</ul></details>; }
