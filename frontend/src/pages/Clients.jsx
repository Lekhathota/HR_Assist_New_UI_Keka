import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { toast } from '../components/EnterpriseFeedback.jsx';
import { apiGet, apiPost } from '../api.js';
import '../styles/clients.css';
import '../styles/jd_create.css';

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
  hiring_stages: ['Sourced', 'Screening', 'Interview', 'Offer', 'Hired'],
};

function isShimentoXClient(client) {
  return String(client?.client_account_id || '').trim().toUpperCase() === 'SHIMENTOX';
}

function isShimentoXInternalProject(project) {
  return String(project?.name || '').trim().toLowerCase() === 'shimentox internal';
}

function Clients({ createPage = false }) {
  const navigate = useNavigate();
  // ?client=<id> (e.g. from global search) opens that client directly.
  const [searchParams] = useSearchParams();
  const requestedClientId = Number(searchParams.get('client')) || null;
  const [clients, setClients] = useState([]);
  const [activeClientId, setActiveClientId] = useState(requestedClientId);
  const [details, setDetails] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
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
    if (requestedClientId) setActiveClientId(requestedClientId);
  }, [requestedClientId]);

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
        toast({ type: 'error', message: 'Could not load client details. Please try again.' });
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
  const addStage = () => setForm(prev => ({
    ...prev,
    hiring_stages: [...prev.hiring_stages, ''],
  }));
  const removeStage = (index) => setForm(prev => (
    prev.hiring_stages.length > 1
      ? { ...prev, hiring_stages: prev.hiring_stages.filter((_, stageIndex) => stageIndex !== index) }
      : prev
  ));
  const updateStage = (index, value) => setForm(prev => ({
    ...prev,
    hiring_stages: prev.hiring_stages.map((stage, stageIndex) => (
      stageIndex === index ? value : stage
    )),
  }));

  const openAddClient = () => {
    setForm(EMPTY_CLIENT_FORM);
    navigate('/clients/create');
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
      toast({ type: 'success', message: 'Client added.' });
      navigate('/clients');
    } catch {
      toast({ type: 'error', message: 'Could not add client.' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Layout>
      <div className={`clients-page${createPage ? ' client-create-page' : ''}`}>
        {createPage ? (
          <div className="jd-create-container client-create-container">
            <div className="jd-create-header">
              <h1><span className="client-create-icon"><i className="fas fa-building"></i></span> Add Client</h1>
              <p>Create a client account for job intake.</p>
            </div>

            <div className="form-container">
              <form onSubmit={handleCreateClient}>
                <section className="client-create-section">
                  <div className="client-create-section-heading">
                    <span>Client details</span>
                    <span className="client-create-section-rule"></span>
                  </div>
                  <div className="client-form-grid">
                    <label className="jd-create-label-color">
                      <span><i className="fas fa-building"></i> Client Name <span className="client-required-mark">*</span></span>
                      <input value={form.name} onChange={(event) => updateForm('name', event.target.value)} required />
                    </label>
                    <label className="jd-create-label-color">
                      <span><i className="fas fa-id-card"></i> Client Account ID</span>
                      <input value={form.client_account_id} onChange={(event) => updateForm('client_account_id', event.target.value)} placeholder="Auto-created if blank" />
                    </label>
                    <label className="jd-create-label-color">
                      <span><i className="fas fa-industry"></i> Industry</span>
                      <input value={form.industry} onChange={(event) => updateForm('industry', event.target.value)} />
                    </label>
                    <label className="jd-create-label-color">
                      <span><i className="fas fa-location-dot"></i> Location</span>
                      <input value={form.location} onChange={(event) => updateForm('location', event.target.value)} />
                    </label>
                  </div>
                </section>

                <section className="client-create-section">
                  <div className="client-create-section-heading">
                    <span>Contact</span>
                    <span className="client-create-section-rule"></span>
                  </div>
                  <div className="client-form-grid">
                    <label className="jd-create-label-color">
                      <span><i className="fas fa-user"></i> Contact</span>
                      <input value={form.contact_person} onChange={(event) => updateForm('contact_person', event.target.value)} />
                    </label>
                    <label className="jd-create-label-color">
                      <span><i className="fas fa-envelope"></i> Email</span>
                      <input type="email" value={form.contact_email} onChange={(event) => updateForm('contact_email', event.target.value)} placeholder="name@company.com" />
                    </label>
                    <label className="jd-create-label-color">
                      <span><i className="fas fa-phone"></i> Phone</span>
                      <input value={form.contact_phone} onChange={(event) => updateForm('contact_phone', event.target.value)} />
                    </label>
                    <label className="jd-create-label-color">
                      <span><i className="fas fa-user-tie"></i> Account Owner</span>
                      <input value={form.account_owner} onChange={(event) => updateForm('account_owner', event.target.value)} />
                    </label>
                    <label className="client-form-wide jd-create-label-color">
                      <span><i className="fas fa-note-sticky"></i> Notes</span>
                      <textarea value={form.notes} onChange={(event) => updateForm('notes', event.target.value)} />
                    </label>
                  </div>
                </section>

                <section className="client-hiring-stages">
                  <div className="client-create-section-heading">
                    <span>Hiring stages</span>
                    <span className="client-create-stage-count">{form.hiring_stages.length} {form.hiring_stages.length === 1 ? 'stage' : 'stages'}</span>
                    <span className="client-create-section-rule"></span>
                  </div>
                  <p className="client-create-stage-help">Jobs under this client will default to these stages, in this order.</p>
                  <div className="client-hiring-stage-list">
                    {form.hiring_stages.map((stage, index) => (
                      <div className="client-hiring-stage-row" key={index}>
                        <span className="client-hiring-stage-number">{index + 1}</span>
                        <input
                          value={stage}
                          onChange={(event) => updateStage(index, event.target.value)}
                          aria-label={`Hiring stage ${index + 1}`}
                        />
                        <button
                          type="button"
                          className="client-hiring-stage-remove"
                          onClick={() => removeStage(index)}
                          aria-label={`Remove hiring stage ${index + 1}`}
                        >
                          <i className="fas fa-times"></i>
                        </button>
                      </div>
                    ))}
                    <button type="button" className="client-hiring-stage-add" onClick={addStage}>
                      <i className="fas fa-plus"></i> Add stage
                    </button>
                  </div>
                </section>

                <div className="client-create-footer">
                  <Link to="/clients" className="back-link"><i className="fas fa-arrow-left"></i> Back to Clients</Link>
                  <button type="submit" className="btn btn-primary client-create-submit" disabled={saving}>
                    {saving ? <><i className="fas fa-spinner fa-spin"></i> Saving...</> : <><i className="fas fa-plus"></i> Add Client</>}
                  </button>
                </div>
              </form>
            </div>
          </div>
        ) : (
          <>
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

          </>
        )}
      </div>
    </Layout>
  );
}

export default Clients;
