import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { toast } from '../components/EnterpriseFeedback.jsx';
import { apiGet, apiPost } from '../api.js';
import '../styles/clients.css';

const EMPTY_CLIENT_FORM = {
  name: '',
  client_account_id: '',
  industry: '',
  location: '',
  contact_person: '',
  contact_email: '',
  contact_phone: '',
  account_owner: '',
  notes: '',
};

function isShimentoXClient(client) {
  return String(client?.client_account_id || '').trim().toUpperCase() === 'SHIMENTOX';
}

function isShimentoXInternalProject(project) {
  return String(project?.name || '').trim().toLowerCase() === 'shimentox internal';
}

function Clients() {
  const navigate = useNavigate();
  const [clients, setClients] = useState([]);
  const [activeClientId, setActiveClientId] = useState(null);
  const [details, setDetails] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(EMPTY_CLIENT_FORM);

  const loadClients = () => {
    setLoading(true);
    setError('');
    apiGet('/api/clients')
      .then((data) => {
        const rows = Array.isArray(data.clients) ? data.clients : [];
        setClients(rows);
        setActiveClientId((current) => current || rows[0]?.id || null);
      })
      .catch((err) => setError(err.message || 'Could not load clients.'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadClients();
  }, []);

  useEffect(() => {
    if (!activeClientId) {
      setDetails(null);
      return;
    }
    apiGet(`/api/clients/${activeClientId}`)
      .then((data) => {
        setDetails(data);
      })
      .catch(() => {
        setDetails(null);
      });
  }, [activeClientId]);

  const filteredClients = useMemo(() => {
    const needle = searchTerm.trim().toLowerCase();
    if (!needle) return clients;
    return clients.filter((client) => (
      `${client.name || ''} ${client.client_account_id || ''} ${client.industry || ''} ${client.contact_person || ''}`
        .toLowerCase()
        .includes(needle)
    ));
  }, [clients, searchTerm]);

  const selectedClient = details?.client || clients.find((client) => client.id === activeClientId) || null;
  const projects = useMemo(() => {
    const rows = Array.isArray(details?.projects) ? details.projects : [];
    if (isShimentoXClient(selectedClient)) return rows;
    return rows.filter((project) => !isShimentoXInternalProject(project));
  }, [details, selectedClient]);
  const clientTotals = useMemo(() => projects.reduce((totals, project) => {
    const requiredRoles = Array.isArray(project.required_role_cards) ? project.required_role_cards.length : 0;
    return {
      requiredJobs: totals.requiredJobs + Number(project.active_jobs || 0),
      requiredRoles: totals.requiredRoles + requiredRoles,
      benchCandidates: totals.benchCandidates + Number(project.current_candidates || 0),
      totalCandidates: totals.totalCandidates + Number(project.total_candidates || 0),
    };
  }, { requiredJobs: 0, requiredRoles: 0, benchCandidates: 0, totalCandidates: 0 }), [projects]);
  const updateForm = (key, value) => setForm(prev => ({ ...prev, [key]: value }));

  const openAddClient = () => {
    setForm(EMPTY_CLIENT_FORM);
    setAddOpen(true);
  };

  const closeAddClient = () => {
    if (!saving) setAddOpen(false);
  };

  const handleCreateClient = async (event) => {
    event.preventDefault();
    if (!form.name.trim()) {
      toast({ type: 'error', message: 'Client name is required.' });
      return;
    }

    setSaving(true);
    try {
      const { ok, data } = await apiPost('/api/clients', {
        ...form,
        name: form.name.trim(),
        client_account_id: form.client_account_id.trim(),
        status: 'Active',
      });
      if (!ok || !data.success) {
        toast({ type: 'error', message: data.error || 'Could not add client.' });
        return;
      }

      const refreshed = await apiGet('/api/clients');
      const rows = Array.isArray(refreshed.clients) ? refreshed.clients : [];
      setClients(rows);
      setActiveClientId(data.client?.id || rows[0]?.id || null);
      setForm(EMPTY_CLIENT_FORM);
      setAddOpen(false);
      toast({ type: 'success', message: 'Client added.' });
    } catch {
      toast({ type: 'error', message: 'Could not add client.' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Layout>
      <div className="clients-page">
        <div className="clients-header">
          <div>
            <h1><i className="fas fa-building"></i> Clients</h1>
            <p>Client accounts connected to jobs, candidates, and interview activity.</p>
          </div>
          <button type="button" className="btn btn-primary" onClick={openAddClient}>
            <i className="fas fa-plus"></i> Add Client
          </button>
        </div>

        {loading ? (
          <div className="clients-empty">Loading client accounts...</div>
        ) : error ? (
          <div className="clients-empty">{error}</div>
        ) : (
          <div className="clients-layout">
            <aside className="clients-sidebar">
              <input
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Search clients..."
                aria-label="Search clients"
              />
              <div className="clients-list">
                {filteredClients.map((client) => (
                  <button
                    key={client.id}
                    type="button"
                    className={`client-list-item${client.id === activeClientId ? ' active' : ''}`}
                    onClick={() => setActiveClientId(client.id)}
                  >
                    <strong>{client.name}</strong>
                    <span>{client.client_account_id}</span>
                    <small>{client.active_jobs || 0} required jobs - {client.total_candidates || 0} bench candidates</small>
                  </button>
                ))}
                {filteredClients.length === 0 && <div className="client-list-empty">No matching clients</div>}
              </div>
            </aside>

            <main className="client-detail">
              {selectedClient ? (
                <>
                  <section className="client-overview-card">
                    <div>
                      <span className="client-account-id">{selectedClient.client_account_id}</span>
                      <h2>{selectedClient.name}</h2>
                      <p>{selectedClient.notes || 'Default client account for existing recruitment data.'}</p>
                      <div className="client-overview-stats">
                        {[
                          ['Total Projects', projects.length],
                          ['Total Bench', clientTotals.benchCandidates],
                          ['Total Required', clientTotals.requiredJobs],
                        ].map(([label, value]) => (
                          <div key={label}>
                            <span>{label}</span>
                            <strong>{value}</strong>
                          </div>
                        ))}
                      </div>
                    </div>
                    <span className={`client-status status-${String(selectedClient.status || 'active').toLowerCase()}`}>
                      {selectedClient.status || 'Active'}
                    </span>
                  </section>

                  <section className="client-metrics client-overview-metrics">
                    {[
                      ['Required Jobs', clientTotals.requiredJobs, 'fas fa-briefcase'],
                      ['Required Roles', clientTotals.requiredRoles, 'fas fa-clipboard-list'],
                      ['Bench Candidates', clientTotals.benchCandidates, 'fas fa-user-check'],
                      ['Total Candidates', clientTotals.totalCandidates, 'fas fa-users'],
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
                      <h2><i className="fas fa-folder-tree"></i> Projects</h2>
                      <span>{projects.length} project{projects.length === 1 ? '' : 's'}</span>
                    </div>
                    <div className="client-project-grid">
                      {projects.map((project) => (
                        <button
                          key={project.id}
                          type="button"
                          className="client-project-card"
                          onClick={() => navigate(`/clients/${selectedClient.id}/projects/${project.id}`)}
                        >
                          <strong>{project.name}</strong>
                          <span>{project.project_type || 'Client'} - {project.status || 'Active'}</span>
                          <small>{project.active_jobs || 0} required jobs - {project.current_candidates || 0} bench candidates</small>
                          <em>Open project</em>
                        </button>
                      ))}
                      {projects.length === 0 && <div className="clients-empty compact">No projects available.</div>}
                    </div>
                  </section>
                </>
              ) : (
                <div className="clients-empty">No client selected.</div>
              )}
            </main>
          </div>
        )}

        {addOpen && (
          <div className="client-modal-backdrop" role="presentation" onMouseDown={closeAddClient}>
            <form className="client-modal" onSubmit={handleCreateClient} onMouseDown={(event) => event.stopPropagation()}>
              <div className="client-modal-head">
                <div>
                  <h2>Add Client</h2>
                  <p>Create a client account for job intake.</p>
                </div>
                <button type="button" className="client-modal-close" onClick={closeAddClient} aria-label="Close add client">
                  <i className="fas fa-times"></i>
                </button>
              </div>

              <div className="client-form-grid">
                <label>
                  <span>Client Name</span>
                  <input value={form.name} onChange={(event) => updateForm('name', event.target.value)} required />
                </label>
                <label>
                  <span>Client Account ID</span>
                  <input value={form.client_account_id} onChange={(event) => updateForm('client_account_id', event.target.value)} placeholder="Auto-created if blank" />
                </label>
                <label>
                  <span>Industry</span>
                  <input value={form.industry} onChange={(event) => updateForm('industry', event.target.value)} />
                </label>
                <label>
                  <span>Location</span>
                  <input value={form.location} onChange={(event) => updateForm('location', event.target.value)} />
                </label>
                <label>
                  <span>Contact</span>
                  <input value={form.contact_person} onChange={(event) => updateForm('contact_person', event.target.value)} />
                </label>
                <label>
                  <span>Email</span>
                  <input type="email" value={form.contact_email} onChange={(event) => updateForm('contact_email', event.target.value)} />
                </label>
                <label>
                  <span>Phone</span>
                  <input value={form.contact_phone} onChange={(event) => updateForm('contact_phone', event.target.value)} />
                </label>
                <label>
                  <span>Account Owner</span>
                  <input value={form.account_owner} onChange={(event) => updateForm('account_owner', event.target.value)} />
                </label>
                <label className="client-form-wide">
                  <span>Notes</span>
                  <textarea value={form.notes} onChange={(event) => updateForm('notes', event.target.value)} />
                </label>
              </div>

              <div className="client-modal-actions">
                <button type="button" className="btn btn-secondary" onClick={closeAddClient} disabled={saving}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? <><i className="fas fa-spinner fa-spin"></i> Saving...</> : <><i className="fas fa-plus"></i> Add Client</>}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </Layout>
  );
}

export default Clients;
