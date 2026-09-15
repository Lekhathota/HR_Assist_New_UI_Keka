import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { SkeletonBlock } from '../components/EnterpriseFeedback.jsx';
import { AnimatedNumber } from '../components/FrontendPolish.jsx';
import {
  DASHBOARD_CACHE_KEY,
  DASHBOARD_TEAM_CACHE_KEY,
  apiGet,
  readSessionCache,
  writeSessionCache,
} from '../api.js';
import '../styles/dashboard.css';
import '../styles/dashboard_extra.css';
import flatpickr from 'flatpickr';
import 'flatpickr/dist/flatpickr.min.css';

const emptyMetrics = {
  total_jds: 0,
  total_candidates: 0,
  screened_candidates: 0,
  active_jobs: 0,
  selected_candidates: 0,
  rejected_candidates: 0,
  submissions: 0,
  client_submissions: 0,
  client_rejections: 0,
  internal_interviews: 0,
  external_interviews: 0,
  selected_bench_candidates: 0,
  waitlisted_bench_candidates: 0,
  vendor_submitted_candidates: 0,
  accepted_vendor_candidates: 0,
  remaining_vendor_requirement: 0,
};

function formatPercent(value, total) {
  return total > 0 ? Math.round((Number(value || 0) / total) * 100) : 0;
}

function Dashboard() {
  const dashboardMountKey = useRef(Date.now()).current;
  const cachedDashboardRef = useRef(readSessionCache(DASHBOARD_CACHE_KEY));
  const cachedTeamRef = useRef(readSessionCache(DASHBOARD_TEAM_CACHE_KEY));
  const cachedDashboard = cachedDashboardRef.current || {};
  const [metrics, setMetrics] = useState(cachedDashboard.metrics || emptyMetrics);
  const [recentJds, setRecentJds]                 = useState(cachedDashboard.recent_jds || []);
  const [recentCandidates, setRecentCandidates]   = useState(cachedDashboard.recent_candidates || []);
  const [recentComparisons, setRecentComparisons] = useState(cachedDashboard.recent_comparisons || []);
  const [candidates, setCandidates]               = useState(cachedDashboard.candidates || []);
  const [teamData, setTeamData]                   = useState(Array.isArray(cachedTeamRef.current) ? cachedTeamRef.current : []);
  const [searchTerm, setSearchTerm]               = useState('');
  const [dashboardLoading, setDashboardLoading]    = useState(!cachedDashboardRef.current);
  const startDateRef = useRef(null);
  const endDateRef   = useRef(null);
  const fpStart      = useRef(null);
  const fpEnd        = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const applyDashboardData = (data) => {
      if (cancelled) return;
      setMetrics(data.metrics || emptyMetrics);
      setRecentJds(data.recent_jds || []);
      setRecentCandidates(data.recent_candidates || []);
      setRecentComparisons(data.recent_comparisons || []);
      setCandidates(data.candidates || []);
    };

    apiGet('/api/dashboard').then(data => {
      writeSessionCache(DASHBOARD_CACHE_KEY, data || {});
      applyDashboardData(data || {});
    }).catch(() => {}).finally(() => {
      if (!cancelled) setDashboardLoading(false);
    });

    apiGet('/api/dashboard/team').then(data => {
      const normalized = Array.isArray(data) ? data : [];
      writeSessionCache(DASHBOARD_TEAM_CACHE_KEY, normalized);
      if (!cancelled) setTeamData(normalized);
    }).catch(() => {});

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const endDate   = new Date();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - 30);
    if (startDateRef.current) fpStart.current = flatpickr(startDateRef.current, { mode: 'single', dateFormat: 'M d, Y', defaultDate: startDate, maxDate: 'today' });
    if (endDateRef.current)   fpEnd.current   = flatpickr(endDateRef.current,   { mode: 'single', dateFormat: 'M d, Y', defaultDate: endDate,   maxDate: 'today' });
    return () => { fpStart.current?.destroy(); fpEnd.current?.destroy(); };
  }, []);

  const filteredTeam = teamData.filter(m => String(m.name || '').toLowerCase().includes(searchTerm.toLowerCase()));
  const filteredTeamTotals = filteredTeam.reduce((acc, m) => ({
    submissions: acc.submissions + Number(m.submissions || 0),
    clientSubs:  acc.clientSubs  + Number(m.clientSubs || 0),
    interviews:  acc.interviews  + Number(m.interviews || 0),
    hires:       acc.hires       + Number(m.hires || 0),
  }), { submissions: 0, clientSubs: 0, interviews: 0, hires: 0 });

  const totalCandidates = Number(metrics.total_candidates || 0);
  const selectedCount = Number(metrics.selected_candidates || 0);
  const rejectedCount = Number(metrics.rejected_candidates || 0);
  const screenedCandidates = Number(metrics.screened_candidates || selectedCount + rejectedCount);
  const selectedRate = formatPercent(selectedCount, screenedCandidates);
  const rejectedRate = formatPercent(rejectedCount, screenedCandidates);
  const activeRate = formatPercent(metrics.active_jobs, Number(metrics.total_jds || 0));
  const interviewedTotal = filteredTeamTotals.interviews;
  const teamConversionRate = formatPercent(filteredTeamTotals.hires, interviewedTotal);
  const funnelItems = [
    { label: 'Uploaded',   value: totalCandidates,                         pct: totalCandidates ? 100 : 0, detail: 'Candidate pool' },
    { label: 'Screened',   value: screenedCandidates,                      pct: totalCandidates ? formatPercent(screenedCandidates, totalCandidates) : 0, detail: 'Ready for decision' },
    { label: 'Selected',   value: selectedCount,                           pct: selectedRate,              detail: `${selectedRate}% of screened` },
    { label: 'Rejected',   value: rejectedCount,                           pct: rejectedRate,              detail: `${rejectedRate}% of screened` },
  ];
  const metricCards = [
    { label: 'Total Jobs',           val: metrics.total_jds,           detail: `${activeRate}% active`,                  icon: 'fas fa-briefcase',       cls: '',        to: '/jobs' },
    { label: 'Total Candidates',      val: metrics.total_candidates,    detail: `${recentCandidates.length} recent`,      icon: 'fas fa-users',           cls: '',        to: '/talent' },
    { label: 'Active Jobs',           val: metrics.active_jobs,         detail: `${recentJds.length} recent openings`,    icon: 'fas fa-calendar-check',  cls: 'success', to: '/jobs' },
    { label: 'Submissions',           val: metrics.submissions,         detail: 'Compared profiles',                    icon: 'fas fa-paper-plane',     cls: 'success' },
    { label: 'Client Submissions',    val: metrics.client_submissions,  detail: 'Client-ready profiles',                icon: 'fas fa-handshake',       cls: 'success' },
    { label: 'Client Rejections',     val: metrics.client_rejections,   detail: 'Client rejection data',                icon: 'fas fa-user-xmark',      cls: 'success' },
    { label: 'Internal Selections',   val: selectedCount,              detail: `${selectedRate}% selection rate`,        icon: 'fas fa-circle-check',    cls: 'warning' },
    { label: 'Internal Rejections',   val: rejectedCount,              detail: `${rejectedRate}% rejection rate`,        icon: 'fas fa-circle-xmark',    cls: 'danger'  },
    { label: 'Internal Interviews',   val: metrics.internal_interviews, detail: 'Scheduled interviews',                  icon: 'fas fa-comments',        cls: 'danger'  },
    { label: 'External Interviews',   val: metrics.external_interviews, detail: 'External interview data',               icon: 'fas fa-calendar-days',   cls: 'danger'  },
  ];
  const formatDate = value => (value ? String(value).slice(0, 10) : '');

  return (
    <Layout>
      <div className="dashboard-container">
        <h1><i className="fas fa-chart-line"></i> Dashboard</h1>

        {/* Metrics */}
        {dashboardLoading ? (
          <SkeletonBlock variant="metrics" count={10} />
        ) : (
        <div className="metrics">
          {metricCards.map((m, index) => {
            const className = `dashboard-metric-card${m.cls ? ` ${m.cls}` : ''}${m.to ? ' dashboard-metric-link' : ''}`;
            const content = (
              <>
                <i className={`dashboard-metric-icon ${m.icon}`}></i>
                <AnimatedNumber key={`${dashboardMountKey}-${m.label}`} value={m.val} alwaysAnimate />
                <h4>{m.label}</h4>
                <small>{m.detail}</small>
              </>
            );

            return m.to ? (
              <Link key={m.label} to={m.to} className={className} aria-label={`Open ${m.label}`} style={{ '--delay': `${index * 0.035}s` }}>
                {content}
              </Link>
            ) : (
              <div key={m.label} className={className} style={{ '--delay': `${index * 0.035}s` }}>{content}</div>
            );
          })}
        </div>
        )}

        <div className="workflow-kpi-strip" aria-label="Automated fulfilment metrics">
          {[
            ['Bench Selected', metrics.selected_bench_candidates || 0, 'fas fa-user-check'],
            ['Bench Waitlisted', metrics.waitlisted_bench_candidates || 0, 'fas fa-list'],
            ['Vendor Submitted', metrics.vendor_submitted_candidates || 0, 'fas fa-paper-plane'],
            ['Vendor Accepted', metrics.accepted_vendor_candidates || 0, 'fas fa-handshake'],
            ['Open Shortage', metrics.remaining_vendor_requirement || 0, 'fas fa-triangle-exclamation'],
          ].map(([label, value, icon]) => (
            <div key={label}>
              <i className={icon}></i>
              <span><strong>{value}</strong><small>{label}</small></span>
            </div>
          ))}
        </div>

        {/* Analytics */}
        <h2><i className="fas fa-chart-bar"></i> Recruitment Analytics</h2>
        <div className="grid grid-2">
          <div className="analytics-card">
            <h3>JD-wise Performance</h3>
            <p>Selection vs Rejection by Job Description</p>
            <ul className="list-group">
              {recentJds.map(jd => {
                const sel = jd.selected_count ?? candidates.filter(c => c.jd_id === jd.id && c.status === 'Selected').length;
                const rej = jd.rejected_count ?? candidates.filter(c => c.jd_id === jd.id && c.status === 'Rejected').length;
                return (
                  <li key={jd.id} className="list-group-item">
                    <strong>{jd.title}</strong>
                    <div className="dashboard-jd-item-status">
                      Selected: <span className="badge badge-success">{sel}</span>{' '}
                      Rejected: <span className="badge badge-danger">{rej}</span>
                    </div>
                  </li>
                );
              })}
              {recentJds.length === 0 && <li className="list-group-item list-item-empty">No JDs yet</li>}
            </ul>
          </div>
          <div className="analytics-card">
            <h3>Hiring Funnel</h3>
            <div className="dashboard-funnel-stats" aria-label="Funnel conversion summary">
              <div>
                <strong>{selectedRate}%</strong>
                <span>Selection Rate</span>
              </div>
              <div>
                <strong>{rejectedRate}%</strong>
                <span>Rejection Rate</span>
              </div>
              <div>
                <strong>{screenedCandidates}</strong>
                <span>Total Screened</span>
              </div>
            </div>
            <p>Uploaded → Screened → Selected → Rejected</p>
            <div className="funnel-section">
              {funnelItems.map(item => (
                <div key={item.label} className="funnel-item">
                  <div className="progress-label">
                    <span>{item.label}<small>{item.detail}</small></span>
                    <span>{item.value}<em>{item.pct}%</em></span>
                  </div>
                  <div className="progress"><div className="progress-bar dashboard-progress-bar" style={{ width: `${item.pct}%` }}></div></div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Recent Activity */}
        <h2 className="dashboard-recent-activity-title">
          <i className="fas fa-history"></i> Recent Activity
        </h2>
        <div className="grid grid-3">
          <div className="activity-card">
            <h3 className="activity-card-title"><i className="fas fa-file-alt"></i> Recent Job Descriptions</h3>
            <ul className="list-group">
              {recentJds.length > 0 ? recentJds.map(jd => (
                <li key={jd.id} className="list-group-item">
                  <Link to={`/jobs/${jd.id}`}>{jd.title}</Link>
                  <div className="dashboard-jd-item-meta">
                    <i className="fas fa-calendar-alt"></i> {formatDate(jd.created_date || jd.created || jd.created_at || jd.updated_at)}
                  </div>
                </li>
              )) : <li className="list-group-item list-item-empty">No recent JDs</li>}
            </ul>
          </div>
          <div className="activity-card">
            <h3 className="activity-card-title"><i className="fas fa-users"></i> Recent Candidates</h3>
            <ul className="list-group">
              {recentCandidates.length > 0 ? recentCandidates.map(c => (
                <li key={c.id} className="list-group-item">
                  <Link to={`/talent/${c.id}`}>{c.name}</Link>
                  <div className="dashboard-jd-item-meta">
                    <span className="badge badge-primary">{c.status}</span>
                  </div>
                </li>
              )) : <li className="list-group-item list-item-empty">No recent candidates</li>}
            </ul>
          </div>
          <div className="activity-card">
            <h3 className="activity-card-title"><i className="fas fa-exchange-alt"></i> Latest Comparisons</h3>
            <ul className="list-group">
              {recentComparisons.length > 0 ? recentComparisons.map((comp, i) => (
                <li key={i} className="list-group-item">
                  <strong className="dashboard-comparison-title">JD: {comp.jd_title}</strong>
                  <div className="dashboard-jd-item-meta">
                    <i className="fas fa-calendar-alt"></i> {formatDate(comp.date)}
                  </div>
                </li>
              )) : <li className="list-group-item list-item-empty">No comparisons yet</li>}
            </ul>
          </div>
        </div>

        {/* Team Performance — live from backend */}
        <div className="jsip-report-container">
          <div className="dbBox" id="report-box5001">
            <div className="dbBoxHeadView">
              <div className="dbBoxTitleSection">
                <h3 className="dbBoxTitle"><i className="fas fa-users"></i> Team Performance Report</h3>
                <p className="dbBoxSubtitle">Recruitment team submissions and placements summary</p>
              </div>
              <div className="dbBAction">
                <div className="date-range-picker-container">
                  <div className="date-range-group">
                    <label className="date-label"><i className="fas fa-calendar-check"></i> From</label>
                    <input type="text" ref={startDateRef} className="date-input" placeholder="Select start date" readOnly />
                  </div>
                  <div className="date-range-divider"><i className="fas fa-arrow-right"></i></div>
                  <div className="date-range-group">
                    <label className="date-label"><i className="fas fa-calendar-check"></i> To</label>
                    <input type="text" ref={endDateRef} className="date-input" placeholder="Select end date" readOnly />
                  </div>
                  <button className="date-reset-btn" title="Reset dates" onClick={(e) => { e.preventDefault(); const s = new Date(); s.setDate(s.getDate() - 30); fpStart.current?.setDate(s); fpEnd.current?.setDate(new Date()); }}>
                    <i className="fas fa-redo-alt"></i>
                  </button>
                </div>
              </div>
            </div>
            <div className="dbBoxBody">
              <div className="custom-loading-block">
                <div className="dataTables_wrapper no-footer">
                  <div className="dashboard-team-overview" aria-label="Team performance snapshot">
                    <div>
                      <i className="fas fa-paper-plane"></i>
                      <span><strong>{filteredTeamTotals.submissions}</strong><small>Submissions</small></span>
                    </div>
                    <div>
                      <i className="fas fa-handshake"></i>
                      <span><strong>{filteredTeamTotals.clientSubs}</strong><small>Client Submissions</small></span>
                    </div>
                    <div>
                      <i className="fas fa-comment-dots"></i>
                      <span><strong>{filteredTeamTotals.interviews}</strong><small>Interviews</small></span>
                    </div>
                    <div>
                      <i className="fas fa-briefcase"></i>
                      <span><strong>{filteredTeamTotals.hires}</strong><small>Hires</small></span>
                    </div>
                    <div>
                      <i className="fas fa-chart-line"></i>
                      <span><strong>{teamConversionRate}%</strong><small>Interview to Hire</small></span>
                    </div>
                  </div>
                  <div className="report_controls">
                    <div className="dataTables_length">
                      <label><i className="fas fa-list"></i> Show{' '}
                        <select><option value="10">10</option><option value="25">25</option><option value="50">50</option></select> entries
                      </label>
                    </div>
                    <div className="dataTables_filter">
                      <label><i className="fas fa-search"></i>{' '}
                        <input type="search" className="search-box" placeholder="Search team members..."
                          value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
                      </label>
                    </div>
                  </div>
                  <div className="table-responsive">
                    <table className="table_block dataTable no-footer">
                      <thead>
                        <tr>
                          <th><span><i className="fas fa-user"></i> User Name</span></th>
                          <th className="text-align-right"><span><i className="fas fa-paper-plane"></i> Submissions</span></th>
                          <th className="text-align-right"><span><i className="fas fa-handshake"></i> Client Submissions</span></th>
                          <th className="text-align-right"><span><i className="fas fa-comment-dots"></i> Interviews</span></th>
                          <th className="text-align-right"><span><i className="fas fa-briefcase"></i> Hires</span></th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredTeam.length > 0 ? filteredTeam.map((m, i) => (
                          <tr key={m.name} className={i % 2 === 0 ? 'odd' : 'even'}>
                            <td>{m.name}</td>
                            <td className="text-align-right">{m.submissions}</td>
                            <td className="text-align-right">{m.clientSubs}</td>
                            <td className="text-align-right">{m.interviews}</td>
                            <td className="text-align-right">{m.hires}</td>
                          </tr>
                        )) : (
                          <tr><td colSpan="5" className="list-item-empty">No team data available</td></tr>
                        )}
                      </tbody>
                      <tfoot className="table-footer">
                        <tr>
                          <td><strong>Total</strong></td>
                          <td className="text-align-right"><strong>{filteredTeamTotals.submissions}</strong></td>
                          <td className="text-align-right"><strong>{filteredTeamTotals.clientSubs}</strong></td>
                          <td className="text-align-right"><strong>{filteredTeamTotals.interviews}</strong></td>
                          <td className="text-align-right"><strong>{filteredTeamTotals.hires}</strong></td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                  <div className="pagination-section">
                    <div className="dataTables_info">Showing 1 to {filteredTeam.length} of {teamData.length} entries</div>
                    <div className="dataTables_paginate paging_simple_numbers">
                      <span className="paginate_button previous disabled" aria-hidden="true"><i className="fas fa-chevron-left"></i></span>
                      <span><span className="paginate_button current">1</span></span>
                      <span className="paginate_button next disabled" aria-hidden="true"><i className="fas fa-chevron-right"></i></span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
}

export default Dashboard;
