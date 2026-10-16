import React, { useEffect, useRef, useState } from 'react';
import { apiGet, apiPost } from '../api.js';
import { toast } from './EnterpriseFeedback.jsx';
import '../styles/send_assessment.css';

export function newRequestId() {
  try {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  } catch { /* fall through */ }
  return `req-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    try { document.execCommand('copy'); } finally { area.remove(); }
  }
  toast({ type: 'success', message: 'Assessment link copied.' });
}

export function formatStamp(value) {
  if (!value) return '';
  const parsed = new Date(String(value));
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString([], { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function jdLabel(jd) {
  return [jd.title || `JD #${jd.id}`, jd.client_name].filter(Boolean).join(' · ');
}

// Generate a JD-specific assessment as a draft and open it in Preview Assessment, where the recruiter
// reviews, edits, validates and confirms before anything is emailed. Shared by the Talent table and All
// Details; both call the same backend workflow (POST /api/candidates/:id/assessments/send). An assessment
// that was already sent can be re-emailed here with the same link.
function SendAssessmentModal({ candidate, onClose, onSent }) {
  const [jds, setJds] = useState([]);
  const [jdsLoading, setJdsLoading] = useState(true);
  const [jdsError, setJdsError] = useState('');
  const [jdId, setJdId] = useState('');
  const [email, setEmail] = useState(candidate?.email || '');
  const [editingEmail, setEditingEmail] = useState(!candidate?.email);
  const [emailError, setEmailError] = useState('');
  const [working, setWorking] = useState(false);
  const [error, setError] = useState(null);
  const [outcome, setOutcome] = useState(null);
  // One id per submission: a retry after a timeout reuses it, so the server never sends twice.
  const requestId = useRef(newRequestId());
  const selectRef = useRef(null);

  const loadJds = () => {
    setJdsLoading(true);
    setJdsError('');
    apiGet('/api/jds')
      .then(data => {
        const rows = (Array.isArray(data) ? data : []).filter(jd => jd && jd.id);
        setJds(rows);
        const preferred = rows.find(jd => String(jd.id) === String(candidate?.jd_id) && jd.status !== 'Closed');
        if (preferred) setJdId(String(preferred.id));
      })
      .catch(() => setJdsError('Could not load job descriptions. Check your connection and try again.'))
      .finally(() => setJdsLoading(false));
  };

  useEffect(loadJds, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!jdsLoading) selectRef.current?.focus(); }, [jdsLoading]);
  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape' && !working) onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [working, onClose]);

  const selectedJd = jds.find(jd => String(jd.id) === String(jdId));
  const canSubmit = Boolean(selectedJd) && selectedJd.status !== 'Closed' && (!editingEmail || email.trim()) && !working;

  const submit = async ({ resend = false } = {}) => {
    if (!selectedJd) return;
    setWorking(true);
    setError(null);
    setEmailError('');
    let response;
    try {
      response = await apiPost(`/api/candidates/${candidate.id}/assessments/send`, {
        jd_id: Number(selectedJd.id),
        request_id: requestId.current,
        to_email: editingEmail ? email.trim() : '',
        resend,
      });
    } catch {
      setWorking(false);
      setError({
        message: 'The connection dropped before the server replied. Retrying is safe: it will not create a second assessment or send a second email.',
        retry: 'Retry',
      });
      return;
    }
    setWorking(false);
    const { ok, status, data = {} } = response;
    const code = data.code || '';
    if (ok && code === 'draft_ready') {
      requestId.current = newRequestId();
      setOutcome({ kind: 'draft', message: data.message, assessment: data.assessment });
      toast({ type: 'info', message: 'Assessment generated as a draft. Review it before sending.' });
      onSent?.(data.assessment);
      return;
    }
    if (ok) {
      requestId.current = newRequestId();
      setOutcome({ kind: code === 'delivery_unknown' ? 'unknown' : 'sent', message: data.message, assessment: data.assessment });
      toast({ type: code === 'delivery_unknown' ? 'info' : 'success', message: data.message || 'Assessment sent.' });
      onSent?.(data.assessment);
      return;
    }
    if (code === 'email_missing' || code === 'email_invalid') {
      setEditingEmail(true);
      if (data.email) setEmail(data.email);
      setEmailError(data.error);
      return;
    }
    if (code === 'already_sent') {
      setOutcome({ kind: 'already_sent', message: data.error, assessment: data.assessment });
      return;
    }
    if (code === 'attempt_in_progress' || code === 'attempt_submitted') {
      setOutcome({ kind: 'blocked', message: data.error, assessment: data.assessment });
      return;
    }
    if (code === 'delivery_failed') onSent?.(null);
    const retry = {
      generation_failed: 'Retry generation',
      delivery_failed: 'Retry sending',
      request_in_progress: 'Try again',
      server_error: 'Retry',
    }[code];
    setError({
      message: data.error || `Could not send the assessment (error ${status}).`,
      note: code === 'delivery_failed' ? 'The assessment was saved. Retrying sends the same assessment; it is not generated again.' : '',
      retry,
    });
  };

  const resend = () => {
    requestId.current = newRequestId();
    submit({ resend: true });
  };

  const link = outcome?.assessment?.assessment_link;

  return (
    <div className="jd-modal-backdrop sa-backdrop" role="presentation">
      <div className="jd-schedule-modal sa-modal" role="dialog" aria-modal="true" aria-labelledby="sa-modal-title">
        <div className="jd-modal-header">
          <h2 id="sa-modal-title"><i className="fas fa-clipboard-question" aria-hidden="true"></i> Generate Assessment</h2>
          <button type="button" className="jd-modal-close" onClick={onClose} disabled={working} aria-label="Close">
            <i className="fas fa-times" aria-hidden="true"></i>
          </button>
        </div>
        <p className="sa-modal-sub">
          For <strong>{candidate?.name || 'this candidate'}</strong>
          {/reject/i.test(candidate?.status || '') && <span className="sa-chip">Rejected at screening</span>}
        </p>

        {outcome ? (
          <div className="sa-outcome" role="status">
            <div className={`sa-banner ${['sent', 'draft'].includes(outcome.kind) ? 'good' : outcome.kind === 'blocked' ? 'info' : 'warn'}`}>
              <i className={`fas ${['sent', 'draft'].includes(outcome.kind) ? 'fa-circle-check' : outcome.kind === 'blocked' ? 'fa-circle-info' : 'fa-triangle-exclamation'}`} aria-hidden="true"></i>
              <span>{outcome.message}</span>
            </div>
            {outcome.assessment && (
              <dl className="sa-facts">
                <div><dt>Job</dt><dd>{[outcome.assessment.jd_title, outcome.assessment.client_name].filter(Boolean).join(' · ')}</dd></div>
                <div><dt>Status</dt><dd>{outcome.assessment.lifecycle_label}</dd></div>
                {outcome.assessment.candidate_email && <div><dt>{outcome.kind === 'draft' ? 'Will be sent to' : 'Sent to'}</dt><dd>{outcome.assessment.candidate_email}</dd></div>}
                {outcome.assessment.token_expires_at && <div><dt>Link expires</dt><dd>{formatStamp(outcome.assessment.token_expires_at)}</dd></div>}
              </dl>
            )}
            {link && (
              <div className="sa-link">
                <input readOnly value={link} aria-label="Assessment link" onFocus={(event) => event.target.select()} />
                <button type="button" className="btn btn-secondary" onClick={() => copyText(link)}>
                  <i className="fas fa-copy" aria-hidden="true"></i> Copy link
                </button>
              </div>
            )}
            <div className="jd-modal-actions">
              {(outcome.kind === 'already_sent' || outcome.kind === 'unknown') && (
                <button type="button" className="btn btn-secondary" onClick={resend} disabled={working}>
                  {working ? <><i className="fas fa-spinner fa-spin" aria-hidden="true"></i> Resending…</>
                    : <><i className="fas fa-paper-plane" aria-hidden="true"></i> Resend same link</>}
                </button>
              )}
              {outcome.kind === 'draft' ? (
                <>
                  <button type="button" className="btn btn-secondary" onClick={onClose}>Later</button>
                  <a className="btn btn-primary" href={`/hiring-pipeline/assessment/${outcome.assessment?.id}?preview=1`}>
                    <i className="fas fa-eye" aria-hidden="true"></i> Review &amp; Send
                  </a>
                </>
              ) : (
                <button type="button" className="btn btn-primary" onClick={onClose} disabled={working}>Done</button>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="form-group">
              <label htmlFor="sa-jd">Job description</label>
              {jdsLoading ? (
                <p className="sa-muted"><i className="fas fa-spinner fa-spin" aria-hidden="true"></i> Loading job descriptions…</p>
              ) : jdsError ? (
                <div className="sa-banner bad">
                  <span>{jdsError}</span>
                  <button type="button" className="btn btn-secondary sa-inline-btn" onClick={loadJds}>Retry</button>
                </div>
              ) : jds.length === 0 ? (
                <p className="sa-muted">No job descriptions are configured yet. Create one under Jobs first.</p>
              ) : (
                <select id="sa-jd" ref={selectRef} value={jdId} onChange={(event) => { setJdId(event.target.value); setError(null); }} disabled={working}>
                  <option value="">Select a job description…</option>
                  {jds.map(jd => (
                    <option key={jd.id} value={jd.id} disabled={jd.status === 'Closed'}>
                      {jdLabel(jd)}{jd.status === 'Closed' ? ' (closed)' : ''}
                    </option>
                  ))}
                </select>
              )}
              {selectedJd && (
                <p className="sa-muted sa-jd-meta">
                  {[selectedJd.job_code, selectedJd.location, selectedJd.experience && `${selectedJd.experience} experience`,
                    (selectedJd.skills || []).length ? `${selectedJd.skills.length} skills` : ''].filter(Boolean).join(' · ')}
                </p>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="sa-email">Candidate email</label>
              {editingEmail ? (
                <input id="sa-email" type="email" value={email} onChange={(event) => { setEmail(event.target.value); setEmailError(''); }}
                  aria-invalid={Boolean(emailError)} aria-describedby={emailError ? 'sa-email-error' : undefined} disabled={working}
                  placeholder="candidate@example.com" />
              ) : (
                <div className="sa-email-row">
                  <span><i className="far fa-envelope" aria-hidden="true"></i> {email}</span>
                  <button type="button" className="sa-link-btn" onClick={() => setEditingEmail(true)} disabled={working}>Edit</button>
                </div>
              )}
              {emailError && <p id="sa-email-error" className="sa-field-error" role="alert">{emailError}</p>}
              {!emailError && <p className="sa-muted">Taken from the candidate's resume. A corrected address is used for this assessment only.</p>}
            </div>

            <p className="sa-muted sa-explainer">
              A timed assessment with a pass mark is generated by AI from the selected JD's skills, responsibilities
              and qualifications and saved as a draft. Nothing is emailed until you review it in the preview, validate it
              and confirm sending. The candidate's hiring stage is not changed.
            </p>

            {working && (
              <div className="sa-banner info" role="status">
                <i className="fas fa-spinner fa-spin" aria-hidden="true"></i>
                <span>Generating and validating the assessment. This can take up to a minute…</span>
              </div>
            )}
            {error && (
              <div className="sa-banner bad" role="alert">
                <i className="fas fa-circle-exclamation" aria-hidden="true"></i>
                <span>{error.message}{error.note && <><br /><small>{error.note}</small></>}</span>
              </div>
            )}

            <div className="jd-modal-actions">
              <button type="button" className="btn btn-secondary" onClick={onClose} disabled={working}>Cancel</button>
              <button type="button" className="btn btn-primary" onClick={() => submit()} disabled={!canSubmit}>
                {working ? <><i className="fas fa-spinner fa-spin" aria-hidden="true"></i> Generating…</>
                  : <><i className="fas fa-wand-magic-sparkles" aria-hidden="true"></i> {error?.retry || 'Generate & Review Assessment'}</>}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default SendAssessmentModal;
