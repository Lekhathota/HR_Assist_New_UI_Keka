import React from 'react';
import { Link } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { useAnalytics, AnalyticsFilters, AnalyticsStatus, Panel, Chart, Kpis, DataTable, Coverage } from '../components/Analytics.jsx';
import { getCurrentRole, roleCanAccess } from '../roleAccess.js';
import { readUser, displayName, initials } from '../utils/userDisplay.js';

function Person({ name }) { return <span className="table-person"><span className="person-avatar" aria-hidden="true">{initials(name)}</span>{name}</span>; }
function eventTime(value) { const date = new Date(value); return value && !Number.isNaN(date.getTime()) ? date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '?'; }
export default function Welcome() {
  const state = useAnalytics('/api/dashboard');
  const { data } = state;
  const can = path => roleCanAccess(getCurrentRole(), path);
  const actions = [['Create Job Description', '/jobs/create', 'fa-briefcase'], ['Analyze Resumes', '/analyze', 'fa-code-compare'], ['View Candidates', '/talent', 'fa-users'], ['Schedule Interviews', '/hiring-pipeline', 'fa-calendar'], ['Open Reports', '/insights', 'fa-chart-bar']];
  const a = data?.analytics;
  return <Layout><div className="insights-page home-page">
    <div className="insights-heading"><div><h1>Welcome back, {displayName(readUser()).split(' ')[0]}!</h1><p>Here's an overview of your hiring activities.</p></div><AnalyticsFilters {...state} /></div>
    <AnalyticsStatus {...state} />
    {data && <>
      <Kpis data={data} />
      <div className="insight-grid three home-charts">
        <Panel title="Hiring Pipeline"><Chart rows={a.pipeline.filter(row => row.name !== 'Rejected')} label="Recorded screening outcomes" /></Panel>
        <Panel title={a.distribution_title}><Chart rows={a.distribution} kind="donut" label={a.distribution_title} /></Panel>
        <Panel title={a.trend.length ? 'Candidate Trend' : 'Match Score Distribution'}>{a.trend.length ? <Chart rows={a.trend} kind="line" label="Candidates uploaded by month" /> : <Chart rows={a.score_bands} label="Recorded match scores" />}</Panel>
      </div>
      <div className="insight-grid two home-activity">
        <Panel title="Recent Activity" action={can('/talent') && <Link to="/talent">View candidates</Link>}>
          <DataTable columns={[["name", "Candidate / Job"], ["activity", "Activity"], ["job", "Job Role"], ["time", "Time"]]} rows={a.activities.map(r => ({ ...r, name: r.candidate_id && can('/talent') ? <Link to={`/talent/${r.candidate_id}`}><Person name={r.name} /></Link> : <Person name={r.name} />, activity: <span className="activity-label"><i className={`fas ${r.icon}`} aria-hidden="true" />{r.activity}</span>, time: eventTime(r.time) }))} />
        </Panel>
        <Panel title="Upcoming Interviews" action={can('/hiring-pipeline') && <Link to="/hiring-pipeline">View all</Link>}>
          {a.interviews_error ? <p role="alert" className="insight-empty">{a.interviews_error}<button onClick={state.retry}>Retry</button></p> : <DataTable columns={[["candidate", "Candidate"], ["job", "Job Role"], ["date", "Date & Time"], ...(a.upcoming_interviews.some(r => r.interviewer) ? [["interviewer", "Interviewer"]] : [])]} rows={a.upcoming_interviews.map(r => ({ id: r.id, candidate: <Person name={r.candidate_name || `Candidate #${r.candidate_id}`} />, job: r.job_role || r.jd_title || a.jobs.find(j => String(j.id) === String(r.jd_id))?.title || '?', date: <span className="interview-date">{eventTime(r.interview_start)}<small>{new Date(r.interview_start).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}</small></span>, interviewer: r.interviewer || '?' }))} empty="No upcoming interviews scheduled." />}
        </Panel>
      </div>
      <Coverage notes={a.notes} />
    </>}
    <nav className="home-quick-actions" aria-label="Recruiting quick actions">{actions.filter(([, path]) => can(path)).map(([label, path, icon]) => <Link key={path} to={path}><i className={`fas ${icon}`} aria-hidden="true" />{label}<span aria-hidden="true">&rarr;</span></Link>)}</nav>
  </div></Layout>;
}
