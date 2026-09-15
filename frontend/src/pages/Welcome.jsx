import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { AnimatedNumber } from '../components/FrontendPolish.jsx';
import { apiGet } from '../api.js';
import '../styles/welcome.css';

const LOGIN_USER_KEY = 'recruitment_assist_user';

function useWelcomeReveal() {
  useEffect(() => {
    const elements = Array.from(document.querySelectorAll('.welcome-reveal'));
    if (!elements.length) return undefined;

    const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (prefersReducedMotion) {
      elements.forEach((el) => el.classList.add('welcome-reveal-visible'));
      return undefined;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('welcome-reveal-visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.18, rootMargin: '0px 0px -8% 0px' }
    );

    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);
}

function readStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(LOGIN_USER_KEY) || '{}') || {};
  } catch {
    return {};
  }
}

function sameDay(value, date) {
  if (!value) return false;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value).slice(0, 10) === date.toISOString().slice(0, 10);
  return parsed.toDateString() === date.toDateString();
}

function formatDate(value) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value).slice(0, 10);
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function Welcome() {
  const [user] = useState(readStoredUser);
  const [dashboard, setDashboard] = useState(null);
  const [interviews, setInterviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [briefingError, setBriefingError] = useState('');

  useWelcomeReveal();

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([apiGet('/api/dashboard'), apiGet('/api/interviews')])
      .then(([dashboardResult, interviewResult]) => {
        if (cancelled) return;
        if (dashboardResult.status === 'fulfilled') {
          setDashboard(dashboardResult.value || {});
        } else {
          setBriefingError('Briefing unavailable');
        }
        if (interviewResult.status === 'fulfilled') {
          setInterviews(Array.isArray(interviewResult.value) ? interviewResult.value : []);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const metrics = dashboard?.metrics || {};
  const recentJds = dashboard?.recent_jds || [];
  const recentCandidates = dashboard?.recent_candidates || [];
  const recentComparisons = dashboard?.recent_comparisons || [];
  const todayInterviews = useMemo(() => {
    const today = new Date();
    return interviews.filter((item) => sameDay(item.interview_start || item.start || item.date, today));
  }, [interviews]);

  const displayName = user.username || user.role || 'Recruiter';
  const moduleRows = [
    ['Resume Intelligence', 'Parsing and screening pipeline'],
    ['Candidate Matching', 'JD fit and recommendation layer'],
    ['Interview Scheduler', 'Calendar and outreach workflow'],
    ['Hiring Insights', 'Reports and decision intelligence'],
  ];
  const actionCards = [
    { label: 'Create Job Description', hint: 'Start a new hiring requirement', icon: 'fas fa-file-circle-plus', to: '/jobs/create' },
    { label: 'Analyze Resumes', hint: 'Screen candidates against a JD', icon: 'fas fa-code-compare', to: '/analyze' },
    { label: 'View Candidates', hint: 'Open the talent repository', icon: 'fas fa-users', to: '/talent' },
    { label: 'Schedule Interviews', hint: 'Coordinate candidate conversations', icon: 'fas fa-calendar-days', to: '/interviews' },
    { label: 'Open Reports', hint: 'Review hiring intelligence', icon: 'fas fa-chart-bar', to: '/insights' },
  ];
  const briefingCards = [
    { label: 'Active Jobs', value: metrics.active_jobs || 0, icon: 'fas fa-briefcase' },
    { label: 'Total Candidates', value: metrics.total_candidates || 0, icon: 'fas fa-users' },
    { label: 'Selected', value: metrics.selected_candidates || 0, icon: 'fas fa-circle-check' },
    { label: 'Rejected', value: metrics.rejected_candidates || 0, icon: 'fas fa-circle-xmark' },
    { label: 'Interviews Today', value: todayInterviews.length, icon: 'fas fa-calendar-check' },
  ];
  const pipelineSteps = [
    { label: 'Job Intake', detail: 'Capture role requirements', icon: 'fas fa-clipboard-list' },
    { label: 'Screen', detail: 'Parse and evaluate resumes', icon: 'fas fa-file-waveform' },
    { label: 'Match', detail: 'Rank candidates by fit', icon: 'fas fa-code-compare' },
    { label: 'Interview', detail: 'Coordinate conversations', icon: 'fas fa-calendar-check' },
    { label: 'Decide', detail: 'Move with hiring clarity', icon: 'fas fa-circle-check' },
  ];

  return (
    <Layout>
      <div className="welcome-container">
        <section className="welcome-hero welcome-reveal">
          <div className="welcome-hero-copy">
            <img src="/ShimentoX-Light-Logo.webp" alt="ShimentoX" className="welcome-hero-logo" />
            <p className="welcome-eyebrow">Talent Intelligence Command Center</p>
            <h1>Welcome back, {displayName}</h1>
            <p className="welcome-hero-text">Your recruiting systems are online. Review today&apos;s briefing, launch critical workflows, or enter the dashboard.</p>
          </div>
          <div className="welcome-module-panel" aria-label="AI module readiness">
            {moduleRows.map(([name, detail], index) => (
              <div key={name} className="welcome-module-row" style={{ '--delay': `${index * 0.14}s` }}>
                <span className="welcome-module-dot"></span>
                <span>
                  <strong>{name}</strong>
                  <small>{detail}</small>
                </span>
                <em>Online</em>
              </div>
            ))}
          </div>
        </section>

        <section className="welcome-pipeline welcome-reveal" aria-label="Recruitment intelligence flow">
          <div className="welcome-section-head">
            <div>
              <p className="welcome-eyebrow">Recruitment Intelligence Flow</p>
              <h2>From requirement to hiring decision</h2>
            </div>
          </div>
          <div className="welcome-pipeline-track">
            {pipelineSteps.map((step, index) => (
              <div key={step.label} className="welcome-pipeline-step" style={{ '--delay': `${index * 0.12}s` }}>
                <span className="welcome-pipeline-icon"><i className={step.icon}></i></span>
                <strong>{step.label}</strong>
                <small>{step.detail}</small>
              </div>
            ))}
          </div>
        </section>

        <section className="welcome-section welcome-reveal">
          <div className="welcome-section-head">
            <div>
              <p className="welcome-eyebrow">Daily Briefing</p>
              <h2>Today&apos;s hiring signal</h2>
            </div>
            {briefingError && <span className="welcome-briefing-error">{briefingError}</span>}
          </div>
          <div className="welcome-briefing-grid">
            {briefingCards.map((item, index) => (
              <div key={item.label} className="welcome-briefing-card" style={{ '--delay': `${index * 0.07}s` }}>
                <i className={item.icon}></i>
                <strong>{loading ? '-' : <AnimatedNumber value={item.value} />}</strong>
                <span>{item.label}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="welcome-section welcome-reveal">
          <div className="welcome-section-head">
            <div>
              <p className="welcome-eyebrow">Launchpad</p>
              <h2>Quick actions</h2>
            </div>
          </div>
          <div className="welcome-actions-grid">
            {actionCards.map((action, index) => (
              <Link key={action.label} to={action.to} className="welcome-action-card" style={{ '--delay': `${index * 0.06}s` }}>
                <i className={action.icon}></i>
                <span>
                  <strong>{action.label}</strong>
                  <small>{action.hint}</small>
                </span>
              </Link>
            ))}
          </div>
        </section>

        <section className="welcome-section welcome-reveal">
          <div className="welcome-section-head">
            <div>
              <p className="welcome-eyebrow">Recent Activity</p>
              <h2>Latest movement</h2>
            </div>
          </div>
          <div className="welcome-activity-grid">
            <ActivityList title="Recent JDs" icon="fas fa-file-alt" items={recentJds} empty="No recent JDs" render={(jd) => (
              <Link to={`/jobs/${jd.id}`}>{jd.title || 'Untitled JD'}<small>{formatDate(jd.created_date || jd.created || jd.created_at)}</small></Link>
            )} />
            <ActivityList title="Recent Candidates" icon="fas fa-users" items={recentCandidates} empty="No recent candidates" render={(candidate) => (
              <Link to={`/talent/${candidate.id}`}>{candidate.name || 'Candidate'}<small>{candidate.status || 'Pending'}</small></Link>
            )} />
            <ActivityList title="Latest Comparisons" icon="fas fa-code-compare" items={recentComparisons} empty="No comparisons yet" render={(comparison, index) => (
              <span key={index}>JD: {comparison.jd_title || 'Untitled'}<small>{formatDate(comparison.date || comparison.comparison_date)}</small></span>
            )} />
          </div>
        </section>
      </div>
    </Layout>
  );
}

function ActivityList({ title, icon, items, empty, render }) {
  return (
    <div className="welcome-activity-card">
      <h3><i className={icon}></i>{title}</h3>
      <div className="welcome-activity-list">
        {items.length > 0 ? items.slice(0, 4).map((item, index) => (
          <div key={item.id || `${title}-${index}`} className="welcome-activity-item" style={{ '--delay': `${index * 0.06}s` }}>
            {render(item, index)}
          </div>
        )) : <p className="welcome-empty">{empty}</p>}
      </div>
    </div>
  );
}

export default Welcome;
