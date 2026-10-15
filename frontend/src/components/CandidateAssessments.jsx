import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiGet } from '../api.js';
import { copyText, formatStamp } from './SendAssessmentModal.jsx';
import '../styles/send_assessment.css';

const LIFECYCLE_TONE = {
  generated: 'info', delivery_failed: 'bad', delivery_unknown: 'warn', awaiting_response: 'info',
  in_progress: 'warn', submitted: 'info', evaluated: 'good', terminated: 'bad', expired: 'muted',
};
const DELIVERY_LABEL = { sent: 'Email sent', failed: 'Email failed', unknown: 'Delivery uncertain', sending: 'Sending', not_sent: 'Not sent' };

function tone(assessment) {
  if (assessment.lifecycle === 'evaluated') return assessment.result?.passed ? 'good' : 'bad';
  return LIFECYCLE_TONE[assessment.lifecycle] || 'muted';
}

// Assessment attempts for one candidate, shown on the All Details page. refreshKey reloads after a send.
function CandidateAssessments({ candidateId, refreshKey = 0, onSend }) {
  const [state, setState] = useState({ loading: true, error: '', assessments: [], failures: [] });
  const [openHistory, setOpenHistory] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setState(prev => ({ ...prev, loading: true, error: '' }));
    apiGet(`/api/candidates/${candidateId}/assessments`)
      .then(data => {
        if (!cancelled) setState({ loading: false, error: '', assessments: data.assessments || [], failures: data.generation_failures || [] });
      })
      .catch(err => {
        if (!cancelled) setState(prev => ({ ...prev, loading: false, error: err.message || 'Could not load assessments.' }));
      });
    return () => { cancelled = true; };
  }, [candidateId, refreshKey]);

  const { loading, error, assessments, failures } = state;

  return (
    <section className="cp-card sa-panel" aria-labelledby="sa-panel-title">
      <header className="cp-card-head">
        <h2 id="sa-panel-title"><i className="fas fa-clipboard-question" aria-hidden="true" /> Assessments</h2>
        {onSend && (
          <button type="button" className="cp-btn cp-btn-ghost cp-btn-sm" onClick={onSend}>
            <i className="fas fa-paper-plane" aria-hidden="true" /> Send assessment
          </button>
        )}
      </header>

      {loading && <p className="cp-muted"><i className="fas fa-spinner fa-spin" aria-hidden="true" /> Loading assessments…</p>}
      {!loading && error && <p className="cp-note bad">{error}</p>}

      {!loading && failures.map(failure => (
        <div key={`${failure.jd_id}-${failure.at}`} className="sa-banner bad">
          <i className="fas fa-circle-exclamation" aria-hidden="true" />
          <span>
            Generation failed for <strong>{failure.jd_title || `JD #${failure.jd_id}`}</strong>
            {failure.at ? ` on ${formatStamp(failure.at)}` : ''}. {failure.error}
          </span>
          {onSend && <button type="button" className="btn btn-secondary sa-inline-btn" onClick={onSend}>Retry</button>}
        </div>
      ))}

      {!loading && !error && assessments.length === 0 && failures.length === 0 && (
        <p className="cp-muted">No assessments yet. Send one to evaluate this candidate against a job description.</p>
      )}

      {!loading && assessments.length > 0 && (
        <ul className="sa-list">
          {assessments.map(item => {
            const result = item.result;
            const history = item.delivery_history || [];
            const facts = [
              ['Generated', item.created_at],
              ['Email sent', item.email_sent_at || item.sent_at],
              ['Started', item.started_at],
              ['Submitted', item.completed_at],
              [item.lifecycle === 'expired' ? 'Expired' : 'Link expires', ['generated', 'delivery_failed'].includes(item.lifecycle) ? null : item.token_expires_at],
            ].filter(([, value]) => value);
            return (
              <li key={item.id} className="sa-item">
                <div className="sa-item-head">
                  <div>
                    <strong>{item.jd_title || item.title}</strong>
                    {item.client_name && <small>{item.client_name}</small>}
                  </div>
                  <span className={`sa-pill ${tone(item)}`}>{item.lifecycle_label}</span>
                </div>
                {item.screening_override && (
                  <p className="sa-muted sa-override"><i className="fas fa-rotate-right" aria-hidden="true" /> Sent after resume screening{item.initiated_by ? ` by ${item.initiated_by}` : ''}. Review the result to decide whether to reconsider the candidate.</p>
                )}
                {result && (
                  <div className="sa-result">
                    <b className={result.passed ? 'good' : 'bad'}>{result.percentage ?? '—'}%</b>
                    <span>{result.passed ? 'Passed' : 'Did not pass'} · pass mark {item.passing_score}%{result.pending_review_count ? ` · ${result.pending_review_count} answer(s) awaiting review` : ''}</span>
                  </div>
                )}
                {item.termination_reason && <p className="cp-note bad">{item.termination_reason}</p>}
                <dl className="sa-facts">
                  {facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{formatStamp(value)}</dd></div>)}
                  <div><dt>Delivery</dt><dd>{DELIVERY_LABEL[item.email_delivery_status] || item.email_delivery_status}{item.candidate_email ? ` · ${item.candidate_email}` : ''}</dd></div>
                </dl>
                {item.email_delivery_error && item.email_delivery_status !== 'sent' && <p className="sa-field-error">{item.email_delivery_error}</p>}
                <div className="sa-item-actions">
                  {item.assessment_link && (
                    <button type="button" className="cp-btn cp-btn-ghost cp-btn-sm" onClick={() => copyText(item.assessment_link)}>
                      <i className="fas fa-copy" aria-hidden="true" /> Copy link
                    </button>
                  )}
                  <Link className="cp-btn cp-btn-ghost cp-btn-sm" to={`/hiring-pipeline/assessment/${item.id}`}>
                    <i className="fas fa-up-right-from-square" aria-hidden="true" /> {result ? 'View result' : 'Open assessment'}
                  </Link>
                  {history.length > 0 && (
                    <button type="button" className="sa-link-btn" aria-expanded={openHistory === item.id}
                      onClick={() => setOpenHistory(prev => (prev === item.id ? null : item.id))}>
                      Email history ({history.length})
                    </button>
                  )}
                </div>
                {openHistory === item.id && (
                  <ol className="sa-history">
                    {history.map((entry, index) => (
                      <li key={index}>
                        <span className={`sa-pill ${entry.status === 'sent' ? 'good' : entry.status === 'unknown' ? 'warn' : 'bad'}`}>{DELIVERY_LABEL[entry.status] || entry.status}</span>
                        <span>{formatStamp(entry.at)}{entry.to_email ? ` · ${entry.to_email}` : ''}{entry.by ? ` · by ${entry.by}` : ''}</span>
                        {entry.error && <small>{entry.error}</small>}
                      </li>
                    ))}
                  </ol>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export default CandidateAssessments;
