import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Layout from '../components/Layout.jsx';
import { toast, useConfirm } from '../components/EnterpriseFeedback.jsx';
import { apiDelete, apiGet, apiPost, apiPostForm, apiPut, readSessionCache, VENDOR_CACHE_KEY, writeSessionCache } from '../api.js';
import '../styles/vendors.css';

const EMPTY_VENDOR_FORM = {
  vendor_name: '',
  company_name: '',
  contact_person: '',
  email: '',
  phone: '',
  status: 'Active',
  notes: '',
  supported_categories: '',
  supported_sub_tags: '',
};

function Vendors() {
  const confirm = useConfirm();
  const [vendors, setVendors] = useState(() => readSessionCache(VENDOR_CACHE_KEY) || []);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('Active');
  const [sortBy, setSortBy] = useState('company_name');
  const [loading, setLoading] = useState(!readSessionCache(VENDOR_CACHE_KEY));
  const [error, setError] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingVendor, setEditingVendor] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(EMPTY_VENDOR_FORM);
  const [assignModal, setAssignModal] = useState(null);
  const [assignJobs, setAssignJobs] = useState([]);
  const [assignedJobIds, setAssignedJobIds] = useState([]);
  const [originalAssignedJobIds, setOriginalAssignedJobIds] = useState([]);
  const [jobSearch, setJobSearch] = useState('');
  const [loadingAssignments, setLoadingAssignments] = useState(false);
  const [savingAssignments, setSavingAssignments] = useState(false);
  const [assignmentError, setAssignmentError] = useState('');
  const [emailModal, setEmailModal] = useState(null);
  const [emailBusy, setEmailBusy] = useState(false);
  const [manualAttachment, setManualAttachment] = useState(null);
  const [emailQueue, setEmailQueue] = useState([]);

  const loadVendors = useCallback(() => {
    setLoading(true);
    setError('');
    const params = new URLSearchParams({ status: statusFilter, sort: sortBy });
    if (searchTerm.trim()) params.set('search', searchTerm.trim());
    apiGet(`/api/vendors?${params.toString()}`)
      .then((data) => {
        const rows = Array.isArray(data.vendors) ? data.vendors : [];
        setVendors(rows);
        writeSessionCache(VENDOR_CACHE_KEY, rows);
      })
      .catch((err) => setError(err.message || 'Could not load vendors.'))
      .finally(() => setLoading(false));
  }, [searchTerm, statusFilter, sortBy]);

  useEffect(() => {
    const timer = window.setTimeout(loadVendors, 180);
    return () => window.clearTimeout(timer);
  }, [loadVendors]);

  const stats = useMemo(() => vendors.reduce((total, vendor) => ({
    active: total.active + (vendor.status === 'Active' ? 1 : 0),
    assigned: total.assigned + Number(vendor.assigned_jds_count || 0),
    candidates: total.candidates + Number(vendor.candidates_provided_count || 0),
  }), { active: 0, assigned: 0, candidates: 0 }), [vendors]);

  const updateForm = (key, value) => setForm(prev => ({ ...prev, [key]: value }));

  const openCreate = () => {
    setEditingVendor(null);
    setForm(EMPTY_VENDOR_FORM);
    setModalOpen(true);
  };

  const openEdit = (vendor) => {
    setEditingVendor(vendor);
    setForm({
      vendor_name: vendor.vendor_name || '',
      company_name: vendor.company_name || '',
      contact_person: vendor.contact_person || '',
      email: vendor.email || '',
      phone: vendor.phone || '',
      status: vendor.status || 'Active',
      notes: vendor.notes || '',
      supported_categories: (vendor.supported_categories || []).join(', '),
      supported_sub_tags: (vendor.supported_sub_tags || []).join(', '),
    });
    setModalOpen(true);
  };

  const closeModal = () => {
    if (!saving) setModalOpen(false);
  };

  const saveVendor = async (event) => {
    event.preventDefault();
    if (!form.email.trim()) {
      toast({ type: 'error', message: 'Vendor email is required.' });
      return;
    }
    if (!form.vendor_name.trim() && !form.company_name.trim()) {
      toast({ type: 'error', message: 'Vendor name or company name is required.' });
      return;
    }

    setSaving(true);
    try {
      const payload = {
        ...form,
        vendor_name: form.vendor_name.trim(),
        company_name: form.company_name.trim(),
        contact_person: form.contact_person.trim(),
        email: form.email.trim(),
        phone: form.phone.trim(),
        notes: form.notes.trim(),
        supported_categories: form.supported_categories.split(',').map(item => item.trim()).filter(Boolean),
        supported_sub_tags: form.supported_sub_tags.split(',').map(item => item.trim()).filter(Boolean),
      };
      const result = editingVendor
        ? await apiPut(`/api/vendors/${editingVendor.id}`, payload)
        : await apiPost('/api/vendors', payload);
      if (!result.ok || !result.data.success) {
        toast({ type: 'error', message: result.data.error || 'Could not save vendor.' });
        return;
      }
      setModalOpen(false);
      toast({ type: 'success', message: editingVendor ? 'Vendor updated.' : 'Vendor added.' });
      loadVendors();
    } catch {
      toast({ type: 'error', message: 'Could not save vendor.' });
    } finally {
      setSaving(false);
    }
  };

  const deleteVendor = async (vendor) => {
    const approved = await confirm({
      title: 'Delete vendor',
      message: `Delete "${vendor.vendor_name || vendor.company_name || vendor.email}"? Active JD assignments will be removed.`,
      confirmLabel: 'Delete Vendor',
      icon: 'fas fa-trash-alt',
      danger: true,
    });
    if (!approved) return;
    try {
      const { ok, data } = await apiDelete(`/api/vendors/${vendor.id}`);
      if (!ok || !data.success) throw new Error(data.error || 'Could not delete vendor.');
      toast({ type: 'success', message: 'Vendor deleted.' });
      loadVendors();
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not delete vendor.' });
    }
  };

  const openAssignJobs = async (vendor) => {
    setAssignModal(vendor);
    setAssignJobs([]);
    setAssignedJobIds([]);
    setOriginalAssignedJobIds([]);
    setJobSearch('');
    setAssignmentError('');
    setLoadingAssignments(true);
    try {
      try {
        const data = await apiGet(`/api/vendors/${vendor.id}/jds`);
        const ids = Array.isArray(data.assigned_jd_ids) ? data.assigned_jd_ids.map(Number) : [];
        setAssignJobs(Array.isArray(data.jobs) ? data.jobs : []);
        setAssignedJobIds(ids);
        setOriginalAssignedJobIds(ids);
      } catch {
        const jobs = await apiGet('/api/jds');
        const rows = Array.isArray(jobs) ? jobs : [];
        const activeJobs = rows.filter(job => (job.status || 'Active') === 'Active');
        const assignedPairs = await Promise.all(
          activeJobs.map(job =>
            apiGet(`/api/jds/${job.id}/vendors`)
              .then(data => [Number(job.id), (data.vendors || []).some(item => Number(item.id) === Number(vendor.id))])
              .catch(() => [Number(job.id), false]),
          ),
        );
        const assignedIds = assignedPairs.filter(([, assigned]) => assigned).map(([id]) => id);
        setAssignJobs(activeJobs.map(job => ({ ...job, assigned: assignedIds.includes(Number(job.id)) })));
        setAssignedJobIds(assignedIds);
        setOriginalAssignedJobIds(assignedIds);
      }
    } catch (err) {
      setAssignmentError(err.message || 'Could not load JD assignments.');
    } finally {
      setLoadingAssignments(false);
    }
  };

  const toggleJobSelection = (jdId) => {
    const id = Number(jdId);
    setAssignedJobIds(prev => (
      prev.includes(id) ? prev.filter(item => item !== id) : [...prev, id]
    ));
  };

  const saveJobAssignments = async () => {
    if (!assignModal) return;
    const vendor = assignModal;
    const selectedBeforeSave = assignedJobIds.map(Number);
    const originalBeforeSave = originalAssignedJobIds.map(Number);
    setSavingAssignments(true);
    setAssignmentError('');
    try {
      const selected = new Set(selectedBeforeSave);
      const original = new Set(originalBeforeSave);
      const keptExistingIds = originalBeforeSave.filter(id => selected.has(id));
      const newJobIds = selectedBeforeSave.filter(id => !original.has(id));
      const removedJobIds = originalBeforeSave.filter(id => !selected.has(id));

      if (removedJobIds.length) {
        try {
          const { ok, data } = await apiPost(`/api/vendors/${vendor.id}/jds`, { jd_ids: keptExistingIds });
          if (!ok || !data.success) throw new Error(data.error || 'Could not update existing JD assignments.');
          setAssignJobs(Array.isArray(data.jobs) ? data.jobs : []);
          const ids = Array.isArray(data.assigned_jd_ids) ? data.assigned_jd_ids.map(Number) : keptExistingIds;
          setAssignedJobIds(ids);
          setOriginalAssignedJobIds(ids);
        } catch {
          await Promise.all(removedJobIds.map(async (jdId) => {
            const data = await apiGet(`/api/jds/${jdId}/vendors`);
            const currentIds = (data.vendors || []).map(item => Number(item.id));
            const nextIds = currentIds.filter(id => id !== Number(vendor.id));
            const result = await apiPost(`/api/jds/${jdId}/vendors`, { vendor_ids: nextIds });
            if (!result.ok || !result.data.success) throw new Error(result.data.error || `Could not update JD ${jdId}.`);
          }));
          setOriginalAssignedJobIds(keptExistingIds);
        }
      } else {
        setOriginalAssignedJobIds(originalBeforeSave);
      }

      setAssignModal(null);
      toast({ type: 'success', message: newJobIds.length ? 'Send email to complete new JD assignment.' : 'JD assignments updated.' });
      loadVendors();

      const newJobs = newJobIds
        .map(id => assignJobs.find(item => Number(item.id) === Number(id)) || { id, title: 'Selected JD' });
      if (newJobs.length) {
        setEmailQueue(newJobs.slice(1));
        openVendorEmail(vendor, newJobs[0]);
      }
    } catch (err) {
      setAssignmentError(err.message || 'Could not assign JDs.');
      toast({ type: 'error', message: err.message || 'Could not assign JDs.' });
    } finally {
      setSavingAssignments(false);
    }
  };

  const openVendorEmail = async (vendor, job) => {
    setManualAttachment(null);
    setEmailModal({
      vendor,
      job,
      from_email: '',
      to_email: vendor.email || '',
      subject: '',
      body: '',
      attachments: [],
      error: '',
    });
    setEmailBusy(true);
    try {
      const { ok, data } = await apiPost(`/api/jds/${job.id}/vendors/${vendor.id}/generate-email`, {});
      if (!ok) throw new Error(data.error || 'Could not generate vendor email.');
      setEmailModal({ vendor, job, ...data, error: '' });
    } catch (err) {
      setEmailModal(prev => ({ ...prev, error: err.message || 'Could not generate vendor email.' }));
    } finally {
      setEmailBusy(false);
    }
  };

  const updateEmail = (key, value) => {
    setEmailModal(prev => ({ ...prev, [key]: value }));
  };

  const closeEmailModal = () => {
    if (emailBusy) return;
    setEmailModal(null);
    setManualAttachment(null);
    setEmailQueue([]);
  };

  const sendVendorEmail = async () => {
    if (!emailModal?.vendor || !emailModal?.job || !emailModal.subject || !emailModal.body) {
      updateEmail('error', 'Email subject and body are required.');
      return;
    }
    setEmailBusy(true);
    try {
      const formData = new FormData();
      formData.append('to_email', emailModal.to_email || '');
      formData.append('subject', emailModal.subject || '');
      formData.append('body', emailModal.body || '');
      if (manualAttachment) formData.append('attachment', manualAttachment);
      const { ok, data } = await apiPostForm(`/api/jds/${emailModal.job.id}/vendors/${emailModal.vendor.id}/assign-send-email`, formData);
      if (!ok || !data.success) throw new Error(data.error || 'Could not send vendor email.');
      toast({ type: 'success', message: 'JD email sent and vendor assigned.' });
      setManualAttachment(null);
      loadVendors();
      const [nextJob, ...rest] = emailQueue;
      if (nextJob) {
        setEmailQueue(rest);
        await openVendorEmail(emailModal.vendor, nextJob);
      } else {
        setEmailModal(null);
        setEmailQueue([]);
      }
    } catch (err) {
      const message = err.message || 'Email was not sent, so the vendor was not assigned.';
      updateEmail('error', message);
      toast({ type: 'error', message });
    } finally {
      setEmailBusy(false);
    }
  };

  const filteredAssignJobs = useMemo(() => {
    const needle = jobSearch.trim().toLowerCase();
    if (!needle) return assignJobs;
    return assignJobs.filter(job => `${job.title || ''} ${job.client_name || ''} ${job.location || ''}`.toLowerCase().includes(needle));
  }, [assignJobs, jobSearch]);

  return (
    <Layout>
      <div className="vendors-page">
        <div className="vendors-header">
          <div>
            <h1><i className="fas fa-handshake"></i> Vendors</h1>
            <p>Recruitment partners available for selective JD sharing.</p>
          </div>
          <button type="button" className="btn btn-primary" onClick={openCreate}>
            <i className="fas fa-plus"></i> Add Vendor
          </button>
        </div>

        <section className="vendor-metrics">
          <div><span>Total Vendors</span><strong>{vendors.length}</strong></div>
          <div><span>Active Vendors</span><strong>{stats.active}</strong></div>
          <div><span>Assigned JDs</span><strong>{stats.assigned}</strong></div>
          <div><span>Candidates Provided</span><strong>{stats.candidates}</strong></div>
        </section>

        <section className="vendor-toolbar">
          <input value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)} placeholder="Search vendors..." />
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="Active">Active</option>
            <option value="Inactive">Inactive</option>
            <option value="All">All</option>
          </select>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
            <option value="company_name">Company</option>
            <option value="vendor_name">Vendor</option>
            <option value="updated_at">Last Updated</option>
            <option value="created_at">Created Date</option>
          </select>
        </section>

        {loading ? (
          <div className="vendors-empty">Loading vendors...</div>
        ) : error ? (
          <div className="vendors-empty">{error}</div>
        ) : vendors.length === 0 ? (
          <div className="vendors-empty">No vendors found.</div>
        ) : (
          <div className="vendor-table-wrap">
            <table className="vendor-table">
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>Contact</th>
                  <th>Status</th>
                  <th>Assigned JDs</th>
                  <th>Candidates Provided</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {vendors.map(vendor => (
                  <tr key={vendor.id}>
                    <td>
                      <strong>{vendor.vendor_name || vendor.company_name}</strong>
                      <span>{vendor.company_name || 'Independent vendor'}</span>
                    </td>
                    <td>
                      <strong>{vendor.contact_person || vendor.email}</strong>
                      <span>{vendor.email}</span>
                      {vendor.phone && <small>{vendor.phone}</small>}
                    </td>
                    <td><span className={`vendor-status status-${String(vendor.status || 'active').toLowerCase()}`}>{vendor.status}</span></td>
                    <td>{vendor.assigned_jds_count || 0}</td>
                    <td>{vendor.candidates_provided_count || 0}</td>
                    <td>
                      <div className="vendor-actions">
                        <button type="button" className="btn btn-success" onClick={() => openAssignJobs(vendor)} disabled={vendor.status !== 'Active'}>
                          <i className="fas fa-briefcase"></i> Assign JDs
                        </button>
                        <button type="button" className="btn btn-secondary" onClick={() => openEdit(vendor)}><i className="fas fa-edit"></i> Edit</button>
                        <button type="button" className="btn btn-danger" onClick={() => deleteVendor(vendor)}><i className="fas fa-trash-alt"></i> Delete</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {modalOpen && (
          <div className="vendor-modal-backdrop" role="presentation" onMouseDown={closeModal}>
            <form className="vendor-modal" onSubmit={saveVendor} onMouseDown={(event) => event.stopPropagation()}>
              <div className="vendor-modal-head">
                <div>
                  <h2>{editingVendor ? 'Edit Vendor' : 'Add Vendor'}</h2>
                  <p>{editingVendor ? 'Update vendor contact and status.' : 'Create a vendor for JD assignment.'}</p>
                </div>
                <button type="button" className="vendor-modal-close" onClick={closeModal} aria-label="Close vendor modal">
                  <i className="fas fa-times"></i>
                </button>
              </div>
              <div className="vendor-form-grid">
                <label><span>Vendor Name</span><input value={form.vendor_name} onChange={(event) => updateForm('vendor_name', event.target.value)} /></label>
                <label><span>Company Name</span><input value={form.company_name} onChange={(event) => updateForm('company_name', event.target.value)} /></label>
                <label><span>Contact Person</span><input value={form.contact_person} onChange={(event) => updateForm('contact_person', event.target.value)} /></label>
                <label><span>Email</span><input type="email" required value={form.email} onChange={(event) => updateForm('email', event.target.value)} /></label>
                <label><span>Phone</span><input value={form.phone} onChange={(event) => updateForm('phone', event.target.value)} /></label>
                <label><span>Status</span><select value={form.status} onChange={(event) => updateForm('status', event.target.value)}><option>Active</option><option>Inactive</option></select></label>
                <label className="vendor-form-wide"><span>Notes</span><textarea value={form.notes} onChange={(event) => updateForm('notes', event.target.value)} /></label>
                <label className="vendor-form-wide"><span>Supported Categories</span><input value={form.supported_categories} onChange={(event) => updateForm('supported_categories', event.target.value)} placeholder="Backend Development, QA" /><small>Comma-separated exact JD categories used for automated shortage assignment.</small></label>
                <label className="vendor-form-wide"><span>Supported Sub-tags</span><input value={form.supported_sub_tags} onChange={(event) => updateForm('supported_sub_tags', event.target.value)} placeholder="Python, Automation" /></label>
              </div>
              <div className="vendor-modal-actions">
                <button type="button" className="btn btn-secondary" onClick={closeModal} disabled={saving}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? <><i className="fas fa-spinner fa-spin"></i> Saving...</> : <><i className="fas fa-save"></i> Save Vendor</>}
                </button>
              </div>
            </form>
          </div>
        )}

        {assignModal && (
          <div className="vendor-modal-backdrop" role="presentation">
            <div className="vendor-modal vendor-assign-modal" role="dialog" aria-modal="true" aria-labelledby="vendor-assign-title">
              <div className="vendor-modal-head">
                <div>
                  <h2 id="vendor-assign-title">Assign JDs</h2>
                  <p>{assignModal.vendor_name || assignModal.company_name || assignModal.email}</p>
                </div>
                <button type="button" className="vendor-modal-close" onClick={() => !savingAssignments && setAssignModal(null)} aria-label="Close assign JDs">
                  <i className="fas fa-times"></i>
                </button>
              </div>

              <div className="vendor-assign-toolbar">
                <input value={jobSearch} onChange={(event) => setJobSearch(event.target.value)} placeholder="Search JDs..." />
                <span>{assignedJobIds.length} selected</span>
              </div>

              {assignmentError && <div className="vendor-alert vendor-alert-error">{assignmentError}</div>}

              <div className="vendor-job-select-list">
                {loadingAssignments ? (
                  <div className="vendor-job-empty">Loading JDs...</div>
                ) : filteredAssignJobs.length === 0 ? (
                  <div className="vendor-job-empty">No active JDs found.</div>
                ) : filteredAssignJobs.map(job => (
                  <label key={job.id} className={`vendor-job-option${assignedJobIds.includes(Number(job.id)) ? ' selected' : ''}`}>
                    <input type="checkbox" checked={assignedJobIds.includes(Number(job.id))} onChange={() => toggleJobSelection(job.id)} />
                    <span>
                      <strong>{job.title}</strong>
                      <small>{job.client_name || 'ShimentoX'}{job.location ? ` - ${job.location}` : ''}</small>
                    </span>
                  </label>
                ))}
              </div>

              <div className="vendor-modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setAssignModal(null)} disabled={savingAssignments}>Cancel</button>
                <button type="button" className="btn btn-success" onClick={saveJobAssignments} disabled={savingAssignments || loadingAssignments}>
                  {savingAssignments ? <><i className="fas fa-spinner fa-spin"></i> Saving...</> : <><i className="fas fa-save"></i> Save Assignments</>}
                </button>
              </div>
            </div>
          </div>
        )}

        {emailModal && (
          <div className="vendor-modal-backdrop" role="presentation">
            <div className="vendor-modal vendor-email-modal" role="dialog" aria-modal="true" aria-labelledby="vendor-email-title">
              <div className="vendor-modal-head">
                <div>
                  <h2 id="vendor-email-title">Send JD</h2>
                  <p>{emailModal.job?.title || 'Selected JD'} - {emailModal.vendor?.vendor_name || emailModal.vendor?.company_name || emailModal.to_email}</p>
                </div>
                <button type="button" className="vendor-modal-close" onClick={closeEmailModal} aria-label="Close send JD email">
                  <i className="fas fa-times"></i>
                </button>
              </div>

              <div className="vendor-email-grid">
                <label><span>From</span><input value={emailModal.from_email || 'Configured sender email'} readOnly /></label>
                <label><span>To</span><input value={emailModal.to_email || ''} onChange={(event) => updateEmail('to_email', event.target.value)} /></label>
              </div>
              <label className="vendor-email-field"><span>Subject</span><input value={emailModal.subject || ''} onChange={(event) => updateEmail('subject', event.target.value)} placeholder={emailBusy ? 'Generating...' : 'Subject'} /></label>
              <label className="vendor-email-field"><span>Message Body</span><textarea value={emailModal.body || ''} onChange={(event) => updateEmail('body', event.target.value)} placeholder={emailBusy ? 'Generating email...' : 'Message body'} /></label>

              <div className="vendor-email-attachments">
                <strong><i className="fas fa-paperclip"></i> Attachment</strong>
                <div className="vendor-email-attachment-list">
                  {(emailModal.attachments || []).length > 0
                    ? emailModal.attachments.map(file => <span key={file}>{file}</span>)
                    : <span>No saved JD file found. Choose a file below.</span>}
                  {manualAttachment && <span>{manualAttachment.name}</span>}
                </div>
                <label className="vendor-file-picker">
                  <i className="fas fa-upload"></i>
                  <span>{manualAttachment ? 'Change Manual JD File' : 'Attach JD From Computer'}</span>
                  <input type="file" accept=".pdf,.doc,.docx" onChange={(event) => setManualAttachment(event.target.files?.[0] || null)} />
                </label>
              </div>

              {emailModal.error && <div className="vendor-alert vendor-alert-error">{emailModal.error}</div>}

              <div className="vendor-modal-actions">
                <button type="button" className="btn btn-secondary" onClick={closeEmailModal} disabled={emailBusy}>Cancel</button>
                <button type="button" className="btn btn-success" onClick={sendVendorEmail} disabled={emailBusy || !emailModal.subject || !emailModal.body}>
                  {emailBusy ? <><i className="fas fa-spinner fa-spin"></i> Working...</> : <><i className="fas fa-paper-plane"></i> Send Email</>}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}

export default Vendors;
