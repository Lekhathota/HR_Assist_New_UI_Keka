import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { toast } from '../components/EnterpriseFeedback.jsx';
import { apiGet, apiPost } from '../api.js';
import '../styles/workflow_admin.css';

function splitList(value) {
  return String(value || '').split(',').map(item => item.trim()).filter(Boolean);
}

function WorkflowAdmin() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [defaultCount, setDefaultCount] = useState('');
  const [countEdits, setCountEdits] = useState({});
  const [categoryEdits, setCategoryEdits] = useState({});

  const load = () => {
    setLoading(true);
    apiGet('/api/admin/workflow-readiness')
      .then(payload => setData(payload))
      .catch(err => toast({ type: 'error', message: err.message || 'Could not load workflow readiness.' }))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const applyPayload = payload => setData(payload.readiness || payload);

  const runBackfill = async () => {
    setBusy(true);
    try {
      const { ok, data: payload } = await apiPost('/api/admin/workflow-backfill', {
        default_required_candidate_count: defaultCount || null,
      });
      if (!ok) throw new Error(payload.error || 'Backfill failed.');
      applyPayload(payload);
      toast({ type: 'success', message: 'Workflow defaults backfilled.' });
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Backfill failed.' });
    } finally {
      setBusy(false);
    }
  };

  const saveCount = async jd => {
    const next = countEdits[jd.id] || jd.required_candidate_count || '';
    const { ok, data: payload } = await apiPost(`/api/admin/jds/${jd.id}/required-count`, { required_candidate_count: Number(next) });
    if (!ok) throw new Error(payload.error || 'Could not update JD count.');
    applyPayload(payload);
    toast({ type: 'success', message: 'JD required count updated.' });
  };

  const saveVendorCategories = async vendor => {
    const raw = categoryEdits[vendor.id] ?? (vendor.supported_categories || []).join(', ');
    const { ok, data: payload } = await apiPost(`/api/admin/vendors/${vendor.id}/categories`, {
      supported_categories: splitList(raw),
      supported_sub_tags: [],
    });
    if (!ok) throw new Error(payload.error || 'Could not update vendor categories.');
    applyPayload(payload);
    toast({ type: 'success', message: 'Vendor categories updated.' });
  };

  const summary = data?.summary || {};

  return (
    <Layout>
      <div className="workflow-admin-page">
        <header className="workflow-admin-head">
          <div>
            <h1><i className="fas fa-screwdriver-wrench"></i> Workflow Admin</h1>
            <p>Prepare legacy data for automated bench analysis and vendor shortage assignment.</p>
          </div>
          <button type="button" className="btn btn-secondary" onClick={load} disabled={loading || busy}>
            <i className="fas fa-rotate"></i> Refresh
          </button>
        </header>

        <section className="workflow-admin-metrics">
          {[
            ['Active JDs', summary.active_jds || 0],
            ['Workflow Ready', summary.workflow_ready_jds || 0],
            ['Missing Counts', summary.missing_required_counts || 0],
            ['Category Review', summary.category_review_required || 0],
            ['Vendor Gaps', summary.vendors_without_categories || 0],
          ].map(([label, value]) => <div key={label}><strong>{value}</strong><span>{label}</span></div>)}
        </section>

        <section className="workflow-admin-panel">
          <div>
            <h2>Backfill Defaults</h2>
            <p>Fill missing workflow fields on old records. Optional default count only applies to JDs with no count.</p>
          </div>
          <div className="workflow-admin-action">
            <input type="number" min="1" value={defaultCount} onChange={event => setDefaultCount(event.target.value)} placeholder="Optional JD count" />
            <button type="button" className="btn btn-primary" onClick={runBackfill} disabled={busy}>
              <i className="fas fa-database"></i> Run Backfill
            </button>
          </div>
        </section>

        <div className="workflow-admin-grid">
          <section className="workflow-admin-panel">
            <h2>JDs Missing Required Count</h2>
            {loading ? <div className="workflow-admin-empty">Loading...</div> : (data?.missing_counts || []).length === 0 ? <div className="workflow-admin-empty">No missing counts.</div> : (
              <div className="workflow-admin-list">
                {data.missing_counts.map(jd => (
                  <article key={jd.id} className="workflow-admin-item">
                    <span><Link to={`/jobs/${jd.id}`}>{jd.title || `JD ${jd.id}`}</Link><small>{jd.job_category || 'No category'}</small></span>
                    <input type="number" min="1" value={countEdits[jd.id] ?? ''} onChange={event => setCountEdits(prev => ({ ...prev, [jd.id]: event.target.value }))} placeholder="Count" />
                    <button type="button" className="btn btn-success" onClick={() => saveCount(jd)}><i className="fas fa-check"></i></button>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="workflow-admin-panel">
            <h2>JDs Needing Category Review</h2>
            {(data?.category_review || []).length === 0 ? <div className="workflow-admin-empty">No category review items.</div> : (
              <div className="workflow-admin-list">
                {data.category_review.map(jd => (
                  <article key={jd.id} className="workflow-admin-item workflow-admin-item-readonly">
                    <span><Link to={`/jobs/${jd.id}`}>{jd.title || `JD ${jd.id}`}</Link><small>{jd.job_category || 'No category detected'}</small></span>
                    <Link className="btn btn-secondary" to={`/jobs/${jd.id}`}><i className="fas fa-arrow-right"></i></Link>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>

        <section className="workflow-admin-panel">
          <h2>Vendors Without Automated Categories</h2>
          {(data?.vendor_category_gaps || []).length === 0 ? <div className="workflow-admin-empty">All active vendors have automated categories.</div> : (
            <div className="workflow-admin-list">
              {data.vendor_category_gaps.map(vendor => (
                <article key={vendor.id} className="workflow-admin-item workflow-admin-vendor-item">
                  <span><strong>{vendor.vendor_name || vendor.company_name || vendor.email}</strong><small>{vendor.email}</small></span>
                  <input value={categoryEdits[vendor.id] ?? ''} onChange={event => setCategoryEdits(prev => ({ ...prev, [vendor.id]: event.target.value }))} placeholder={(data.categories || []).slice(0, 3).join(', ') || 'Backend, QA'} />
                  <button type="button" className="btn btn-success" onClick={() => saveVendorCategories(vendor)}><i className="fas fa-check"></i> Save</button>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </Layout>
  );
}

export default WorkflowAdmin;
