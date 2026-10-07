import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { apiGet } from '../api.js';
import '../styles/clients.css';
import '../styles/clients_page.css';

function ClientProject() {
  const { clientId, projectId } = useParams();
  const navigate = useNavigate();
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    apiGet(`/api/clients/${clientId}`)
      .then((data) => setDetails(data))
      .catch((err) => setError(err.message || 'Could not load project.'))
      .finally(() => setLoading(false));
  }, [clientId]);

  const client = details?.client || null;
  const projects = useMemo(() => (Array.isArray(details?.projects) ? details.projects : []), [details]);
  const project = useMemo(
    () => projects.find((item) => String(item.id) === String(projectId)) || null,
    [projects, projectId]
  );
  const benchCards = Array.isArray(project?.bench_cards) ? project.bench_cards : [];
  const requiredRoleCards = Array.isArray(project?.required_role_cards) ? project.required_role_cards : [];

  return (
    <Layout>
      <div className="clients-page project-detail-page cl-page">
        <div className="project-detail-header">
          <div>
            {client?.client_account_id && <span className="client-account-id">{client.client_account_id}</span>}
            <h1>{project?.name || 'Project'}</h1>
            <p>{client?.name ? `${client.name} · ` : ''}Required roles, active jobs and bench candidates for this project.</p>
          </div>
          <button type="button" className="btn btn-secondary" onClick={() => navigate('/clients')}>
            <i className="fas fa-arrow-left"></i> Back to Clients
          </button>
        </div>

        {loading ? (
          <div className="clients-empty">Loading project...</div>
        ) : error ? (
          <div className="clients-empty">{error}</div>
        ) : !project ? (
          <div className="clients-empty">Project not found.</div>
        ) : (
          <>
            <section className="client-overview-card project-overview-card">
              <div className="project-overview-main">
                <div className="project-overview-title-row">
                  <div>
                    <span className="client-account-id">PROJECT</span>
                    <h2>{project.name}</h2>
                    {project.notes && <p>{project.notes}</p>}
                  </div>
                  {project.status && (
                    <span className={`client-status status-${String(project.status).toLowerCase()}`}>
                      {project.status}
                    </span>
                  )}
                </div>
                <div className="client-info-grid project-info-grid">
                  {[
                    ['Client', client?.name || 'Not set'],
                    ['Project Type', project.project_type || 'Not set'],
                    ['Total Jobs', project.total_jobs ?? 0],
                    ['Upcoming Interviews', project.interviews ?? 0],
                    ['Industry', client?.industry || 'Not set'],
                    ['Account Owner', client?.account_owner || 'Not set'],
                  ].map(([label, value]) => (
                    <div key={label} className="client-info-item">
                      <span>{label}</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <section className="client-metrics">
              {[
                ['Required Jobs', project.active_jobs || 0, 'fas fa-briefcase'],
                ['Required Roles', requiredRoleCards.length, 'fas fa-clipboard-list'],
                ['Bench Candidates', project.current_candidates || 0, 'fas fa-user-check'],
                ['Total Candidates', project.total_candidates || 0, 'fas fa-users'],
              ].map(([label, value, icon]) => (
                <div key={label} className="client-metric-card">
                  <i className={icon}></i>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </section>

            <section className="client-projects">
              <div className="client-section-title">
                <h2><i className="fas fa-user-plus"></i> Required Roles</h2>
                <span>{requiredRoleCards.length} role{requiredRoleCards.length === 1 ? '' : 's'}</span>
              </div>
              <div className="client-role-grid required-role-grid">
                {requiredRoleCards.map((card) => (
                  <article key={card.role} className={`client-role-card required-card${card.priority ? ` priority-${String(card.priority).toLowerCase()}` : ''}`}>
                    <div className="client-role-card-head">
                      <strong>{card.role}</strong>
                      {card.priority && <span title="Based on how many posts are still unfilled">{card.priority} priority</span>}
                    </div>
                    <div className="client-role-counts">
                      <div>
                        <span>Required</span>
                        <strong>{card.required_count || 0}</strong>
                      </div>
                      <div>
                        <span>Available</span>
                        <strong>{card.available_count || 0}</strong>
                      </div>
                      <div>
                        <span>Gap</span>
                        <strong>{card.gap || 0}</strong>
                      </div>
                    </div>
                    <div className="client-gap-bar" aria-hidden="true">
                      <span style={{ width: `${Math.min(100, ((card.available_count || 0) / Math.max(1, card.required_count || 1)) * 100)}%` }}></span>
                    </div>
                    <div className="client-chip-row">
                      {(card.skills || []).slice(0, 6).map((skill) => (
                        <span key={skill}>{skill}</span>
                      ))}
                      {(card.skills || []).length === 0 && <span>Skills pending</span>}
                    </div>
                  </article>
                ))}
                {requiredRoleCards.length === 0 && <div className="clients-empty compact">No required roles yet. Required jobs will appear here as role demand.</div>}
              </div>
            </section>

            <section className="client-projects">
              <div className="client-section-title">
                <h2><i className="fas fa-layer-group"></i> Bench</h2>
                <span>{benchCards.length} role group{benchCards.length === 1 ? '' : 's'}</span>
              </div>
              <div className="client-role-grid">
                {benchCards.map((card) => (
                  <article key={card.role} className="client-role-card">
                    <div className="client-role-card-head">
                      <strong>{card.role}</strong>
                      <span>{card.count} on bench</span>
                    </div>
                    <div className="client-role-metric-row">
                      <span>Availability</span>
                      <strong>{card.availability || '—'}</strong>
                    </div>
                    <div className="client-role-metric-row">
                      <span>Avg Match</span>
                      <strong>{card.avg_match || 0}%</strong>
                    </div>
                    <div className="client-chip-row">
                      {(card.skills || []).slice(0, 6).map((skill) => (
                        <span key={skill}>{skill}</span>
                      ))}
                      {(card.skills || []).length === 0 && <span>Skills pending</span>}
                    </div>
                  </article>
                ))}
                {benchCards.length === 0 && <div className="clients-empty compact">No internal bench candidates grouped for this project yet.</div>}
              </div>
            </section>
          </>
        )}
      </div>
    </Layout>
  );
}

export default ClientProject;
