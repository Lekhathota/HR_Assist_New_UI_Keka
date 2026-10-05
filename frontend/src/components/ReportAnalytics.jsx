import React, { useState } from 'react';
import { Panel, Chart, DataTable, Coverage, Empty } from './Analytics.jsx';
import HomeDetails from './HomeDetails.jsx';

const tabs = ['Hiring Overview', 'Job Analysis', 'Candidate Analytics', 'Skill Gap Analysis'];
export default function ReportAnalytics({ data, filters }) {
  const [tab, setTab] = useState(0);
  const { analytics: a, metrics, jd_reports: jobs, skill_gaps: skills } = data;
  const visiblePipeline = a.pipeline.filter(row => row.name !== 'Rejected');
  const basis = a.pipeline.find(r => r.name === 'Uploaded')?.count;
  return <>
    <div className="reports-toolbar"><div className="insight-tabs" role="tablist" aria-label="Report views">{tabs.map((name, i) => <button key={name} role="tab" id={`report-tab-${i}`} aria-controls="report-panel" aria-selected={tab === i} tabIndex={tab === i ? 0 : -1} onClick={() => setTab(i)} onKeyDown={event => {
      const next = event.key === 'ArrowRight' ? (i + 1) % 4 : event.key === 'ArrowLeft' ? (i + 3) % 4 : event.key === 'Home' ? 0 : event.key === 'End' ? 3 : null;
      if (next !== null) { event.preventDefault(); setTab(next); document.getElementById(`report-tab-${next}`)?.focus(); }
    }}>{name}</button>)}</div>{tab !== 3 && filters}</div>
    <div role="tabpanel" id="report-panel" aria-labelledby={`report-tab-${tab}`}>
      {tab === 0 && <>
        <div className="insight-grid three reports-overview reports-charts">
          <Panel title="Candidates by Job Role"><Chart kind="horizontal" rows={jobs.slice(0, 6).map(j => ({ name: j.title, count: j.total_screened }))} label="Candidates by job; first six jobs" /></Panel>
          <Panel title="Candidate Upload Trend"><Chart rows={a.trend} kind="line" label="Candidate uploads by month" /></Panel>
          <Panel title="Screening Outcomes"><Chart kind="funnel" rows={visiblePipeline} label="Uploaded, screened and selected candidates" /></Panel>
        </div>
        <Panel title="Screening Percentages"><p className="insight-caption">Percentages use uploaded candidates as the baseline. Selected represents screening selections, not hires.</p><DataTable columns={visiblePipeline.map(r => [r.name, r.name])} rows={[Object.fromEntries(visiblePipeline.map(r => [r.name, r.count == null || !basis ? 'Not available' : `${(r.count / basis * 100).toFixed(1)}%`]))]} /></Panel>
        <Panel title="Recruitment Summary"><DataTable columns={[["total_jobs", "Total Jobs"], ["active_jobs", "Active Jobs"], ["total_candidates", "Candidates"], ["rate", "Selection Rate"]]} rows={[{ ...metrics, rate: metrics.selection_rate == null ? '?' : `${metrics.selection_rate}%` }]} /></Panel>
      </>}
      {tab === 1 && <><Panel title="Job Performance"><DataTable columns={[["title", "Job Title"], ["total_screened", "Candidates"], ["selected", "Selected"], ["rejected", "Rejected"], ["avg_match", "Avg Match %"], ["rate", "Selection Rate"]]} rows={jobs.map(j => ({ ...j, rate: j.total_screened ? `${(j.selected / j.total_screened * 100).toFixed(1)}%` : '?' }))} /></Panel><details className="home-operational"><summary>Additional operational totals &amp; team report (all time)</summary><HomeDetails /></details></>}
      {tab === 2 && (a.candidate_data_available ? <div className="insight-grid three reports-charts"><Panel title="Match Score Distribution"><Chart kind="histogram" rows={a.score_bands} label="Candidate match score bands" /></Panel><Panel title="Candidate Status"><Chart rows={a.status_breakdown} kind="donut" label="Recorded candidate outcomes" /></Panel><Panel title={a.distribution_title}><Chart rows={a.distribution} kind="horizontal" label={a.distribution_title} /></Panel></div> : <Empty>Candidate details could not be loaded. Retry to load this analysis.</Empty>)}
      {tab === 3 && <Panel title="Skill Gap Analysis"><p className="insight-caption">All-time skill demand and availability from the existing report. Candidate date filters do not apply to this aggregate.</p><DataTable columns={[["name", "Skill"], ["jd_count", "JD Demand"], ["candidate_count", "Available Candidates"], ["gap", "Gap"], ["status", "Status"]]} rows={skills.map(r => ({ ...r, gap: r.jd_count - r.candidate_count, status: r.jd_count > r.candidate_count ? 'Shortage' : r.jd_count < r.candidate_count ? 'Surplus' : 'Balanced' }))} /></Panel>}
      <Coverage notes={a.notes} />
    </div>
  </>;
}
