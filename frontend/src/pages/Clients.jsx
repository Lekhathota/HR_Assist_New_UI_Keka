import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { toast } from '../components/EnterpriseFeedback.jsx';
import PipelineEditor from '../components/PipelineEditor.jsx';
import RoleEditor from '../components/RoleEditor.jsx';
import { apiGet, apiPost, apiPut } from '../api.js';
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

function requestFailureMessage(error, status) {
  if (error?.data?.error) return error.data.error;
  if (status != null) return `Request failed (status ${status})`;
  const message = String(error?.message || '');
  const statusMatch = message.match(/failed:\s*(\d+)/i);
  if (statusMatch) return `Request failed (status ${statusMatch[1]})`;
  return message || 'Request failed';
}

function Clients({ createPage = false }) {
  const navigate = useNavigate();
  // ?client=<id> (e.g. from global search) opens that client directly.
  const [searchParams] = useSearchParams();
  const requestedClientId = Number(searchParams.get('client')) || null;
  const [clients, setClients] = useState([]);
  const [activeClientId, setActiveClientId] = useState(requestedClientId);
  const [details, setDetails] = useState(null);
  const [detailsError, setDetailsError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(EMPTY_CLIENT_FORM);
  const [pipelineEditor, setPipelineEditor] = useState(null);
  const [roleEditor, setRoleEditor] = useState(null);
  const [archivingPipelineId, setArchivingPipelineId] = useState('');
  const [moveRolesToPipelineId, setMoveRolesToPipelineId] = useState('');

  const loadClients = () => {
    setLoading(true);
    setError('');
    apiGet('/api/clients')
      .then((data) => {
        const rows = Array.isArray(data?.clients) ? data.clients.filter(Boolean) : [];
        setClients(rows);
        setActiveClientId((current) => current || rows[0]?.id || null);
      })
      .catch((err) => setError(requestFailureMessage(err)))
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
      setDetailsError('');
      return;
    }
    setPipelineEditor(null);
    setRoleEditor(null);
    setArchivingPipelineId('');
    setMoveRolesToPipelineId('');
    let ignore = false;
    setDetails(null);
    setDetailsError('');
    apiGet(`/api/clients/${activeClientId}`)
      .then((data) => {
        if (ignore) return;
        if (String(data?.client?.id) === String(activeClientId)) {
          setDetails(data);
        } else {
          setDetailsError('Request returned details for a different client.');
        }
      })
      .catch((err) => {
        if (ignore) return;
        setDetails(null);
        const message = requestFailureMessage(err);
        setDetailsError(message);
        toast({ type: 'error', message });
      });
    return () => {
      ignore = true;
    };
  }, [activeClientId]);

  const filteredClients = useMemo(() => {
    const needle = searchTerm.trim().toLowerCase();
    if (!needle) return clients;
    return clients.filter((client) => client && (
      `${client.name || ''} ${client.client_account_id || ''} ${client.industry || ''} ${client.contact_person || ''}`
        .toLowerCase()
        .includes(needle)
    ));
  }, [clients, searchTerm]);

  const hasMatchingDetails = details?.client?.id != null
    && String(details.client.id) === String(activeClientId);
  const selectedClient = hasMatchingDetails
    ? details.client
    : clients.find((client) => String(client?.id) === String(activeClientId)) || null;
  const projects = useMemo(() => {
    const rows = hasMatchingDetails && Array.isArray(details?.projects) ? details.projects.filter(Boolean) : [];
    if (isShimentoXClient(selectedClient)) return rows;
    return rows.filter((project) => !isShimentoXInternalProject(project));
  }, [details, hasMatchingDetails, selectedClient]);
  const detailClient = hasMatchingDetails ? details?.client : null;
  const hiringPipelines = useMemo(
    () => (Array.isArray(detailClient?.hiring_pipelines) ? detailClient.hiring_pipelines.filter(Boolean) : []),
    [detailClient]
  );
  const activePipelines = useMemo(
    () => hiringPipelines.filter((pipeline) => !pipeline?.is_archived),
    [hiringPipelines]
  );
  const roles = useMemo(
    () => (Array.isArray(detailClient?.roles) ? detailClient.roles.filter(Boolean) : []),
    [detailClient]
  );
  const getPipelineName = (pipelineId) => (
    hiringPipelines.find((pipeline) => String(pipeline?.id) === String(pipelineId))?.name || 'Pipeline unavailable'
  );
  const clientTotals = useMemo(() => projects.reduce((totals, project) => {
    const requiredRoles = Array.isArray(project?.required_role_cards) ? project.required_role_cards.length : 0;
    return {
      requiredJobs: totals.requiredJobs + Number(project?.active_jobs || 0),
      requiredRoles: totals.requiredRoles + requiredRoles,
      benchCandidates: totals.benchCandidates + Number(project?.current_candidates || 0),
      totalCandidates: totals.totalCandidates + Number(project?.total_candidates || 0),
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
      const { ok, status, data } = await apiPost('/api/clients', {
        ...form,
        name: form.name.trim(),
        client_account_id: form.client_account_id.trim(),
        status: 'Active',
      });
      if (!ok) {
        toast({ type: 'error', message: requestFailureMessage(data, status) });
        return;
      }
      if (!data?.success) {
        toast({ type: 'error', message: data?.error || 'Could not add client.' });
        return;
      }

      const refreshed = await apiGet('/api/clients');
      const rows = Array.isArray(refreshed?.clients) ? refreshed.clients.filter(Boolean) : [];
      setClients(rows);
      setActiveClientId(data?.client?.id || rows[0]?.id || null);
      setForm(EMPTY_CLIENT_FORM);
      toast({ type: 'success', message: 'Client added.' });
      navigate('/clients');
    } catch (err) {
      toast({ type: 'error', message: requestFailureMessage(err) });
    } finally {
      setSaving(false);
    }
  };

  const reloadClient = async (clientId) => {
    const refreshed = await apiGet(`/api/clients/${clientId}`);
    if (String(refreshed?.client?.id) !== String(clientId)) {
      throw new Error('Request returned details for a different client.');
    }
    setDetails(refreshed);
  };

  const saveClientConfig = async (request, successMessage, onSuccess) => {
    setSaving(true);
    try {
      const result = await request();
      if (!result?.ok) {
        toast({
          type: 'error',
          message: requestFailureMessage(result?.data, result?.status),
        });
        return false;
      }
      await reloadClient(activeClientId);
      onSuccess?.();
      toast({ type: 'success', message: successMessage });
      return true;
    } catch (err) {
      toast({ type: 'error', message: requestFailureMessage(err) });
      return false;
    } finally {
      setSaving(false);
    }
  };

  const savePipeline = (pipeline, payload) => {
    const path = pipeline
      ? `/api/clients/${activeClientId}/pipelines/${pipeline.id}`
      : `/api/clients/${activeClientId}/pipelines`;
    return saveClientConfig(
      () => (pipeline ? apiPut(path, payload) : apiPost(path, payload)),
      pipeline ? 'Hiring pipeline updated.' : 'Hiring pipeline added.',
      () => setPipelineEditor(null)
    );
  };

  const setDefaultPipeline = (pipeline) => saveClientConfig(
    () => apiPut(`/api/clients/${activeClientId}/pipelines/${pipeline.id}`, { is_default: true }),
    'Default hiring pipeline updated.'
  );

  const saveRole = (role, payload) => {
    const path = role
      ? `/api/clients/${activeClientId}/roles/${role.id}`
      : `/api/clients/${activeClientId}/roles`;
    return saveClientConfig(
      () => (role ? apiPut(path, payload) : apiPost(path, payload)),
      role ? 'Role updated.' : 'Role added.',
      () => setRoleEditor(null)
    );
  };

  const archiveRole = (role) => saveClientConfig(
    () => apiPut(`/api/clients/${activeClientId}/roles/${role.id}`, { is_archived: true }),
    'Role archived.'
  );

  const archivePipeline = (pipeline) => {
    const activeRoleCount = roles.filter(
      (role) => role?.pipeline_id === pipeline.id && !role?.is_archived
    ).length;
    if (activeRoleCount > 0) {
      setArchivingPipelineId(pipeline.id);
      setMoveRolesToPipelineId('');
      return;
    }
    saveClientConfig(
      () => apiPut(`/api/clients/${activeClientId}/pipelines/${pipeline.id}`, { is_archived: true }),
      'Hiring pipeline archived.'
    );
  };

  const confirmArchivePipeline = (pipeline) => {
    if (!moveRolesToPipelineId) return;
    saveClientConfig(
      () => apiPut(`/api/clients/${activeClientId}/pipelines/${pipeline.id}`, {
        is_archived: true,
        move_roles_to_pipeline_id: moveRolesToPipelineId,
      }),
      'Hiring pipeline archived.',
      () => {
        setArchivingPipelineId('');
        setMoveRolesToPipelineId('');
      }
    );
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
                    key={client?.id}
                    type="button"
                    className={`client-list-item${String(client?.id) === String(activeClientId) ? ' active' : ''}`}
                    onClick={() => setActiveClientId(client?.id)}
                  >
                    <strong>{client?.name}</strong>
                    <span>{client?.client_account_id}</span>
                    <small>{client?.active_jobs || 0} required jobs - {client?.total_candidates || 0} bench candidates</small>
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
                      <span className="client-account-id">{selectedClient?.client_account_id}</span>
                      <h2>{selectedClient?.name}</h2>
                      <p>{selectedClient?.notes || 'Default client account for existing recruitment data.'}</p>
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
                    <span className={`client-status status-${String(selectedClient?.status || 'active').toLowerCase()}`}>
                      {selectedClient?.status || 'Active'}
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
                      <h2><i className="fas fa-diagram-project"></i> Hiring pipelines</h2>
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => setPipelineEditor({ pipeline: null })}
                        disabled={!hasMatchingDetails || saving}
                      >
                        <i className="fas fa-plus"></i> Add pipeline
                      </button>
                    </div>
                    <div className="client-project-grid">
                      {activePipelines.map((pipeline) => {
                        const stageList = Array.isArray(pipeline?.stages) ? pipeline.stages.filter(Boolean) : [];
                        const activeRoleCount = roles.filter(
                          (role) => role?.pipeline_id === pipeline?.id && !role?.is_archived
                        ).length;
                        const editing = pipelineEditor?.pipeline?.id === pipeline?.id;
                        const archiveInProgress = archivingPipelineId === pipeline?.id;
                        return (
                          <article key={pipeline?.id} className="client-project-card client-config-card client-pipeline-card">
                            <div className="client-config-card-heading">
                              <div className="client-pipeline-heading">
                                <strong>{pipeline?.name || 'Unnamed pipeline'}</strong>
                                {pipeline?.is_default && <span className="client-default-badge">Default</span>}
                              </div>
                              <span className="client-pipeline-stage-count">
                                {stageList.length} stages
                              </span>
                            </div>
                            <ol
                              className={`client-pipeline-stepper${stageList.length > 6 ? ' is-scrollable' : ''}`}
                              aria-label={`${pipeline?.name || 'Hiring pipeline'} stages`}
                            >
                              {stageList.map((stage, index) => (
                                <li key={stage?.id || `${stage?.name || 'stage'}-${index}`}>
                                  <span className="client-pipeline-stage-number">{index + 1}</span>
                                  <span className="client-pipeline-stage-name">{stage?.name || 'Unnamed stage'}</span>
                                </li>
                              ))}
                            </ol>
                            <div className="client-config-actions client-pipeline-actions">
                              <button
                                type="button"
                                className="btn btn-secondary"
                                onClick={() => {
                                  setArchivingPipelineId('');
                                  setPipelineEditor({ pipeline });
                                }}
                              >
                                Edit
                              </button>
                              {!pipeline?.is_default && (
                                <>
                                  <button
                                    type="button"
                                    className="btn btn-secondary"
                                    onClick={() => setDefaultPipeline(pipeline)}
                                    disabled={saving}
                                  >
                                    Set as default
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-secondary"
                                    onClick={() => archivePipeline(pipeline)}
                                    disabled={saving}
                                  >
                                    Archive
                                  </button>
                                </>
                              )}
                            </div>
                            {archiveInProgress && (
                              <div className="client-archive-role-move">
                                <label className="jd-create-label-color">
                                  <span>Move {activeRoleCount} active role{activeRoleCount === 1 ? '' : 's'} to</span>
                                  <select
                                    value={moveRolesToPipelineId}
                                    onChange={(event) => setMoveRolesToPipelineId(event.target.value)}
                                  >
                                    <option value="">Select a pipeline</option>
                                    {activePipelines
                                      .filter((option) => option?.id !== pipeline?.id)
                                      .map((option) => (
                                        <option key={option.id} value={option.id}>{option.name}</option>
                                      ))}
                                  </select>
                                </label>
                                <div className="client-config-actions">
                                  <button
                                    type="button"
                                    className="btn btn-secondary"
                                    onClick={() => {
                                      setArchivingPipelineId('');
                                      setMoveRolesToPipelineId('');
                                    }}
                                  >
                                    Cancel
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-primary"
                                    onClick={() => confirmArchivePipeline(pipeline)}
                                    disabled={!moveRolesToPipelineId || saving}
                                  >
                                    Confirm archive
                                  </button>
                                </div>
                              </div>
                            )}
                            {editing && (
                              <PipelineEditor
                                key={pipeline?.id}
                                pipeline={pipeline}
                                saving={saving}
                                onSave={(payload) => savePipeline(pipeline, payload)}
                                onCancel={() => setPipelineEditor(null)}
                              />
                            )}
                          </article>
                        );
                      })}
                      {activePipelines.length === 0 && (
                        <div className="clients-empty compact">
                          {hasMatchingDetails ? 'No hiring pipelines configured.' : detailsError || 'Loading client details...'}
                        </div>
                      )}
                      {hasMatchingDetails && pipelineEditor && !pipelineEditor.pipeline && (
                        <div className="client-role-card client-editor-card">
                          <PipelineEditor
                            saving={saving}
                            onSave={(payload) => savePipeline(null, payload)}
                            onCancel={() => setPipelineEditor(null)}
                          />
                        </div>
                      )}
                    </div>
                  </section>

                  <section className="client-projects">
                    <div className="client-section-title">
                      <h2><i className="fas fa-briefcase"></i> Roles</h2>
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => setRoleEditor({ role: null })}
                        disabled={!hasMatchingDetails || activePipelines.length === 0 || saving}
                      >
                        <i className="fas fa-plus"></i> Add role
                      </button>
                    </div>
                    <div className="client-role-grid">
                      {roles.map((role) => {
                        const editing = roleEditor?.role?.id === role?.id;
                        return (
                          <article key={role?.id} className="client-role-card client-config-card">
                            <div className="client-role-row">
                              <div className="client-role-title">
                                <strong>{role?.title || 'Untitled role'}</strong>
                                <span className="client-role-level">{role?.level || 'Level not set'}</span>
                              </div>
                              <div className="client-role-pipeline">
                                <span>Pipeline:</span>
                                <strong>{getPipelineName(role?.pipeline_id)}</strong>
                              </div>
                              {role?.is_archived && (
                                <span className="client-role-archived">Archived</span>
                              )}
                              <div className="client-role-actions">
                                {!role?.is_archived && (
                                  <button
                                    type="button"
                                    className="btn btn-secondary"
                                    onClick={() => archiveRole(role)}
                                    disabled={saving}
                                  >
                                    Archive
                                  </button>
                                )}
                                <button
                                  type="button"
                                  className="btn btn-secondary"
                                  onClick={() => setRoleEditor({ role })}
                                >
                                  Edit
                                </button>
                              </div>
                            </div>
                            {editing && (
                              <RoleEditor
                                key={role?.id}
                                role={role}
                                pipelines={activePipelines}
                                saving={saving}
                                onSave={(payload) => saveRole(role, payload)}
                                onCancel={() => setRoleEditor(null)}
                              />
                            )}
                          </article>
                        );
                      })}
                      {roles.length === 0 && (
                        <div className="clients-empty compact">
                          {hasMatchingDetails ? 'No roles configured for this client.' : detailsError || 'Loading client details...'}
                        </div>
                      )}
                      {hasMatchingDetails && roleEditor && !roleEditor.role && (
                        <div className="client-role-card client-editor-card">
                          <RoleEditor
                            pipelines={activePipelines}
                            saving={saving}
                            onSave={(payload) => saveRole(null, payload)}
                            onCancel={() => setRoleEditor(null)}
                          />
                        </div>
                      )}
                    </div>
                  </section>

                  <section className="client-projects">
                    <div className="client-section-title">
                      <h2><i className="fas fa-folder-tree"></i> Projects</h2>
                      <span>{projects.length} project{projects.length === 1 ? '' : 's'}</span>
                    </div>
                    <div className="client-project-grid">
                      {projects.map((project) => (
                        <button
                          key={project?.id}
                          type="button"
                          className="client-project-card"
                          onClick={() => navigate(`/clients/${selectedClient?.id}/projects/${project?.id}`)}
                        >
                          <strong>{project?.name}</strong>
                          <span>{project?.project_type || 'Client'} - {project?.status || 'Active'}</span>
                          <small>{project?.active_jobs || 0} required jobs - {project?.current_candidates || 0} bench candidates</small>
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
